## MODIFIED Requirements

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

A research turn that **fails** after its graph streamed state writes its research
slice elsewhere. Its `messages` field SHALL carry only the turn's preparation
messages, and the research slice SHALL be written into the turn's snapshot instead,
with its images uploaded the same way (**research-resume**). Any other failed turn
persists an empty `messages`. History reconstruction never reads the snapshot, so a
failed run's research transcript never reaches a later turn's preparation agent.

#### Scenario: Research turn slice is fully persisted

- **WHEN** a research turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[finish_iteration]) → ToolMessage(finish_iteration) → [injected next-plan HumanMessage] → … → AIMessage(report)`
- **THEN** `custom_content.state["messages"]` SHALL carry those entries in run order, each encoded with its matching `messages_to_dict` `type` discriminator, the injected next-plan `HumanMessage` appearing at the position research-agent saw it, and the report `AIMessage` last

#### Scenario: Multimodal tool loop persists with image URLs, not image bytes

- **WHEN** a research turn produces a `ToolMessage` whose `content` includes one or more `{type: "image", base64, mime_type}` blocks
- **THEN** the persisted entry for that `ToolMessage` SHALL contain the same blocks rewritten to `{type: "image", url, mime_type}` (with `base64` absent), and the serialized state blob SHALL NOT include the original image byte payload

#### Scenario: A failed research turn keeps its research slice in the snapshot

- **WHEN** research-agent fails with a quota error after several tool calls
- **THEN** the turn's `custom_content.state["messages"]` SHALL carry only the turn's preparation messages, and the research-agent messages SHALL be in the turn's snapshot

### Requirement: Reconstruction of LangChain history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the LangChain message history fed to the agent by walking `request.messages` in order and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["messages"]` is present and non-empty, emitting `messages_from_dict(custom_content.state["messages"])` (the full intermediate-plus-final slice) instead of consulting the native `content` or `tool_calls` fields, then traversing the reconstructed messages and re-inlining every LangChain v1 `ImageContentBlock` carrying a `url` (and no `base64`) by downloading the file from DIAL and replacing the block with the same `ImageContentBlock` populated with `base64` and `mime_type` (so the rehydrated block satisfies the in-flight contract from `multimodal-tool-output`);
- if `role == assistant` AND `custom_content.state["messages"]` is absent (legacy turn produced before this change), emitting a single `AIMessage(content=msg.content)` as a fallback so legacy conversations continue to work without a migration step.

This asymmetry — user turns read from native `content`, assistant turns read from `custom_content.state["messages"]` — exists because the assistant's native `content` is a display-only concatenation of every streamed text segment (intermediate reasoning plus `"\n\n"` separators plus the final answer; see **Assistant message content contains only model text**) and cannot be decomposed back into the `AIMessage` / `ToolMessage` / `tool_call` interleaving the agent needs. The persisted state slice — which includes the final `AIMessage`, per **Tool messages persisted via DIAL custom_content state** — is the only structurally faithful source for assistant turns, so the native assistant `content` and `tool_calls` fields SHALL NOT be consulted when a usable state slice is present. User turns carry no such structure, so their flat native `content` is sufficient.

The system message provided by the DIAL request SHALL continue to be ignored on reconstruction; the app's own system prompt is supplied to `create_agent` directly.

An assistant message whose `custom_content.state` carries the failure flag — one written by a failed turn — SHALL be reconstructed like any other: from its `messages` when they are non-empty, otherwise from its native `content`. It SHALL be followed in the history by one fixed failed-turn note as a `SystemMessage` (**research-resume**). These notes are the only system messages the reconstructed history contains. Reconstruction SHALL read nothing of a snapshot: its research transcript and images never enter the history, and an image of it that cannot be downloaded never costs the preparation agent anything.

#### Scenario: Assistant turn with state replays the full slice
- **WHEN** a request includes an assistant message whose `custom_content.state["messages"]` carries the encoded sequence `[ai(tool_calls=[X]), tool(X_result), ai(content="final")]`
- **THEN** the reconstructed LangChain history at that position SHALL contain exactly those three messages decoded via `messages_from_dict`, in order, and SHALL NOT contain any `AIMessage` derived from the DIAL message's native `content` or `tool_calls` fields

