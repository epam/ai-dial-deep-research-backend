## REMOVED Requirements

### Requirement: Tool messages persisted via DIAL custom_content state
**Reason**: This change drops scenarios of this requirement that describe behavior it removes,
and a modified requirement cannot drop a scenario. The requirement is therefore removed and added
again under a new title.
**Migration**: See "Each graph's messages persisted in its own part of the DIAL state" under ADDED Requirements in this delta.

### Requirement: Reconstruction of LangChain history from DIAL request
**Reason**: This change drops scenarios of this requirement that describe behavior it removes,
and a modified requirement cannot drop a scenario. The requirement is therefore removed and added
again under a new title.
**Migration**: See "Reconstruction of the preparation agent's history from DIAL request" under ADDED Requirements in this delta.

### Requirement: Tool-message image content uploaded to DIAL files before persistence
**Reason**: This change drops scenarios of this requirement that describe behavior it removes,
and a modified requirement cannot drop a scenario. The requirement is therefore removed and added
again under a new title.
**Migration**: See "Snapshot image content uploaded to DIAL files before persistence" under ADDED Requirements in this delta.

## MODIFIED Requirements

### Requirement: Assistant message content contains only model text
The DIAL response message content SHALL, in chronological order, contain only the
natural-language assistant text that each component is specified below to forward — never tool
calls, tool results, or structured non-text content blocks (e.g. Anthropic-style `thinking`
blocks, image blocks); those are conveyed via stages (for tool execution UI display) and via
the turn's persisted state (for observability, and for cross-turn replay of the preparation
agent's messages). Coverage differs by
component: preparation forwards its own text, while the research graph forwards none of
research-agent's, research-review's, or report-review's text — only the settled report — as the
next paragraph specifies.

**Preparation and research populate this content by entirely different means.** Preparation
streams its own `AIMessage` text token-by-token as the model produces it, including text on an
intermediate `AIMessage` that also carries `tool_calls` — not just the final text-only
`AIMessage` — and each of its tool calls becomes a DIAL stage alongside that streamed text. The
research graph SHALL NOT stream, or otherwise forward, any `AIMessage`'s text into
`message.content`: research-agent's own reasoning is discarded, whatever text accompanies its
tool calls, and its tool calls become DIAL stages only, as does each report review (see
**report-composition**). The research graph's sole contribution to `message.content` is the one
report the review loop settles on, appended once the loop ends (see **Streaming response path**
for the append-once cadence) — never streamed, and no other text of its own.

Text streamed from **distinct assistant messages** SHALL be separated by a `"\n\n"` in
`message.content`, so the segments render as separate paragraphs rather than running together;
the tokens of one message SHALL be concatenated untouched. The boundary is the message, not the
tool round: two segments SHALL be separated whether or not a tool ran between them — including
the same model call re-streamed after a transient failure, whose already-streamed fragment cannot
be retracted. The first segment of a turn SHALL take no leading separator. A streamed chunk
carries the id of the message it belongs to (the provider's response id, or one langchain_core
stamps per LLM run), which is what makes the boundary observable.

#### Scenario: Preparation's tool-using turn streams intermediate text alongside the final answer
- **WHEN** the preparation agent produces an intermediate `AIMessage` carrying both
  natural-language text (e.g. `"Plan: ..."`) and `tool_calls`, the tool call returns a result,
  and the agent then produces a final `AIMessage` with the answer
- **THEN** the DIAL response `message.content` SHALL contain the intermediate text followed by
  the final text, in that order, with a `"\n\n"` separator between them; tool stages SHALL still
  render between the two segments via the stage channel; the response content SHALL NOT contain
  serialized tool calls, tool result payloads, or `messages_to_dict` blobs

#### Scenario: Preparation's text-only turn (no tool calls)
- **WHEN** the preparation agent answers without invoking any tool, producing a single
  text-only final `AIMessage`
- **THEN** the DIAL response `message.content` SHALL equal that message's text, with no leading
  or trailing separator, streamed token-by-token

#### Scenario: Research-agent's tool-calling text never reaches content
- **WHEN** research-agent produces an `AIMessage` carrying both natural-language text and
  `tool_calls`
- **THEN** the tool call SHALL become a DIAL stage as usual, and the message's text SHALL NOT
  appear in `message.content` at any point in the turn — not streamed, not appended later

