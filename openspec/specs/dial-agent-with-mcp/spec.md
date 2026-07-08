# dial-agent-with-mcp

## Purpose

A DIAL chat completion (deployment id `deep-research`, display name `Deep Research`) that runs a per-request LangChain tool-calling agent against a single HTTP MCP server (the generic-RAG service), authenticated via an `api-key` header. Tool calls and tool results stream to DIAL as timed stages; only the agent's final assistant text becomes message content. All failures funnel into a single logged-and-replaced friendly assistant message — no exceptions ever bubble out of the handler. LLM calls go through DIAL Core using a static service `DIAL_API_KEY`; the deep-research app does not forward per-request user keys. This capability replaces the original echo placeholder and absorbs the structural DIAL-app surface (protocol conformance, streaming, health) under its own contract.
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
The app SHALL produce its assistant response through the SDK's streaming API so that the streaming code path is exercised end-to-end. The app SHALL stream assistant text to `choice` token-by-token as the LLM produces it, rather than buffering each LLM call's full output and emitting it as a single chunk after the producing graph node returns; concretely, the per-request agent's `astream` invocation SHALL subscribe to LangGraph's `messages` stream mode (composed with the existing `updates` mode) and forward every `AIMessageChunk`'s text content to `choice.append_content` immediately, so users see content arrive while the model is still generating.

#### Scenario: Streamed delivery
- **WHEN** DIAL core requests a streaming chat completion
- **THEN** the app SHALL emit the assistant content via one or more streaming chunks terminated by an end-of-stream signal, conforming to the SDK's streaming contract

#### Scenario: Assistant text streams token-by-token, not message-by-message
- **WHEN** the agent's underlying LLM produces a multi-token assistant message (whether the final answer or an intermediate text-plus-tool-calls message)
- **THEN** the app SHALL emit `choice.append_content` calls for individual token chunks during generation, such that DIAL core observes incremental content updates before the producing LangGraph node has returned, and SHALL NOT defer the text to a single end-of-step emission

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
research agent is the graph's **researcher node**, not a directly-invoked
first-message agent.

The researcher node SHALL be a fresh per-request LangChain `create_agent` over the
tools fetched from a freshly-constructed MCP client, plus one sentinel tool
(`finish_iteration`). It SHALL have access only to MCP-loaded tools and that
sentinel — no other built-in tools, subagents, skills, or persistent memory beyond
the graph state. The researcher SHALL be run with **forced tool choice** (every
model step emits a tool call) via an in-process `AgentMiddleware`, so the model
cannot emit a free-form assistant message; it ends an iteration by calling
`finish_iteration` (a `return_direct` sentinel). The previously-permitted reflection
middleware is removed; phase control now lives in the research graph's edges, not in
middleware that redirects a single agent's control flow.

The MCP client SHALL NOT be cached across requests, the app SHALL NOT open a
long-lived SSE listening stream on the MCP endpoint, and the app SHALL NOT issue or
retain an `Mcp-Session-Id`. Tool-list freshness across requests is achieved by
re-polling `tools/list` at the start of every turn that constructs a client,
matching the generic-RAG server's `stateless_http=True` deployment; persistent-session
features (long-lived sessions, `Mcp-Session-Id`, `Last-Event-ID` resumability,
`notifications/tools/list_changed`, `notifications/resources/*`,
`notifications/prompts/list_changed`) are out of scope for this capability.

#### Scenario: Researcher invokes an MCP tool

- **WHEN** the researcher needs information from the knowledge base during an iteration
- **THEN** it SHALL emit a tool call, the MCP server SHALL execute the tool, and the result SHALL be incorporated into the accumulated research context

#### Scenario: Researcher is run only after plan approval

- **WHEN** a chat completion request is processed and no plan has been approved yet
- **THEN** the researcher node SHALL NOT run and no MCP client SHALL be constructed for research; the turn SHALL produce only preparation output

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
The DIAL response message content SHALL carry all of the agent's natural-language assistant text emitted during the turn, in chronological order — including text produced on intermediate `AIMessage` instances that also carry `tool_calls`, not just the final text-only `AIMessage`. Tool calls, tool results, and any structured non-text content blocks (e.g. Anthropic-style `thinking` blocks, image blocks) SHALL NOT appear in the assistant message content; they are conveyed via stages (for tool execution UI display) and via `assistant.custom_content.state["messages"]` (for cross-turn replay). When two streamed text segments from distinct `AIMessage`s are separated in time by one or more tool stages, the app SHALL insert a `"\n\n"` separator between them in `message.content` so the segments render as separate paragraphs rather than running together.

