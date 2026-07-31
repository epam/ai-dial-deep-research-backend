## MODIFIED Requirements

### Requirement: Streaming response path
The app SHALL produce its assistant response through the SDK's streaming API so that the streaming code path is exercised end-to-end.

**Preparation text SHALL stream token-by-token** as the LLM produces it, rather than being buffered and emitted as a single chunk after the producing graph node returns; concretely, the preparation agent's `astream` invocation SHALL subscribe to LangGraph's `messages` stream mode (composed with the existing `updates` mode) and forward every `AIMessageChunk`'s text content to `choice.append_content` immediately, so users see content arrive while the model is still generating.

**The research report SHALL NOT stream.** A report draft may still be revised when it is produced (see the **report-composition** capability's review loop), and DIAL content is append-only, so no draft may reach `choice` while the loop is running. The report SHALL be appended in one call once the loop settles on the draft to deliver. The research graph's stream therefore need not subscribe to the `messages` mode at all; DIAL stages and the SDK keep-alive carry the turn while the loop runs.

#### Scenario: Streamed delivery
- **WHEN** DIAL core requests a streaming chat completion
- **THEN** the app SHALL emit the assistant content via one or more streaming chunks terminated by an end-of-stream signal, conforming to the SDK's streaming contract

#### Scenario: Preparation text streams token-by-token, not message-by-message
- **WHEN** the preparation agent's underlying LLM produces a multi-token assistant message (whether a final answer or an intermediate text-plus-tool-calls message)
- **THEN** the app SHALL emit `choice.append_content` calls for individual token chunks during generation, such that DIAL core observes incremental content updates before the producing LangGraph node has returned, and SHALL NOT defer the text to a single end-of-step emission

#### Scenario: The report is appended once, not streamed
- **WHEN** the report node produces a draft, whether it is approved or revised afterwards
- **THEN** no token of any draft SHALL be appended to `choice` while the review loop runs, and the delivered report SHALL reach `choice` as a single append after the loop settles

### Requirement: Transient LLM stream drops retried in-app

Every LLM chat-completion call the app makes SHALL be retried in-app when it fails with a
transient mid-stream connection drop — the connection dying after response headers arrived,
surfaced as `httpx.RemoteProtocolError` (peer closed the connection mid-body) or
`httpx.ReadError` (connection reset while reading). The OpenAI client's own `max_retries` covers
only failures before a response starts, so without this a single dropped stream aborts the whole
turn.

This applies to every LLM call surface: the preparation, playground, and research-agent model
calls; the structured review calls (query review, plan review, research review, **report
review**); and the report-writing call, for its first draft and every revision alike. Retry
coverage is opted into per call site, so a new LLM call is not covered until its site wraps
itself — adding a call surface without it silently breaks this requirement. The retry budget is 2
retries per call (3 attempts total) with exponential backoff and jitter. A retry re-issues the
failed call from scratch with the same inputs; partial tokens the failed attempt already streamed
to the user are not retracted, so a retried call MAY render duplicated partial text in the chat
(accepted: observed drops occur at stream start, and a rare visual duplicate is preferred over
losing a long research turn). Since the report no longer streams to the user, a retried report
call cannot duplicate visible text.

When the budget is exhausted, the last exception SHALL propagate unchanged to the top-level
handler and deliver through the DIAL error protocol per **Failures delivered as DIAL protocol
errors** — **except at the two call sites the report loop absorbs**: the report-review call, and a
report revision once a draft exists. There the exhausted exception SHALL be caught inside the loop
and the current or previous draft delivered instead (see **report-composition**), because a finished
report must not be discarded over a later failure. The **first** draft is not an exception: no draft
exists yet, so propagation remains correct for it. Exceptions other than the two transient-drop shapes SHALL NOT trigger this retry; they
keep their existing handling.

#### Scenario: Stream drops once at the start of an agent model call
- **WHEN** an agent model call's stream dies with `httpx.RemoteProtocolError` and the retried
  call succeeds
- **THEN** the turn SHALL complete normally with no error delivered to the user

#### Scenario: Stream drops persistently
- **WHEN** an LLM call whose failure aborts the turn fails with `httpx.RemoteProtocolError` on every attempt in the budget
- **THEN** the app SHALL stop after 3 attempts and deliver the failure through the DIAL error
  protocol, resolved as the retryable network-drop message with an error reference

#### Scenario: Persistent drops in the report loop do not abort the turn
- **WHEN** the report-review call, or a report revision written after a first draft, fails on every attempt in the budget
- **THEN** the app SHALL NOT deliver a protocol error; the report loop SHALL absorb the failure, deliver the current or previous draft, and log a warning

#### Scenario: Report stream drops mid-content
- **WHEN** the report-writing stream drops mid-content and a retry succeeds
- **THEN** the turn SHALL complete with the retried report, and the delivered and persisted report SHALL be the retried attempt's full text only; no partial text SHALL be visible to the user, since a report reaches the choice only once the review loop settles

#### Scenario: Non-transient failures are not retried in-app
- **WHEN** an LLM call fails with an HTTP status error (e.g. 400) or a timeout
- **THEN** the in-app stream-drop retry SHALL NOT engage; the failure keeps its existing handling
  (the OpenAI client's own retries and the DIAL error protocol)

### Requirement: Failures delivered as DIAL protocol errors

The app SHALL resolve every turn-aborting failure to an accurate, user-safe message and deliver it
through the **DIAL error protocol**, never as fake-success HTTP 200 assistant content. This applies
whether an exception reaches the top-level handler or a known turn-aborting condition holds (a turn
"cannot produce its intended answer").

**Cause resolution.** The app SHALL normalize the failure into a common view (HTTP status, error
`code`, error `type`, internal message, and user-safe `display_message`) extracted best-effort
from the supported exception shapes (`openai` LLM errors, `aidial_sdk.exceptions.HTTPException`,
raw `httpx` errors); normalization SHALL be total — a malformed or absent error body yields an
empty view, never a second exception. The app SHALL then choose the user-facing message by a fixed
precedence, most-specific first:

1. the upstream's own `display_message`, used verbatim (rendered as plain text and length-capped),
   with nothing appended;
2. a curated error-`code` map (at least `content_filter` and `context_length_exceeded`);
3. a status/type map with wording specific to the failing surface (AI model vs a required
   service), including timeout, connectivity, and mid-stream connection-drop causes — a
   transport-level stream drop (`httpx.RemoteProtocolError`, reaching the resolver only after
   the in-app retries per **Transient LLM stream drops retried in-app** are exhausted) SHALL
   resolve to the retryable service network-error message, never the generic non-retryable HTTP
   fallback;
4. a dedicated mid-stream rule for a plain `openai.APIError` (an LLM call that failed after its
   stream began) that carries no usable status or code;
5. curated messages for known internal conditions (research step-budget exhaustion; the two
   turn-aborting app conditions below);
6. a generic fallback.

Each resolution SHALL be classified retryable or not; the app SHALL append a single "try again
later" sentence only to retryable resolutions, and SHALL NOT append it to a `display_message`
resolution or to any non-retryable resolution (which carries its own advice). User-facing text
SHALL contain only the upstream `display_message` (user-safe by DIAL contract) or curated wording
— never a raw stack trace, endpoint, header, or the internal error message.

**Error reference.** Every failure handled at the top level SHALL be stamped with a short opaque
reference (8 hex characters) that appears in both the user-facing message (suffixed as
`(error reference: <ref>)`) and a single server log record that also carries the stack trace, the
normalized internal details, and the retryable classification.

**Delivery.** The handler SHALL raise `aidial_sdk.exceptions.HTTPException` built from the
resolution (`display_message` and `message` both set to the composed user-facing text + reference;
`code` and `type` propagated from the normalized details) so the SDK delivers it as a non-200
error body (for non-streaming requests, or failures before the choice opens) or as an in-stream
`{"error": ...}` chunk terminating the open 200 stream (for streaming requests, i.e. any failure
after the choice opens). Any content already appended to the choice SHALL remain visible with the
error rendered beneath it — preparation text, which streams. A report cannot contribute partial
content, because it is appended only once the review loop settles. The app SHALL NOT append the
error as ordinary assistant `content`, and SHALL NOT persist state on a turn that aborts.

**Outgoing-status policy.** The app SHALL NOT emit a status DIAL Core's balancer treats as
retriable (429, 502, 503, 504). A client-attributable status (one of 400, 401, 403, 404, 409, 413,
422) SHALL pass through; every other cause — upstream rate limits and outages, stream failures,
timeouts, unknown internal errors — SHALL be emitted as 500. The true cause SHALL be preserved in
`code`, so a 500 MAY carry `code: "429"`; consumers classify by `code`, not `status_code`.

**Turn-aborting app conditions.** The two outcomes that previously rendered as friendly assistant
content SHALL instead be delivered as protocol errors: an application whose properties cannot be
**validated** (unconfigured) SHALL resolve to a non-retryable "not configured — contact your
administrator" message (outgoing 500), and a conversation whose research has already been handed
off SHALL resolve to a non-retryable "start a new conversation" message (outgoing 409). A failure
to **fetch** the properties from DIAL Core (as opposed to validate them) SHALL propagate to the
top-level handler and resolve through the status/type map to a service message, rather than being
reported as "not configured".

**Absorbed failures are unaffected.** Failures that are deliberately swallowed and never abort the
turn SHALL NOT trigger this path: per-tool errors caught by `handle_tool_error` (surfaced as an
`error ❌` stage), a failed report-review call and a failed report revision once a draft exists (both
absorbed by the report loop, which delivers a draft instead), Opik-tracing failures, and
image-rehydration failures. These continue to let the
turn complete normally.

#### Scenario: Upstream failure carrying a display message
- **WHEN** an LLM call fails with an error whose DIAL body carries a `display_message`
- **THEN** the app SHALL deliver that `display_message` verbatim (plain text, length-capped) as the
  user-facing error text with the error reference appended, and SHALL NOT append a "try again
  later" sentence to it

#### Scenario: LLM failure mid-stream after partial content
- **WHEN** the preparation agent has already streamed some assistant content and the LLM then fails
  mid-stream (a plain `openai.APIError` with no usable status/code)
- **THEN** the app SHALL deliver an in-stream `{"error": ...}` chunk terminating the stream, the
  already-streamed partial content SHALL remain visible, and the error text SHALL be the dedicated
  mid-stream message (retryable, so "try again later"-suffixed) plus the error reference — never the
  generic fallback

#### Scenario: Exhausted stream-drop retries resolve retryable
- **WHEN** an LLM call fails with `httpx.RemoteProtocolError` after the in-app retry budget of
  **Transient LLM stream drops retried in-app** is exhausted
- **THEN** the resolved user-facing text SHALL be the service network-error message with the "try
  again later" sentence appended plus the error reference, classified retryable — never the
  generic non-retryable HTTP message

#### Scenario: Context-length and content-filter causes get actionable text
- **WHEN** the model rejects the request with `code: "context_length_exceeded"` or
  `code: "content_filter"`
- **THEN** the code map SHALL resolve it to the actionable message (shorten the messages / rephrase
  the message) ahead of the status ladder, classified non-retryable

#### Scenario: MCP server unreachable
- **WHEN** the MCP server cannot be reached at the configured endpoint during a turn
- **THEN** the app SHALL log the failure with an error reference and deliver a DIAL protocol error
  whose user-facing text is the resolved service/connectivity message plus the reference — not an
  HTTP 200 completion carrying error content

#### Scenario: Genuinely unknown failure is stamped and logged
- **WHEN** an unexpected exception with no usable error body reaches the top-level handler
- **THEN** the app SHALL deliver the generic fallback message suffixed with an error reference, and
  SHALL write one server log record carrying that same reference together with the stack trace, so
  the reference the user reports can be grepped to the log entry

#### Scenario: Never emits a balancer-retriable status
- **WHEN** the resolved cause is an upstream 429, 502, 503, or 504 (or a mid-stream failure whose
  backfilled status is one of these)
- **THEN** the app SHALL emit outgoing HTTP 500 with the true cause preserved in `code` (e.g.
  `code: "429"`), and SHALL NOT emit 429/502/503/504

#### Scenario: Failed turn is kept out of LLM-visible history
- **WHEN** a turn aborts and is delivered as a protocol error
- **THEN** the app SHALL NOT write the error text into assistant `content` and SHALL NOT persist
  turn state, so a subsequent turn (e.g. after DIAL Chat regenerates) does not replay the error
  text to the model

#### Scenario: Unconfigured application delivered as a protocol error
- **WHEN** a request's DIAL application properties cannot be validated
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 500) whose text is
  the "not configured — contact your administrator" message plus an error reference, and SHALL NOT
  run any agent or append the message as assistant content

#### Scenario: Research-already-handed-off delivered as a protocol error
- **WHEN** a request arrives on a conversation whose research was already handed off on an earlier
  turn
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 409) whose text is
  the "start a new conversation" message plus an error reference, and SHALL NOT append that message
  as assistant content nor persist any state for the turn