#### Scenario: A research turn's content is the report alone
- **WHEN** a turn hands off to research and the review loop settles on a report
- **THEN** `message.content` SHALL gain exactly one addition from the research phase — that
  report, appended once — and no text from research-agent, research-review, or report-review
  SHALL appear in it at any point

#### Scenario: Structured content blocks flattened to text
- **WHEN** an `AIMessageChunk` carries `content` as a list of content blocks (e.g. `[{type: "text", text: "..."}, {type: "thinking", thinking: "..."}, {type: "image", ...}]`) instead of a bare string
- **THEN** the app SHALL append the concatenation of every `text`-typed block's `text` payload to `choice` and SHALL silently skip every non-text block (no append, no error, no stage)

#### Scenario: Cross-turn replay of tool messages
- **WHEN** a follow-up chat completion request arrives after an earlier turn in which the preparation agent called tools
- **THEN** the second turn's preparation agent SHALL receive the prior turn's preparation agent `AIMessage(tool_calls=…, content=…)` and `ToolMessage(...)` messages plus its final `AIMessage` as conversation history, reconstructed from the prior assistant message's `preparation.agent_messages` field, in the original order, instead of being limited to prior assistant text

#### Scenario: A new assistant message starts a new paragraph with no tool round between
- **WHEN** two text segments from distinct assistant messages reach the choice with no tool result between them
- **THEN** the app SHALL still insert a `"\n\n"` between them, because the boundary is the change of message

#### Scenario: Tokens of one message are not separated
- **WHEN** one assistant message streams as many chunks
- **THEN** the app SHALL append them with nothing inserted between, producing one paragraph

### Requirement: Failures delivered as DIAL protocol errors

The app SHALL resolve every turn-aborting failure to an accurate, user-safe message and deliver it
through the **DIAL error protocol**, never as fake-success HTTP 200 assistant content. This applies
whether an exception reaches the top-level handler or a known turn-aborting condition holds (a turn
"cannot produce its intended answer").

**Cause resolution.** The app SHALL normalize the failure into a common view (HTTP status, error
`code`, error `type`, internal message, and user-safe `display_message`) extracted best-effort
from the supported exception shapes (`openai` LLM errors, `aidial_sdk.exceptions.HTTPException`,
raw `httpx` errors); normalization SHALL be total — a malformed or absent error body yields an
empty view, never a second exception. A failure a concurrency runtime has wrapped SHALL be resolved
to the failure the wrapper holds before **any** of this resolution runs, per **A failure wrapped
by a concurrency runtime is unwrapped before classification** in the **tool-call-fault-tolerance**
capability. The unwrapped failure SHALL be what every step below sees, not only the extraction of
the common view: the precedence rules that follow test the failure's own type as well as the
extracted status, so unwrapping for extraction alone would still leave them matching a wrapper and
still reach the generic fallback as if the cause were unknown. The app SHALL then choose the
user-facing message by a fixed precedence, most-specific first:

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
5. curated messages for known internal conditions (research step-budget exhaustion; the
   turn-aborting app conditions below);
6. a generic fallback.

Each resolution SHALL be classified retryable or not; the app SHALL append a single "try again
later" sentence only to retryable resolutions, and SHALL NOT append it to a `display_message`
resolution or to any non-retryable resolution. User-facing text
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
error as ordinary assistant `content`. A turn that aborts SHALL persist a state that records the
failure, and only then raise the error (**research-resume**): with its snapshot when its research
run saved one, otherwise only the failure flag and the `CrossTurnPrepState` the turn started from. A
failure while the application properties are fetched or validated, and the refusal of a
conversation whose report was delivered, SHALL persist no state. A turn does not abort at all once
its report is written (**research-resume**). On a streaming request the SDK sends a state set
before the raise ahead of the error chunk, so the client keeps it with the failed answer. On a
non-streaming request the SDK raises on the error chunk and drops the merged response, state
included, so such a turn carries no state at all. The state never carries the error text.

**Outgoing-status policy.** The app SHALL NOT emit a status DIAL Core's balancer treats as
retriable (429, 502, 503, 504). A client-attributable status (one of 400, 401, 403, 404, 409, 413,
422) SHALL pass through; every other cause — upstream rate limits and outages, stream failures,
timeouts, unknown internal errors — SHALL be emitted as 500. The true cause SHALL be preserved in
`code`, so a 500 MAY carry `code: "429"`; consumers classify by `code`, not `status_code`.

