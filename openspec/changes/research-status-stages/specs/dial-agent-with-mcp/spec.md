## MODIFIED Requirements

### Requirement: Tool execution surfaced as timed DIAL stages
For every tool the agent invokes during a request, the app SHALL emit a single DIAL "result" stage carrying both the input arguments and the tool's output. The one exception is `update_status`, which carries no result and SHALL produce no result stage — it is surfaced as the activity stage described in **Research progress surfaced as one open activity stage**, and the app SHALL NOT render its arguments or its acknowledgement anywhere in the stage channel. Titles follow the normalized form `[TOOL] <tool_name> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where emoji ∈ `{✅, ❌}` marks success and failure. The mark carries the outcome on its own, so the title SHALL NOT spend width on a word for it. Stage timestamps SHALL bracket the actual execution window (start when the call is dispatched to the MCP server, end when the result is received). When the tool returns an error (caught by `handle_tool_error` instead of bubbling), the stage SHALL be marked ❌ so the failure stands out in the chat UI. Stage content is rendered as markdown by DIAL, so both the input arguments and the tool output SHALL be wrapped in fenced code blocks (single newlines would otherwise collapse), making multi-line payloads — JSON args, plain-text results, error tracebacks — readable verbatim.

#### Scenario: Tool result stage carries start, end, elapsed, input, and output
- **WHEN** the tool result returns from the MCP server
- **THEN** the app SHALL emit a stage whose title includes the start timestamp, end timestamp, and elapsed seconds, and whose body contains an "Input" section with the JSON-fenced arguments followed by an "Output" section with the fenced tool result content