#### Scenario: Legacy assistant turn falls back to native content
- **WHEN** a request includes an assistant message with no `custom_content.state` field set, or with `state["messages"]` missing or empty
- **THEN** the reconstructed history at that position SHALL contain a single `AIMessage` whose content equals the DIAL message's native `content` field, and the agent SHALL run successfully without error

#### Scenario: Mixed legacy and new turns in one conversation
- **WHEN** a request's history alternates legacy assistant turns (no state) with new assistant turns (state populated)
- **THEN** the reconstructed history SHALL mix degraded `AIMessage(content=str)` entries (for legacy turns) with full `messages_from_dict(...)`-decoded slices (for new turns), in the original turn order, without raising

#### Scenario: Multimodal tool slice is rehydrated from URL to base64 before reaching the agent
- **WHEN** a request includes an assistant message whose `custom_content.state["messages"]` carries an encoded `ToolMessage` containing a `{type: "image", url, mime_type}` block (a previously uploaded image)
- **THEN** the reconstructed `ToolMessage` passed into the agent's input SHALL contain a `{type: "image", base64, mime_type}` block whose `base64` is the result of downloading the referenced DIAL file and whose `mime_type` is preserved unchanged; and the block SHALL NOT carry the `url` field

#### Scenario: Rehydration failure does not abort the turn
- **WHEN** a request includes an assistant message whose `custom_content.state["messages"]` references a DIAL file that cannot be downloaded (404, network error, or auth failure)
- **THEN** the reconstructed `ToolMessage` SHALL have the offending image block replaced by a `TextContentBlock` placeholder describing the loss, the failure SHALL be logged server-side, and the turn SHALL proceed normally rather than being delivered as a turn-aborting protocol error

#### Scenario: A failed research turn is followed by the failed-turn note
- **WHEN** a request includes an assistant message whose state carries preparation messages, a snapshot and the failure flag, followed by a user message
- **THEN** the reconstructed history at that position SHALL contain the decoded preparation messages, then the failed-turn note as a `SystemMessage`, then the user's `HumanMessage`, and SHALL contain nothing of the snapshot's transcript

#### Scenario: A failed turn without a snapshot is followed by the failed-turn note
- **WHEN** a request includes an assistant message whose state carries the failure flag and an empty `messages`, followed by a user message
- **THEN** the reconstructed history at that position SHALL contain a single `AIMessage` with the message's native `content`, then the failed-turn note as a `SystemMessage`, then the user's `HumanMessage`

### Requirement: Tool-message image content uploaded to DIAL files before persistence

Before calling `choice.set_state(...)` at the end of each turn, the app SHALL upload every LangChain v1 `ImageContentBlock` carrying a `base64` field — wherever it appears in the buffered `AIMessage` / `ToolMessage` slice, or in the research transcript of a failed research turn's snapshot — to the DIAL files API and replace the block's `base64` field with a `url` field pointing at the resulting file object. The upload SHALL use the `aidial-client` `AsyncDial` interface. The target bucket SHALL be resolved per turn from `AsyncDial.bucket.get_raw()`, preferring the `appdata` value and falling back to `bucket` when `appdata` is unset. The target path SHALL include a fixed `dial-deep-research/` prefix to namespace the app within a shared bucket. The block's `mime_type` field SHALL be preserved unchanged; the block's `type: "image"` discriminator SHALL remain `"image"` (no custom block type).

#### Scenario: Image block in a ToolMessage is uploaded and rewritten
- **WHEN** an MCP tool returns a `ToolMessage` whose `content` includes `{type: "image", base64: "<...>", mime_type: "image/png"}` and the turn is about to write `set_state`
- **THEN** the app SHALL upload the decoded bytes to `files/{appdata-or-bucket}/dial-deep-research/<deterministic-name>.png` via `AsyncDial.files.upload`, replace the block in the buffered `ToolMessage.content` with `{type: "image", url: "<returned url>", mime_type: "image/png"}` (no `base64` field), and only then proceed with `messages_to_dict` and `set_state`