**Turn-aborting app conditions.** The two outcomes that previously rendered as friendly assistant
content SHALL instead be delivered as protocol errors: an application whose properties cannot be
**validated** (unconfigured) SHALL resolve to a non-retryable "not configured — contact your
administrator" message (outgoing 500), and a conversation whose research has already been handed
off SHALL resolve to a non-retryable "start a new conversation" message (outgoing 409). Research
counts as handed off once its report was delivered: a failed research turn persists the
research-started flag reset, so a conversation whose research failed is not refused. A failure
to **fetch** the properties from DIAL Core (as opposed to validate them) SHALL propagate to the
top-level handler and resolve through the status/type map to a service message, rather than being
reported as "not configured".

Three more turn-aborting app conditions stop a resume (**research-resume**). A resumable snapshot
whose plan id matches but whose format version this code does not read SHALL resolve to a
non-retryable message saying the research was saved by a different version of Deep Research and
cannot be resumed, so the user should start a new conversation (outgoing 409). A resumable snapshot
whose plan id matches but which cannot be read for any other reason SHALL resolve to a
non-retryable message saying an error on our side prevents resuming the research, so the user
should start a new conversation (outgoing 500). A snapshot image whose download answers 404 is not
a refusal: the snapshot is discarded and research starts fresh. A snapshot image that still cannot be downloaded after its attempts,
for another reason, SHALL resolve to a retryable message saying the saved research progress could
not be loaded (outgoing 500, "try again later" appended).

**Absorbed failures are unaffected.** Failures that are deliberately swallowed and never abort the
turn SHALL NOT trigger this path: a failing tool call, which the **tool-call-fault-tolerance**
capability retries where that helps and otherwise delivers to the agent as an error result
(surfaced as a stage marked ❌), a failed report-review call and a failed report revision once a
draft exists (both absorbed by the report loop, which delivers a draft instead), Opik-tracing
failures, and every failure after the report loop has settled a draft (**research-resume**). These continue to let the turn complete
normally. A snapshot image that cannot be downloaded for a reason other than a 404 is not one of
them: it fails the turn (**research-resume**).

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

#### Scenario: A wrapped failure resolves to its real cause
- **WHEN** a turn-aborting failure reaches the top-level handler wrapped in a concurrency runtime's
  container — for example an HTTP 502 raised inside a task group
- **THEN** the app SHALL resolve it to the message and retryable classification of the 502 (the
  retryable service internal-error message), and SHALL NOT resolve it to the generic non-retryable
  fallback on the grounds that the wrapper matches no supported exception shape

#### Scenario: Context-length and content-filter causes get actionable text
- **WHEN** the model rejects the request with `code: "context_length_exceeded"` or
  `code: "content_filter"`
- **THEN** the code map SHALL resolve it, ahead of the status ladder and classified non-retryable,
  to a message that states what happened (the AI model's context window was exceeded / the content
  policy blocked the request) and that holds whether the call came from preparation or from
  research, so it SHALL NOT tell the user to shorten their own messages

#### Scenario: A rejected request and an exhausted step budget say what happened
- **WHEN** the model rejects a call with HTTP 400, 413 or 422, or research exhausts its step budget
- **THEN** the message SHALL state what happened and SHALL hold whether the call came from
  preparation or from research
- **AND** it SHALL drop the advice that does not fit a research call: "reduce the size of your
  message or attachments" for a 413, "contact your administrator" for a 400 or 422, and "start a
  new conversation" for the step budget, because a request to continue in the same conversation
  starts the research again from the beginning (**research-resume**)
- **AND** the code-map messages SHALL likewise drop "shorten your messages" for a context overflow
  and "rephrase your message" for a content filter

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
- **THEN** the app SHALL NOT write the error text into assistant `content` or into any persisted
  state, so a subsequent turn (e.g. after DIAL Chat regenerates) does not replay the error text to
  the model
- **AND** a turn whose research run saved a snapshot SHALL persist only its preparation agent
  messages and reviews, its reset `CrossTurnPrepState`, its snapshot and the failure flag; a failure while
  the application properties are fetched or validated, and the refusal of a conversation whose
  report was delivered, SHALL persist no state; any other failed turn SHALL persist only the
  `CrossTurnPrepState` it started from and the failure flag; and a later turn learns of the failure from
  the fixed failed-turn note alone