#### Scenario: Property fetch failure is not masked as "not configured"
- **WHEN** fetching the application properties from DIAL Core fails (e.g. Core unreachable or a
  5xx), as opposed to the properties failing validation
- **THEN** the failure SHALL propagate to the top-level handler and resolve through the status/type
  map to a service message with the appropriate retryability, rather than being reported as "not
  configured"

### Requirement: Tool-calling agent over MCP-loaded tools

Each chat completion request SHALL first be handled by the preparation agent (see
the **clarification-and-plan-alignment** capability). When the preparation agent
approves a plan and calls `start_research`, the app SHALL run the **research
execution graph** (see the **research-execution** capability) in the same turn; the
research agent is the graph's **research-agent node**, not a directly-invoked
first-message agent.

The research-agent node SHALL be a fresh per-request LangChain `create_agent` over the
tools fetched from a freshly-constructed MCP client, plus one sentinel tool
(`finish_iteration`). It SHALL have access only to MCP-loaded tools and that
sentinel — no other built-in tools, subagents, skills, or persistent memory beyond
the graph state. Research-agent SHALL be run with **forced tool choice** — every model
call re-issued with `tool_choice="any"` by an in-process `AgentMiddleware` — so every
model step emits a tool call and the model can never emit a free-form assistant
message.