#### Scenario: Tool-using turn streams intermediate text alongside the final answer
- **WHEN** the agent produces an intermediate `AIMessage` carrying both natural-language text (e.g. `"Plan: ..."`) and `tool_calls`, then tool result(s), then a final `AIMessage` with the answer
- **THEN** the DIAL response `message.content` SHALL contain the intermediate text followed by the final text, in that order, with a `"\n\n"` separator between them; tool stages SHALL still render between the two segments via the stage channel; the response content SHALL NOT contain serialized tool calls, tool result payloads, or `messages_to_dict` blobs

#### Scenario: Text-only turn (no tool calls)
- **WHEN** the agent answers without invoking any tool, producing a single text-only final `AIMessage`
- **THEN** the DIAL response `message.content` SHALL equal that message's text, with no leading or trailing separator, streamed token-by-token

#### Scenario: Structured content blocks flattened to text
- **WHEN** an `AIMessageChunk` carries `content` as a list of content blocks (e.g. `[{type: "text", text: "..."}, {type: "thinking", thinking: "..."}, {type: "image", ...}]`) instead of a bare string
- **THEN** the app SHALL append the concatenation of every `text`-typed block's `text` payload to `choice` and SHALL silently skip every non-text block (no append, no error, no stage)

#### Scenario: Cross-turn replay of tool messages
- **WHEN** a follow-up chat completion request arrives after an earlier tool-using turn
- **THEN** the second turn's agent SHALL receive the prior turn's intermediate `AIMessage(tool_calls=…, content=…)` and `ToolMessage(...)` slice plus the prior turn's final `AIMessage` as conversation history, reconstructed from the prior assistant message's `custom_content.state["messages"]` field, in the original order, instead of being limited to prior assistant text

### Requirement: Tool messages persisted via DIAL custom_content state

For every chat completion request, the app SHALL accumulate the ordered sequence of
`AIMessage`, `ToolMessage`, and injected `HumanMessage` instances observed during
the turn — for a research turn this is the research graph's slice: every researcher
`AIMessage` carrying `tool_calls`, every `ToolMessage` returned by a tool, every
next-iteration plan `HumanMessage` injected by the reviewer node, and the final
report `AIMessage` — and SHALL persist that sequence by serializing it via
`langchain_core.messages.messages_to_dict` and writing it under
`assistant.custom_content.state` (the `messages` field of the unified `DialState`).
The injected next-iteration plan `HumanMessage`s SHALL be captured in run order so
the persisted slice interleaves them at the positions the researcher saw them; they
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
- **THEN** `custom_content.state["messages"]` SHALL carry those entries in run order, each encoded with its matching `messages_to_dict` `type` discriminator, the injected next-plan `HumanMessage` appearing at the position the researcher saw it, and the report `AIMessage` last

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
- **THEN** the reconstructed `ToolMessage` SHALL have the offending image block replaced by a `TextContentBlock` placeholder describing the loss, the failure SHALL be logged server-side, and the turn SHALL proceed normally rather than surfacing the friendly error string

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

### Requirement: Top-level error funnel with friendly assistant message
The app SHALL wrap each chat completion in a top-level exception handler. On any failure (MCP unreachable, MCP tool error, LLM error, malformed model output, etc.), the handler SHALL log the exception server-side and append a fixed friendly error string to the assistant message via `choice.append_content`. The handler SHALL NOT re-raise the exception; the chat completion SHALL complete successfully from DIAL's perspective.

#### Scenario: MCP server unreachable
- **WHEN** the MCP server cannot be reached at the configured URL during a chat completion
- **THEN** the app SHALL log the failure server-side and the DIAL response SHALL contain a friendly error string as the assistant message, completing successfully (HTTP 200) from DIAL's perspective

#### Scenario: LLM error mid-turn
- **WHEN** the LLM call fails after one or more tool stages have already been streamed
- **THEN** the app SHALL log the failure server-side and append the friendly error string to the existing partial assistant content, completing successfully from DIAL's perspective

#### Scenario: MCP tool execution error
- **WHEN** an MCP tool raises an error during execution
- **THEN** the app SHALL log the failure server-side and the DIAL response SHALL end with the friendly error string as part of the assistant message, completing successfully from DIAL's perspective