#### Scenario: A failed research turn persists its state ahead of the error
- **WHEN** research-agent fails with a quota error on a streaming request
- **THEN** the turn SHALL send its state, snapshot included, and only then the in-stream
  `{"error": ...}` chunk with DIAL Core's `display_message` and the error reference

#### Scenario: A snapshot saved by a different version is refused
- **WHEN** research starts with a matching resumable snapshot whose format version this code does not read
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 409) whose text says
  the research was saved by a different version and cannot be resumed and asks the user to start a
  new conversation, plus an error reference, and SHALL persist only the turn's failure record, with
  no snapshot

#### Scenario: A snapshot image that cannot be downloaded right now
- **WHEN** a resumed run cannot download a snapshot image, and no attempt answered 404
- **THEN** the app SHALL deliver a retryable protocol error (outgoing HTTP 500) whose text says the
  saved research progress could not be loaded, followed by the "try again later" sentence and an
  error reference, and SHALL persist only the turn's failure record, so the snapshot the turn
  started from stays the latest one

#### Scenario: A snapshot that cannot be read is refused as our error
- **WHEN** research starts with a matching resumable snapshot of a known version that fails to read
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 500) whose text says
  an error on our side prevents resuming the research and asks the user to start a new
  conversation, plus an error reference, SHALL write the stack trace to the turn's error record,
  and SHALL persist only the turn's failure record, with no snapshot

#### Scenario: Unconfigured application delivered as a protocol error
- **WHEN** a request's DIAL application properties cannot be validated
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 500) whose text is
  the "not configured — contact your administrator" message plus an error reference, and SHALL NOT
  run any agent or append the message as assistant content

#### Scenario: Research-already-handed-off delivered as a protocol error
- **WHEN** a request arrives on a conversation whose research delivered its report on an earlier
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

### Requirement: Each graph's messages persisted in its own part of the DIAL state

For every chat completion request, the app SHALL accumulate the messages each graph produced
during the turn and SHALL persist them under `assistant.custom_content.state`, serialized via
`langchain_core.messages.messages_to_dict`, in two places that are never mixed:

- **The preparation agent's messages** go to `preparation.agent_messages`: every `AIMessage` the
  preparation agent produced in this turn, with or without `tool_calls`, and every `ToolMessage`
  returned by its tools, in run order.
- **The research graph's messages** go to the research record under `research`
  (**research-resume**), as `research_agent_messages`: the first research instruction, every
  research-agent `AIMessage` and `ToolMessage`, and every next-iteration plan `HumanMessage` that
  research-review injected, in run order, at the positions research-agent saw them. The injected
  next-iteration plan `HumanMessage`s SHALL NOT be appended to the user-visible assistant `content`.
  No report message is added: the delivered report is the assistant `content` alone
  (**report-citations**), and the record's drafts hold the writer's outputs.

The DIAL `assistant.tool_calls` / `assistant.tool_call_id` native fields SHALL NOT be populated by
the app; `preparation.agent_messages` is the sole carrier of the preparation agent's tool-call
structure across turns. Research-agent's messages are never replayed to a later turn
(**Reconstruction of the preparation agent's history from DIAL request**).

No persisted state SHALL contain image bytes. The preparation agent has no MCP tools, so its
messages carry no images. A research record's images are uploaded to DIAL files when the run failed
and replaced by placeholders when it completed (**Snapshot image content uploaded to DIAL files before persistence**).

When a turn's state cannot be built or encoded, the turn saves the state that **research-resume**
("A turn's one state write falls back in a fixed order") names instead: after a written report, a
closing state with no agent messages and no research record.

#### Scenario: Research turn slice is persisted in the research record

- **WHEN** a research turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[finish_iteration]) → ToolMessage(finish_iteration) → [injected next-plan HumanMessage] → …` and then delivers its report
- **THEN** the research record's `research_agent_messages` SHALL carry those entries in run order, each encoded with its matching `messages_to_dict` `type` discriminator, the injected next-plan `HumanMessage` appearing at the position research-agent saw it, and the record SHALL hold no report `AIMessage`

#### Scenario: Preparation's messages are persisted apart

- **WHEN** a turn's preparation agent calls `update_query` and `update_plan` and then answers
- **THEN** `preparation.agent_messages` SHALL carry the agent's `AIMessage`s and `ToolMessage`s in run order, and SHALL hold no research-agent message

#### Scenario: A failed research turn keeps its research slice in the snapshot

- **WHEN** research-agent fails with a quota error after several tool calls
- **THEN** the turn's `preparation.agent_messages` SHALL carry only the preparation agent's messages, and research-agent's messages SHALL be in the snapshot under `research`

### Requirement: Reconstruction of the preparation agent's history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the preparation agent's
LangChain message history (`reconstruct_prep_agent_history`) by walking `request.messages` in order
and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["preparation"]["agent_messages"]` is present and non-empty, emitting `messages_from_dict(...)` of it instead of consulting the native `content` or `tool_calls` fields;
- otherwise — no state, a state without `preparation.agent_messages`, such as one saved before the two graphs' messages were kept apart, or a state that fails validation — emitting a single `AIMessage(content=msg.content)` as a fallback, so such conversations continue to work without a migration step.