A research-agent iteration therefore ends **only** when research-agent calls
`finish_iteration`, which SHALL be declared `return_direct=True`: the agent loop
returns as soon as that tool executes, with no further model round-trip. The two
mechanisms together make `finish_iteration` the single exit from a research-agent
iteration — the loop's other exit is a tool-call-free assistant message, which forced
tool choice makes unreachable — so research-agent cannot stop early and leave the graph
without a research-review verdict. Phase
control lives in the research graph's edges (see the **research-execution**
capability), not in middleware over a single agent's control flow.

The MCP client SHALL NOT be cached across requests, the app SHALL NOT open a
long-lived SSE listening stream on the MCP endpoint, and the app SHALL NOT issue or
retain an `Mcp-Session-Id`. Tool-list freshness across requests is achieved by
re-polling `tools/list` at the start of every turn that constructs a client,
matching the generic-RAG server's `stateless_http=True` deployment; persistent-session
features (long-lived sessions, `Mcp-Session-Id`, `Last-Event-ID` resumability,
`notifications/tools/list_changed`, `notifications/resources/*`,
`notifications/prompts/list_changed`) are out of scope for this capability.

#### Scenario: research-agent invokes an MCP tool

- **WHEN** research-agent needs information from the knowledge base during an iteration
- **THEN** it SHALL emit a tool call, the MCP server SHALL execute the tool, and the result SHALL be incorporated into the accumulated research context