#### Scenario: Multiple image blocks in a single ToolMessage are all uploaded
- **WHEN** an MCP tool returns a `ToolMessage` whose `content` contains two or more image blocks
- **THEN** each image block SHALL be uploaded as a distinct file, each block SHALL be rewritten to its own `url` form, and the order of blocks within `content` SHALL be preserved

#### Scenario: Non-image content blocks pass through unchanged
- **WHEN** a `ToolMessage` carries a mix of `{type: "text", ...}` and `{type: "image", base64, ...}` blocks
- **THEN** only the image blocks SHALL be uploaded and rewritten; text blocks SHALL be left bit-for-bit unchanged in the persisted state

#### Scenario: Image block in an AIMessage is uploaded by the same path
- **WHEN** a model emits an `AIMessage` whose `content` contains an `{type: "image", base64, mime_type}` block (e.g. a vision-capable model that returns image output)
- **THEN** that block SHALL be uploaded and rewritten by the same walker that handles `ToolMessage` images, with no separate code path

#### Scenario: Upload failure is fail-closed
- **WHEN** the DIAL files upload for an image block raises an exception (network error, DIAL Core 5xx, auth failure, etc.)
- **THEN** the offending block SHALL be removed from the buffered message and replaced in place with a `TextContentBlock` whose text describes the loss (e.g. `"[image upload failed: image/png, ~340 KB]"`), the exception SHALL be logged server-side, and `set_state` SHALL proceed with the rewritten slice — never with inline `base64` left in place

#### Scenario: A files bucket that cannot be resolved is handled like a failed upload
- **WHEN** resolving the DIAL files bucket raises while a turn's `messages` are about to be persisted
- **THEN** every image block in them SHALL be replaced by the same placeholder a failed upload gets, the failure SHALL be logged server-side, and `set_state` SHALL proceed; a failed research turn's snapshot is handled by **research-resume** instead, which drops it

#### Scenario: Persisted state stays below the DIAL request-body limit on multimodal turns
- **WHEN** a turn produces one or more tool messages carrying image content totalling several MB of base64 in aggregate
- **THEN** the serialized state produced for that turn, its `messages` and any snapshot, SHALL contain only URL references for those images (no `base64` fields). Every later request carries the states of all earlier turns, and DIAL Core rejects a request above its size limit (64 MiB by default) with 413, so image bytes left in a state would bring the conversation closer to a request that can no longer be sent

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
run saved one, otherwise only the failure flag and the `PrepState` the turn started from. A
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
should start a new conversation (outgoing 500); a snapshot image whose download answers 404
counts as such a snapshot. A snapshot image that still cannot be downloaded after its attempts,
for another reason, SHALL resolve to a retryable message saying the saved research progress could
not be loaded (outgoing 500, "try again later" appended).

**Absorbed failures are unaffected.** Failures that are deliberately swallowed and never abort the
turn SHALL NOT trigger this path: a failing tool call, which the **tool-call-fault-tolerance**
capability retries where that helps and otherwise delivers to the agent as an error result
(surfaced as a stage marked ❌), a failed report-review call and a failed report revision once a
draft exists (both absorbed by the report loop, which delivers a draft instead), Opik-tracing
failures, image-rehydration failures during history reconstruction, and every failure after the
report loop has settled a draft (**research-resume**). These continue to let the turn complete
normally. A snapshot image that cannot be downloaded for a resumed run is not one of them: it fails
the turn (**research-resume**).

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
- **AND** a turn whose research run saved a snapshot SHALL persist only its preparation messages,
  its reset `PrepState`, its snapshot and the failure flag; a failure while the application
  properties are fetched or validated, and the refusal of a conversation whose report was
  delivered, SHALL persist no state; any other failed turn SHALL persist only an empty `messages`,
  the `PrepState` it started from and the failure flag; and a later turn learns of the failure from
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
- **WHEN** a resumed run cannot download a snapshot image in three attempts, and no attempt answered 404
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
