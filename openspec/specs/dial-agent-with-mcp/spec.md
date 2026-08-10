# dial-agent-with-mcp

## Purpose

A DIAL application server implementing the chat-completion protocol for the `deep-research` deployment (application type display name `Deep Research`), and for the `deep-research-playground` deployment when that channel is enabled. Each turn starts with the preparation agent (see **clarification-and-plan-alignment**); when it approves a plan and calls `start_research`, the research graph runs in the same turn (see **research-execution**) and the report that graph settles on becomes the turn's answer. Research tools come from the HTTP MCP servers configured in the application properties (e.g. the generic-RAG service), each reached as a DIAL application through Core (deployment mode) or as a directly-reachable endpoint (direct mode), with a fresh client per turn. Tool calls and their results surface as timed DIAL stages; assistant message content carries model-authored text only — never tool calls, tool results, or structured non-text blocks. All turn-aborting failures are resolved to a user-safe message (carrying an error reference) and delivered through the DIAL error protocol — a non-200 error body or an in-stream error chunk — never as fake-success HTTP 200 assistant content. LLM calls, DIAL file operations, and deployment-mode MCP connections authenticate with the per-request api-key that DIAL Core forwards with each request (via the SDK's auth-header propagation), not a static service key; the per-request bearer token is forwarded to deployment-mode MCP servers when present. This capability owns the structural DIAL-app surface: protocol conformance, the streaming transport, and the health endpoint.
## Requirements
### Requirement: DIAL-protocol application server
The repository SHALL implement an application server that conforms to the DIAL application protocol, using the official DIAL Python SDK, exposing a chat completion endpoint consumable by DIAL core under the deployment id `deep-research`.

#### Scenario: Request accepted from DIAL core
- **WHEN** DIAL core forwards a chat completion request to the app with a well-formed DIAL envelope
- **THEN** the app SHALL accept the request and respond with a well-formed DIAL chat completion response

#### Scenario: Rejects malformed requests
- **WHEN** the app receives a request that does not conform to the DIAL application protocol
- **THEN** it SHALL respond with an appropriate HTTP 4xx error surfaced via the SDK, without crashing the server process

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

### Requirement: Health endpoint
The app SHALL expose a lightweight health check endpoint that returns success when the process is able to serve requests.

#### Scenario: Health probe
- **WHEN** a client (or Docker healthcheck) issues a GET to the health endpoint
- **THEN** the app SHALL respond with HTTP 200 and a minimal body indicating healthy status

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

### Requirement: Tool execution surfaced as timed DIAL stages
For every tool the agent invokes during a request, the app SHALL emit a single DIAL "result" stage carrying both the input arguments and the tool's output. Titles follow the normalized form `[TOOL] "<tool_name>" - <action> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where action ∈ `{result, error}` and emoji ∈ `{✅, ❌}` respectively. Stage timestamps SHALL bracket the actual execution window (start when the call is dispatched to the MCP server, end when the result is received). When the tool returns an error (caught by `handle_tool_error` instead of bubbling), the stage SHALL use the `error ❌` action variant so the failure stands out in the chat UI. Stage content is rendered as markdown by DIAL, so both the input arguments and the tool output SHALL be wrapped in fenced code blocks (single newlines would otherwise collapse), making multi-line payloads — JSON args, plain-text results, error tracebacks — readable verbatim.

#### Scenario: Tool result stage carries start, end, elapsed, input, and output
- **WHEN** the tool result returns from the MCP server
- **THEN** the app SHALL emit a stage whose title includes the start timestamp, end timestamp, and elapsed seconds, and whose body contains an "Input" section with the JSON-fenced arguments followed by an "Output" section with the fenced tool result content