#### Scenario: Tool error stage signals failure but does not abort the turn
- **WHEN** an MCP tool raises (e.g. argument validation rejects the LLM's call) and the error is caught by the per-tool error handler
- **THEN** the app SHALL emit a stage whose title is marked ❌ (e.g. `[TOOL] <tool_name> ❌ (...)`), whose body carries the JSON-fenced "Input" section followed by a fenced "Error" section with the error text; the agent SHALL receive the same error text as a `ToolMessage` in its next step and MAY retry with corrected arguments without the chat completion failing

#### Scenario: The status tool produces no result stage
- **WHEN** research-agent calls `update_status` beside a research tool in one assistant message
- **THEN** the app SHALL emit a result stage for the research tool only, and the run's stage channel SHALL contain no `[TOOL] update_status` stage and no rendering of the status argument as stage content

### Requirement: Opik tracing of agent runs when configured

The app SHALL attach an `opik.integrations.langchain.OpikTracer` callback to the per-request LangChain agent's streaming invocation **iff** Opik tracing is enabled via configuration (`Settings.opik_tracing_enabled` is true). When attached, the tracer SHALL capture the full hierarchical trace of the turn — the agent graph run, the underlying LLM call, and every MCP tool call (including arguments, results, and errors) — without altering the agent's outputs, the DIAL stages emitted, the assistant message content, or the way turn-aborting failures are delivered. When Opik tracing is not enabled, the agent SHALL run with no Opik callback attached and SHALL produce identical observable behaviour to a build that does not depend on Opik.

#### Scenario: Tracer attached when enabled
- **WHEN** `OPIK_TRACING_ENABLED=true` is set and the local Opik stack (started via `make opik-up`) is reachable, and a chat completion request is processed
- **THEN** the agent's streaming invocation SHALL be configured with an `OpikTracer` callback, and the resulting trace in Opik SHALL contain the agent run, the LLM call, and a span per MCP tool invocation with their inputs, outputs, and timings

#### Scenario: Tracer absent when disabled
- **WHEN** `OPIK_TRACING_ENABLED` is unset or false and a chat completion request is processed
- **THEN** no `OpikTracer` SHALL be constructed or attached, no Opik network calls SHALL be made by the app, and the chat completion SHALL produce the same DIAL stages and assistant content as a run with the Opik dependency absent

#### Scenario: Tracing failure does not break the turn
- **WHEN** Opik tracing is enabled but the configured Opik instance is unreachable mid-turn
- **THEN** the chat completion SHALL still complete successfully (the agent SHALL produce its assistant text and tool stages as usual), with any tracer-side exception swallowed by LangChain's callback machinery — i.e. tracing failures SHALL NOT abort the turn: they SHALL never produce an error response and SHALL never replace successful assistant content with a delivered error

#### Scenario: Tool error is captured as a tool span
- **WHEN** Opik tracing is enabled and an MCP tool raises an error during a turn (caught by `handle_tool_error`)
- **THEN** the corresponding tool call SHALL appear in the Opik trace as a span carrying the tool arguments and the error text, while the existing DIAL stage marked ❌ and agent retry behaviour SHALL be unchanged

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
content: its call is not streamed, and a completed draft reaches the choice only once the review
loop settles. The app SHALL NOT append the
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
turn SHALL NOT trigger this path: per-tool errors caught by `handle_tool_error` (surfaced as a stage
marked ❌), a failed report-review call and a failed report revision once a draft exists (both
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

## ADDED Requirements

### Requirement: Research progress surfaced as one open activity stage

While the research graph runs, the app SHALL keep exactly one DIAL stage open at all times, whose title names what research is doing at that moment. The app SHALL open the first such stage before the graph starts, and SHALL replace it — closing the open one, then opening a new one — each time research-agent announces a step through `update_status` and each time research-review, report or report-review is entered. Replacement SHALL be the only way the title changes, since a DIAL stage name can be appended to but never rewritten.

The activity stage SHALL carry a title only: no stage content, no bracketed prefix of the kind result stages use, and no elapsed time or timestamps. A closing activity stage means a new step has started, not that the closed step finished — work announced earlier may still be running — so the app SHALL NOT stamp it with any duration, and SHALL NOT open and close an activity stage at the same instant, which would render as a completed step.

One assistant message SHALL change the activity stage at most once. When a message carries several `update_status` calls, the app SHALL join their texts into one title and open a single stage. When a message calls `update_status` together with `finish_iteration`, the app SHALL leave the activity stage untouched.

The app SHALL close the open activity stage before the turn ends, on both the success and the failure path, using the failed status when the run is ending in an error. No activity stage SHALL be left open when the response completes.

#### Scenario: A status announcement replaces the open stage

- **WHEN** research-agent calls `update_status` while an activity stage is open
- **THEN** the app SHALL close the open stage and open a new one titled with the announced status, so exactly one activity stage is open before and after

#### Scenario: An activity stage stays open across the tool calls it covers

- **WHEN** research-agent announces a step and then runs several research tools
- **THEN** the activity stage SHALL remain open while those tools run and their result stages are emitted, and SHALL close only when the next announcement or node entry replaces it

#### Scenario: Several announcements in one message yield one stage

- **WHEN** one assistant message carries more than one `update_status` call and no `finish_iteration`
- **THEN** the app SHALL open exactly one activity stage whose title carries every announced status, and no activity stage SHALL be opened and closed at the same instant

#### Scenario: An announcement ending the iteration is ignored

- **WHEN** one assistant message carries both `update_status` and `finish_iteration`
- **THEN** the app SHALL neither close the open activity stage nor open a new one

#### Scenario: A node entry replaces the open stage

- **WHEN** research-review, report or report-review begins
- **THEN** the app SHALL replace the open activity stage with one naming that node's work, so no LLM call in the research graph runs without a stage describing it

#### Scenario: The activity stage carries no timing and no body

- **WHEN** an activity stage is closed
- **THEN** its title SHALL be unchanged from when it was opened, carrying no elapsed time, start time or end time, and the stage SHALL have received no content

#### Scenario: A failing run closes the open stage

- **WHEN** the research graph raises and the turn is delivered as a DIAL error
- **THEN** the app SHALL close the open activity stage with the failed status before the error is raised, and SHALL NOT leave a stage whose status is still unset