#### Scenario: research-agent is run only after plan approval

- **WHEN** a chat completion request is processed and no plan has been approved yet
- **THEN** the research-agent node SHALL NOT run and no MCP client SHALL be constructed for research; the turn SHALL produce only preparation output

#### Scenario: Per-request agent and MCP scoping

- **WHEN** the MCP server's tool list changes between two requests that reach research (e.g. the generic-RAG MCP server is redeployed)
- **THEN** the later research run SHALL discover and use the new tool list without restarting the dial-deep-research process

#### Scenario: No session reuse across requests

- **WHEN** the app processes two requests that each construct an MCP client
- **THEN** the app SHALL construct a new MCP client for the second rather than reusing the first's, the second's MCP traffic SHALL NOT carry an `Mcp-Session-Id` derived from the first, and any in-flight notifications received during the first request's POST SSE response SHALL have terminated with that request

### Requirement: Tool messages persisted via DIAL custom_content state

For every chat completion request, the app SHALL accumulate the ordered sequence of
`AIMessage`, `ToolMessage`, and injected `HumanMessage` instances observed during
the turn — for a research turn this is the research graph's slice: every research-agent
`AIMessage` carrying `tool_calls`, every `ToolMessage` returned by a tool, every
next-iteration plan `HumanMessage` injected by the research-review node, and the final
report `AIMessage` — and SHALL persist that sequence by serializing it via
`langchain_core.messages.messages_to_dict` and writing it under
`assistant.custom_content.state` (the `messages` field of the unified `DialState`).
The injected next-iteration plan `HumanMessage`s SHALL be captured in run order so
the persisted slice interleaves them at the positions research-agent saw them; they
SHALL NOT be appended to the user-visible assistant `content`. Before serialization,
the app SHALL traverse every message's `content` and, for every LangChain v1
`ImageContentBlock` carrying a `base64` field, replace the inline data with a `url`
reference per the **Tool-message image content uploaded to DIAL files before
persistence** requirement, so the persisted state SHALL NOT contain image byte
payloads. The DIAL `assistant.tool_calls` / `assistant.tool_call_id` native fields
SHALL NOT be populated by the app; the `custom_content.state["messages"]` blob is the
sole authoritative carrier of tool-call structure across turns.

The **final report** `AIMessage` SHALL be persisted into this slice too — not just
the intermediate tool-call messages — because the native `assistant.content` field
is a display-only concatenation of streamed text and carries no boundaries from
which the original message structure could be recovered.

#### Scenario: Research turn slice is fully persisted

- **WHEN** a research turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[finish_iteration]) → ToolMessage(finish_iteration) → [injected next-plan HumanMessage] → … → AIMessage(report)`
- **THEN** `custom_content.state["messages"]` SHALL carry those entries in run order, each encoded with its matching `messages_to_dict` `type` discriminator, the injected next-plan `HumanMessage` appearing at the position research-agent saw it, and the report `AIMessage` last

#### Scenario: Multimodal tool loop persists with image URLs, not image bytes

- **WHEN** a research turn produces a `ToolMessage` whose `content` includes one or more `{type: "image", base64, mime_type}` blocks
- **THEN** the persisted entry for that `ToolMessage` SHALL contain the same blocks rewritten to `{type: "image", url, mime_type}` (with `base64` absent), and the serialized state blob SHALL NOT include the original image byte payload