This asymmetry — user turns read from native `content`, assistant turns read from the persisted
agent messages — exists because the assistant's native `content` is a display-only concatenation of
every streamed text segment (see **Assistant message content contains only model text**) and
cannot be decomposed back into the `AIMessage` / `ToolMessage` / `tool_call` interleaving the agent
needs. User turns carry no such structure, so their flat native `content` is sufficient.

The history SHALL be built from the preparation agent's messages only. It SHALL read nothing of a
research record, and nothing of an older state's `messages` field: research-agent's messages, the
report drafts and their images never enter it. The history SHALL contain no image, so
reconstruction downloads no file.

The system message provided by the DIAL request SHALL continue to be ignored on reconstruction; the
app's own system prompt is supplied to `create_agent` directly.

An assistant message whose `custom_content.state` carries the failure flag — one written by a failed
turn — SHALL be reconstructed like any other: from its agent messages when they are non-empty,
otherwise from its native `content`. It SHALL be followed in the history by one fixed failed-turn
note as a `SystemMessage` (**research-resume**). These notes are the only system messages the
reconstructed history contains.

#### Scenario: Assistant turn with state replays the preparation agent's messages
- **WHEN** a request includes an assistant message whose `preparation.agent_messages` carries the encoded sequence `[ai(tool_calls=[X]), tool(X_result), ai(content="final")]`
- **THEN** the reconstructed LangChain history at that position SHALL contain exactly those three messages decoded via `messages_from_dict`, in order, and SHALL NOT contain any `AIMessage` derived from the DIAL message's native `content` or `tool_calls` fields

#### Scenario: Legacy assistant turn falls back to native content
- **WHEN** a request includes an assistant message with no `custom_content.state` field set, or with `preparation.agent_messages` missing or empty
- **THEN** the reconstructed history at that position SHALL contain a single `AIMessage` whose content equals the DIAL message's native `content` field, and the agent SHALL run successfully without error

#### Scenario: A state saved before the split is read as a turn without state
- **WHEN** a request includes an assistant message whose state carries a `messages` field and no `preparation.agent_messages`
- **THEN** the reconstructed history at that position SHALL contain a single `AIMessage` with the native `content`, and nothing of the `messages` field

#### Scenario: Mixed legacy and new turns in one conversation
- **WHEN** a request's history alternates legacy assistant turns (no state) with new assistant turns (state populated)
- **THEN** the reconstructed history SHALL mix degraded `AIMessage(content=str)` entries (for legacy turns) with `messages_from_dict(...)`-decoded agent messages (for new turns), in the original turn order, without raising

#### Scenario: A research turn contributes only its preparation messages
- **WHEN** a request includes an assistant message written by a research turn, whose research record holds research-agent messages with page images
- **THEN** the reconstructed history at that position SHALL contain only that turn's preparation agent messages, with no image and no research-agent message, and no file SHALL be downloaded

#### Scenario: A failed research turn is followed by the failed-turn note
- **WHEN** a request includes an assistant message whose state carries preparation agent messages, a snapshot and the failure flag, followed by a user message
- **THEN** the reconstructed history at that position SHALL contain the decoded preparation agent messages, then the failed-turn note as a `SystemMessage`, then the user's `HumanMessage`, and SHALL contain nothing of the snapshot