### Requirement: MCP authentication via api-key header
The app SHALL authenticate to the MCP server by sending the configured MCP API key in the `api-key` HTTP header on every request to the MCP server.

#### Scenario: Configured key sent on connect
- **WHEN** the app opens an HTTP MCP connection to load tools or invoke a tool
- **THEN** the request SHALL include the header `api-key: <MCP_API_KEY value>`

### Requirement: LLM access via DIAL Core with static service key
The app SHALL invoke its LLM through DIAL Core, authenticating with a static `DIAL_API_KEY` value loaded from environment configuration. The app SHALL NOT forward per-request user API keys (e.g. `request.api_key`) to the LLM call.

#### Scenario: LLM call uses service key
- **WHEN** the agent invokes the LLM
- **THEN** the underlying HTTP request to DIAL Core SHALL carry the configured `DIAL_API_KEY` value as authentication, regardless of any API key value present on the incoming DIAL chat completion request

### Requirement: Configuration via environment variables
The app SHALL be configurable through environment variables documented in `.env.example` and `envvars.md`. The MCP server URL and the MCP API key SHALL be required at process startup. The DIAL API key SHALL be optional with a default of `dial_api_key` (matching the dev key registered in `dial_conf/core/config.json`); deployments shipping a real key SHALL override it via `DIAL_API_KEY`. `LLM_MODELS_<NAME>` env mappings SHALL be supported as overrides for the per-enum-member DIAL Core deployment id; if unset, the app SHALL fall back to the enum member's value (the model id).

#### Scenario: Missing startup-required variable
- **WHEN** the process starts without one of `MCP_URL` or `MCP_API_KEY`
- **THEN** the app SHALL exit non-zero before serving any request, with a log/error message that names the missing variable

#### Scenario: DIAL_API_KEY default
- **WHEN** the process starts without `DIAL_API_KEY` set in the environment
- **THEN** `dial_app_settings.dial_api_key` SHALL resolve to the `dial_api_key` default and the app SHALL start successfully

#### Scenario: LLM_MODELS override resolves at request time
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is set in the environment for the configured model
- **THEN** the agent SHALL use that value as the DIAL Core `azure_deployment` id

#### Scenario: LLM_MODELS unset falls back to enum value
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is **not** set
- **THEN** the agent SHALL use the enum member's `.value` (the model id, e.g. `gpt-5.2-2025-12-11`) as the DIAL Core deployment id without raising

### Requirement: Opik tracing of agent runs when configured

The app SHALL attach an `opik.integrations.langchain.OpikTracer` callback to the per-request LangChain agent's streaming invocation **iff** Opik tracing is enabled via configuration (`OpikSettings.tracing_enabled` is true). When attached, the tracer SHALL capture the full hierarchical trace of the turn — the agent graph run, the underlying LLM call, and every MCP tool call (including arguments, results, and errors) — without altering the agent's outputs, the DIAL stages emitted, the assistant message content, or the top-level error funnel. When Opik tracing is not enabled, the agent SHALL run with no Opik callback attached and SHALL produce identical observable behaviour to a build that does not depend on Opik.

#### Scenario: Tracer attached when enabled
- **WHEN** `OPIK_TRACING_ENABLED=true` is set and the local Opik stack (started via `make opik-up`) is reachable, and a chat completion request is processed
- **THEN** the agent's streaming invocation SHALL be configured with an `OpikTracer` callback, and the resulting trace in Opik SHALL contain the agent run, the LLM call, and a span per MCP tool invocation with their inputs, outputs, and timings

#### Scenario: Tracer absent when disabled
- **WHEN** `OPIK_TRACING_ENABLED` is unset or false and a chat completion request is processed
- **THEN** no `OpikTracer` SHALL be constructed or attached, no Opik network calls SHALL be made by the app, and the chat completion SHALL produce the same DIAL stages and assistant content as a run with the Opik dependency absent

#### Scenario: Tracing failure does not break the turn
- **WHEN** Opik tracing is enabled but the configured Opik instance is unreachable mid-turn
- **THEN** the chat completion SHALL still complete successfully (the agent SHALL produce its assistant text and tool stages as usual), with any tracer-side exception either swallowed by LangChain's callback machinery or absorbed by the existing top-level error funnel — i.e. tracing failures SHALL never produce a non-200 response and SHALL never replace successful assistant content with the friendly error string

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