#### Scenario: Tool error stage signals failure but does not abort the turn
- **WHEN** an MCP tool raises (e.g. argument validation rejects the LLM's call) and the error is caught by the per-tool error handler
- **THEN** the app SHALL emit a stage whose title uses the `error ❌` variant (e.g. `[TOOL] "<tool_name>" - error ❌ (...)`), whose body carries the JSON-fenced "Input" section followed by a fenced "Error" section with the error text; the agent SHALL receive the same error text as a `ToolMessage` in its next step and MAY retry with corrected arguments without the chat completion failing

### Requirement: Assistant message content contains only model text
The DIAL response message content SHALL, in chronological order, contain only the
natural-language assistant text that each component is specified below to forward — never tool
calls, tool results, or structured non-text content blocks (e.g. Anthropic-style `thinking`
blocks, image blocks); those are conveyed via stages (for tool execution UI display) and via
`assistant.custom_content.state["messages"]` (for cross-turn replay). Coverage differs by
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
- **WHEN** a follow-up chat completion request arrives after an earlier tool-using turn
- **THEN** the second turn's agent SHALL receive the prior turn's intermediate `AIMessage(tool_calls=…, content=…)` and `ToolMessage(...)` slice plus the prior turn's final `AIMessage` as conversation history, reconstructed from the prior assistant message's `custom_content.state["messages"]` field, in the original order, instead of being limited to prior assistant text

#### Scenario: A new assistant message starts a new paragraph with no tool round between
- **WHEN** two text segments from distinct assistant messages reach the choice with no tool result between them
- **THEN** the app SHALL still insert a `"\n\n"` between them, because the boundary is the change of message

#### Scenario: Tokens of one message are not separated
- **WHEN** one assistant message streams as many chunks
- **THEN** the app SHALL append them with nothing inserted between, producing one paragraph

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

### Requirement: Reconstruction of LangChain history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the LangChain message history fed to the agent by walking `request.messages` in order and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["messages"]` is present and non-empty, emitting `messages_from_dict(custom_content.state["messages"])` (the full intermediate-plus-final slice) instead of consulting the native `content` or `tool_calls` fields, then traversing the reconstructed messages and re-inlining every LangChain v1 `ImageContentBlock` carrying a `url` (and no `base64`) by downloading the file from DIAL and replacing the block with the same `ImageContentBlock` populated with `base64` and `mime_type` (so the rehydrated block satisfies the in-flight contract from `multimodal-tool-output`);
- if `role == assistant` AND `custom_content.state["messages"]` is absent (legacy turn produced before this change), emitting a single `AIMessage(content=msg.content)` as a fallback so legacy conversations continue to work without a migration step.

This asymmetry — user turns read from native `content`, assistant turns read from `custom_content.state["messages"]` — exists because the assistant's native `content` is a display-only concatenation of every streamed text segment (intermediate reasoning plus `"\n\n"` separators plus the final answer; see **Assistant message content contains only model text**) and cannot be decomposed back into the `AIMessage` / `ToolMessage` / `tool_call` interleaving the agent needs. The persisted state slice — which includes the final `AIMessage`, per **Tool messages persisted via DIAL custom_content state** — is the only structurally faithful source for assistant turns, so the native assistant `content` and `tool_calls` fields SHALL NOT be consulted when a usable state slice is present. User turns carry no such structure, so their flat native `content` is sufficient.

The system message provided by the DIAL request SHALL continue to be ignored on reconstruction; the app's own system prompt is supplied to `create_agent` directly.

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

### Requirement: Tool-message image content uploaded to DIAL files before persistence

Before calling `choice.set_state(...)` at the end of each turn, the app SHALL upload every LangChain v1 `ImageContentBlock` carrying a `base64` field — wherever it appears in the buffered `AIMessage` / `ToolMessage` slice — to the DIAL files API and replace the block's `base64` field with a `url` field pointing at the resulting file object. The upload SHALL use the `aidial-client` `AsyncDial` interface. The target bucket SHALL be resolved per turn from `AsyncDial.bucket.get_raw()`, preferring the `appdata` value and falling back to `bucket` when `appdata` is unset. The target path SHALL include a fixed `dial-deep-research/` prefix to namespace the app within a shared bucket. The block's `mime_type` field SHALL be preserved unchanged; the block's `type: "image"` discriminator SHALL remain `"image"` (no custom block type).

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

#### Scenario: Persisted state stays below the DIAL request-body limit on multimodal turns
- **WHEN** a turn produces one or more tool messages carrying image content totalling more than 1 MB of base64 in aggregate
- **THEN** the serialized `custom_content.state["messages"]` payload produced for that turn SHALL contain only URL references for those images (no `base64` fields), and DIAL Chat SHALL NOT reject the resulting request with a `413 Body exceeded 1mb limit` error

### Requirement: MCP authentication via api-key header

The app SHALL authenticate to the generic-RAG MCP server using per-request credentials, in one
of two mutually exclusive modes (selected by configuration, see **Configuration via environment
variables**):

- **Deployment mode** — the MCP server is a DIAL application reached through DIAL Core. The MCP
  endpoint URL SHALL be `{DIAL_URL}/v1/deployments/{MCP_DEPLOYMENT_NAME}/mcp`. The per-request
  `api-key` SHALL be supplied by DIAL SDK header propagation (the URL is under DIAL Core; see
  **Per-request authentication to DIAL Core via header propagation**), so the app SHALL NOT set a
  static `api-key` header itself. When the incoming request carries a bearer token, the app SHALL
  additionally send `Authorization: Bearer <request bearer token>` on the MCP requests; when the
  request has no bearer token, no `Authorization` header SHALL be added.
- **Local-dev mode** — a directly-reachable external MCP. The app SHALL send the static
  `MCP_API_KEY` value in the `api-key` header on every MCP request (the previous behavior) and
  SHALL NOT add an `Authorization` header.

Transport SHALL remain streamable HTTP and the MCP client SHALL remain per-request (no
cross-request caching), consistent with the **Tool-calling agent over MCP-loaded tools**
requirement.

#### Scenario: Deployment mode sends per-request api-key and forwards the bearer
- **WHEN** the app is in deployment mode and opens an MCP connection for a request that carries a
  bearer token
- **THEN** the MCP endpoint URL SHALL be `{DIAL_URL}/v1/deployments/{MCP_DEPLOYMENT_NAME}/mcp`, the
  outgoing `api-key` header SHALL equal the request's per-request key (via propagation), and an
  `Authorization: Bearer <request bearer token>` header SHALL be present

#### Scenario: Deployment mode without a bearer token
- **WHEN** the app is in deployment mode and the incoming request carries no bearer token
- **THEN** the MCP requests SHALL carry the per-request `api-key` (via propagation) and SHALL NOT
  include an `Authorization` header

#### Scenario: Local-dev mode sends the configured static key
- **WHEN** the app is in local-dev mode and opens an MCP connection to load tools or invoke a tool
- **THEN** the request SHALL target `MCP_URL`, include the header `api-key: <MCP_API_KEY value>`,
  and SHALL NOT include an `Authorization` header

### Requirement: Configuration via environment variables

The app SHALL be configurable through environment variables documented in `.env.example` and the
README environment-variables table. The README environment-variables table SHALL present every
variable in a single table listing its default and its required status. The app SHALL NOT require
a channel-config file path (`CHANNEL_CONFIG_PATH` is removed); per-channel behavior comes from
DIAL application properties (see the **application-config-schema** capability).

`DIAL_URL` SHALL be a required environment variable with no built-in default: the app SHALL NOT
carry a fallback DIAL Core URL, and SHALL exit non-zero at startup with a message naming
`DIAL_URL` when it is unset. `.env.example` SHALL document `DIAL_URL` with the local-dev value
`http://localhost:8080`, so the code carries no localhost default while the local dev loop still
works.

The MCP connection SHALL be configured in exactly one of two mutually exclusive modes, enforced
at process startup by a settings validator:

- **Deployment mode**: `MCP_DEPLOYMENT_NAME` names the DIAL application/deployment id of the
  generic-RAG MCP server, reached through DIAL Core (see **MCP authentication via api-key
  header**). `MCP_URL` and `MCP_API_KEY` are not used.
- **Local-dev mode**: `MCP_URL` gives a directly-reachable MCP endpoint and `MCP_API_KEY` its
  static key. When `MCP_URL` is set the app SHALL use local-dev mode and SHALL require
  `MCP_API_KEY`.

`MCP_SERVER_NAME` SHALL remain required as the logical connection name in both modes. A
configuration that resolves to neither mode (no `MCP_URL` and no `MCP_DEPLOYMENT_NAME`), or that
sets `MCP_URL` without `MCP_API_KEY`, SHALL cause the app to exit non-zero at startup with a
message naming the problem.

The app SHALL NOT read a `DIAL_API_KEY` environment variable; downstream DIAL Core calls
authenticate with the per-request api-key (see **Per-request authentication to DIAL Core via
header propagation**).

`LLM_MODELS_<NAME>` env mappings SHALL be supported as overrides for the per-enum-member DIAL
Core deployment id; if unset, the app SHALL fall back to the enum member's value (the model id).

#### Scenario: Startup with DIAL_URL set
- **WHEN** the process starts with a valid MCP mode configured and `DIAL_URL` set
- **THEN** the app SHALL start successfully and use `DIAL_URL` as the DIAL Core base URL

#### Scenario: Missing DIAL_URL fails fast
- **WHEN** the process starts with a valid MCP mode configured but no `DIAL_URL` set
- **THEN** the app SHALL exit non-zero before serving any request, with a message naming
  `DIAL_URL`, and SHALL NOT fall back to any built-in URL

#### Scenario: Deployment-mode startup
- **WHEN** the process starts with `MCP_SERVER_NAME` and `MCP_DEPLOYMENT_NAME` set and no `MCP_URL`
- **THEN** the app SHALL start successfully in deployment mode and register the `deep-research`
  deployment

#### Scenario: Local-dev-mode startup
- **WHEN** the process starts with `MCP_SERVER_NAME`, `MCP_URL`, and `MCP_API_KEY` set
- **THEN** the app SHALL start successfully in local-dev mode

#### Scenario: Local-dev mode missing the static key
- **WHEN** the process starts with `MCP_URL` set but `MCP_API_KEY` unset
- **THEN** the app SHALL exit non-zero before serving any request, with a message naming
  `MCP_API_KEY`

#### Scenario: Neither MCP mode configured
- **WHEN** the process starts with neither `MCP_URL` nor `MCP_DEPLOYMENT_NAME` set
- **THEN** the app SHALL exit non-zero before serving any request, with a message indicating no
  MCP connection is configured

#### Scenario: Startup without a channel config file
- **WHEN** the process starts with a valid MCP mode configured and no `CHANNEL_CONFIG_PATH` in the
  environment
- **THEN** the app SHALL start successfully and register the `deep-research` deployment without
  reading any local config file

#### Scenario: DIAL_API_KEY is not consulted
- **WHEN** the process starts with no `DIAL_API_KEY` set (or with one set)
- **THEN** the app SHALL start successfully and SHALL NOT use it — downstream DIAL Core auth comes
  from the per-request api-key

#### Scenario: LLM_MODELS override resolves at request time
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is set in the environment
  for the configured model
- **THEN** the agent SHALL use that value as the DIAL Core `azure_deployment` id

#### Scenario: LLM_MODELS unset falls back to enum value
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is **not** set
- **THEN** the agent SHALL use the enum member's `.value` (the model id, e.g. `gpt-5.2-2025-12-11`)
  as the DIAL Core deployment id without raising

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
- **THEN** the corresponding tool call SHALL appear in the Opik trace as a span carrying the tool arguments and the error text, while the existing DIAL `error ❌` stage and agent retry behaviour SHALL be unchanged

### Requirement: Opik trace thread id sourced from incoming request

When Opik tracing is enabled, the app SHALL attempt to extract a thread identifier from the incoming chat completion request via a generically-named extraction helper (e.g. `extract_thread_id`) and construct the per-request `OpikTracer` with that identifier as its `thread_id`. The helper's body, today, SHALL only know how to read DIAL's conversation header (`X-CONVERSATION-ID`) from `request.headers`; the helper SHALL be named so a future second source can slot in without renaming. The helper SHALL be exception-safe: on any failure path — header absent, value empty after whitespace strip, request shape unexpected, or any other exception during extraction — the helper SHALL return `None`. When the helper returns `None`, the tracer SHALL be constructed without a `thread_id`, and the turn SHALL be traced exactly as before this change (one ungrouped trace per turn). Extraction failures SHALL NOT raise out of the helper and SHALL NOT cause the chat completion to fail.

#### Scenario: DIAL conversation id grouped into a single Opik thread
- **WHEN** Opik tracing is enabled and the chat completion request carries an `X-CONVERSATION-ID` header with a non-empty value, and the same conversation issues multiple turns
- **THEN** every turn's Opik trace SHALL be created with `thread_id` set to that conversation id, so all turns of the conversation appear under a single Opik thread in the Opik UI

#### Scenario: Conversation id missing falls back to ungrouped tracing
- **WHEN** Opik tracing is enabled and the chat completion request does not carry an `X-CONVERSATION-ID` header (e.g. a raw API client or eval harness call)
- **THEN** the tracer SHALL be constructed without a `thread_id`, the turn SHALL still be traced normally, and the trace SHALL appear as an individual record in Opik exactly as it did before this change

#### Scenario: Empty conversation id treated as missing
- **WHEN** Opik tracing is enabled and the request carries `X-CONVERSATION-ID` with an empty or whitespace-only value
- **THEN** the extraction helper SHALL return `None` and the tracer SHALL be constructed without a `thread_id`

#### Scenario: Extraction failure never breaks the turn
- **WHEN** Opik tracing is enabled and any exception is raised while attempting to read the conversation id (e.g. an unexpected `request.headers` shape on a future SDK version)
- **THEN** the helper SHALL return `None`, the tracer SHALL be constructed without a `thread_id`, the chat completion SHALL proceed normally, and no exception SHALL propagate out of the helper

#### Scenario: Thread id is not extracted when tracing is disabled
- **WHEN** Opik tracing is disabled (`OPIK_TRACING_ENABLED` unset or false) and a chat completion request is processed
- **THEN** no `OpikTracer` SHALL be constructed and no thread-id extraction SHALL run, preserving the "no Opik network calls and no Opik-dependent code paths" behaviour of the existing tracer-absent requirement

### Requirement: DIAL SDK runs in pydantic v2 mode

The app SHALL ensure the DIAL SDK uses pydantic v2 models, consistent with the app's own pydantic v2 models (`ApplicationProperties`, `Settings`, LLM structured outputs).

The DIAL SDK selects its model backend from the `PYDANTIC_V2` environment variable, read once
**at import time**, and defaults to pydantic v1 when the variable is unset. The app SHALL
guarantee `PYDANTIC_V2=True` is set in the process environment before the first `aidial_sdk`
import, for every entry point — the running app, the test suite, and helper scripts. It SHALL
enforce this in code (not only via deployment configuration) at the earliest guaranteed import
point, and SHALL NOT override a `PYDANTIC_V2` value that is already set explicitly in the
environment.

#### Scenario: SDK models are pydantic v2 when the app runs

- **WHEN** the application package is imported and the DIAL SDK is subsequently imported
- **THEN** the SDK operates in pydantic v2 mode, so its request/response models are pydantic v2
  models consistent with the app's own models

#### Scenario: Flag is set even without deployment configuration

- **WHEN** the app, the test suite, or a helper script imports the application package in an
  environment where `PYDANTIC_V2` was not set (for example, tests, which do not load `.env`)
- **THEN** `PYDANTIC_V2` is `True` in the process environment before `aidial_sdk` is imported

#### Scenario: Explicit environment override is respected

- **WHEN** `PYDANTIC_V2` is already set to an explicit value in the environment before the
  application package is imported
- **THEN** the app SHALL NOT overwrite that value

### Requirement: Per-request authentication to DIAL Core via header propagation

The app SHALL authenticate all outgoing calls to DIAL Core with the **per-request** `api-key`
that DIAL Core sends on the incoming chat completion request, not a static service key. It
SHALL achieve this by enabling the DIAL SDK's auth-header propagation
(`DIALApp(propagate_auth_headers=True)`, with `dial_url` set), which rewrites the `api-key`
header to the per-request value on every outgoing HTTP request whose URL is under `DIAL_URL` —
covering the LLM calls (`AzureChatOpenAI`), DIAL file operations (`AsyncDial`), and the
Core-hosted MCP endpoint in deployment mode. Clients that require a credential at construction
(`AzureChatOpenAI`, `AsyncDial`) SHALL be built with an obviously-fake placeholder api-key that
the propagator overwrites per request; the app SHALL NOT load or require a static `DIAL_API_KEY`.
The app SHALL NOT forward the request bearer token to the LLM endpoint — LLM authentication is
api-key only.

#### Scenario: Propagation enabled at app construction
- **WHEN** the app is constructed via `create_app()`
- **THEN** the `DIALApp` SHALL be created with auth-header propagation enabled and `dial_url` set

#### Scenario: LLM call carries the per-request key
- **WHEN** the agent invokes the LLM during a chat completion request
- **THEN** the outgoing HTTP request to DIAL Core SHALL carry the incoming request's per-request
  `api-key` as the `api-key` header, not a static service key

#### Scenario: DIAL file operations carry the per-request key
- **WHEN** the app reads user attachments or uploads files to DIAL Core during a request
- **THEN** those requests SHALL carry the incoming request's per-request `api-key`

#### Scenario: No static DIAL key required at startup
- **WHEN** the process starts without any `DIAL_API_KEY` set in the environment
- **THEN** the app SHALL start successfully and SHALL make no use of a static DIAL service key on
  the request path

#### Scenario: Bearer token is not sent to the LLM
- **WHEN** the incoming request carries a bearer token and the agent invokes the LLM
- **THEN** the LLM request SHALL NOT include an `Authorization: Bearer` header (the bearer is
  forwarded only to the RAG MCP, per the **MCP authentication** requirement)

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
losing a long research turn). Where that happens, the retry is a distinct assistant message, so a
`"\n\n"` separates the abandoned fragment from the full answer per **Assistant message content
contains only model text** — the duplicate reads as its own paragraph rather than running into the
text that replaces it. The report-writing call is not streamed at all, so a retried report call
cannot duplicate visible text.

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