#### Scenario: A failed turn without a snapshot is followed by the failed-turn note
- **WHEN** a request includes an assistant message whose state carries the failure flag and no preparation agent messages, followed by a user message
- **THEN** the reconstructed history at that position SHALL contain a single `AIMessage` with the message's native `content`, then the failed-turn note as a `SystemMessage`, then the user's `HumanMessage`

### Requirement: Snapshot image content uploaded to DIAL files before persistence

Before calling `choice.set_state(...)` for a failed research turn's snapshot, the app SHALL upload
every LangChain v1 `ImageContentBlock` carrying a `base64` field in the snapshot's research-agent
messages to the DIAL files API, and replace the block's `base64` field with a `url` field pointing
at the resulting file object. The upload SHALL use the `aidial-client` `AsyncDial` interface. The
target bucket SHALL be resolved per turn from `AsyncDial.bucket.get_raw()`, preferring the `appdata`
value and falling back to `bucket` when `appdata` is unset. The target path SHALL include a fixed
`dial-deep-research/` prefix to namespace the app within a shared bucket. The block's `mime_type`
field SHALL be preserved unchanged; the block's `type: "image"` discriminator SHALL remain
`"image"` (no custom block type). The uploads of one save SHALL run concurrently. **research-resume**
owns the retries, what an upload that still fails does to the snapshot, and the placeholder format.

A completed research run's record SHALL upload nothing: each of its image blocks is replaced by a
placeholder (**research-resume**). No other state carries images.

#### Scenario: Image block in a ToolMessage is uploaded and rewritten
- **WHEN** an MCP tool returned a `ToolMessage` whose `content` includes `{type: "image", base64: "<...>", mime_type: "image/png"}`, and the research run then fails and its snapshot is about to be written
- **THEN** the app SHALL upload the decoded bytes to `files/{appdata-or-bucket}/dial-deep-research/<deterministic-name>.png` via `AsyncDial.files.upload`, replace the block in the snapshot's research-agent messages with `{type: "image", url: "<returned url>", mime_type: "image/png"}` (no `base64` field), and only then proceed with `messages_to_dict` and `set_state`

#### Scenario: Multiple image blocks in a single ToolMessage are all uploaded
- **WHEN** a snapshot's `ToolMessage` contains two or more image blocks
- **THEN** each image block SHALL be uploaded as a distinct file, each block SHALL be rewritten to its own `url` form, and the order of blocks within `content` SHALL be preserved

#### Scenario: Non-image content blocks pass through unchanged
- **WHEN** a `ToolMessage` carries a mix of `{type: "text", ...}` and `{type: "image", base64, ...}` blocks
- **THEN** only the image blocks SHALL be uploaded and rewritten, or replaced by placeholders; text blocks SHALL be left bit-for-bit unchanged in the persisted state

#### Scenario: Image block in an AIMessage is handled by the same path
- **WHEN** a model emits an `AIMessage` whose `content` contains an `{type: "image", base64, mime_type}` block (e.g. a vision-capable model that returns image output)
- **THEN** that block SHALL be uploaded or replaced by the same walker that handles `ToolMessage` images, with no separate code path

#### Scenario: Upload failure is fail-closed
- **WHEN** the DIAL files upload for a snapshot image still fails after its attempts
- **THEN** the offending block SHALL be replaced in place by its placeholder, the failure SHALL be logged server-side, the snapshot SHALL be marked not resumable (**research-resume**), and `set_state` SHALL proceed with the rewritten slice — never with inline `base64` left in place

#### Scenario: A completed run makes no files call
- **WHEN** a research run that fetched page images delivers its report
- **THEN** the app SHALL neither resolve the files bucket nor upload any file for that turn, and every image block of its record SHALL be a placeholder

#### Scenario: Persisted state stays below the DIAL request-body limit on multimodal turns
- **WHEN** a turn produces one or more tool messages carrying image content totalling several MB of base64 in aggregate
- **THEN** the serialized state produced for that turn SHALL contain no `base64` fields: URL references in a snapshot, placeholders in a completed run's record. Every later request carries the states of all earlier turns, and DIAL Core rejects a request above its size limit (64 MiB by default) with 413, so image bytes left in a state would bring the conversation closer to a request that can no longer be sent