#### Scenario: A retry's abandoned fragment is separated from the full answer
- **WHEN** a streaming model call has already appended some tokens to the choice, drops, and the retried call succeeds
- **THEN** the fragment SHALL remain visible (it cannot be retracted) and the retried text SHALL be appended after a `"\n\n"`, since the retry is a distinct assistant message

#### Scenario: Stream drops persistently
- **WHEN** an LLM call whose failure aborts the turn fails with `httpx.RemoteProtocolError` on every attempt in the budget
- **THEN** the app SHALL stop after 3 attempts and deliver the failure through the DIAL error
  protocol, resolved as the retryable network-drop message with an error reference

#### Scenario: Persistent drops in the report loop do not abort the turn
- **WHEN** the report-review call, or a report revision written after a first draft, fails on every attempt in the budget
- **THEN** the app SHALL NOT deliver a protocol error; the report loop SHALL absorb the failure, deliver the current or previous draft, and log a warning

#### Scenario: The report call drops mid-response
- **WHEN** the report-writing call's connection drops while its response is being read and a retry succeeds
- **THEN** the turn SHALL complete with the retried report, and the delivered and persisted report SHALL be the retried attempt's text only; a failed attempt SHALL leave no text anywhere, since the call is not streamed and its response is read only after it completes

#### Scenario: Non-transient failures are not retried in-app
- **WHEN** an LLM call fails with an HTTP status error (e.g. 400) or a timeout
- **THEN** the in-app stream-drop retry SHALL NOT engage; the failure keeps its existing handling
  (the OpenAI client's own retries and the DIAL error protocol)
