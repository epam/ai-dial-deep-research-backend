## MODIFIED Requirements

### Requirement: Tool messages persisted via DIAL custom_content state

For every chat completion request, the app SHALL accumulate the full ordered sequence of `AIMessage` and `ToolMessage` instances observed during the agent's `astream` run — every intermediate `AIMessage` carrying `tool_calls`, every `ToolMessage` returned by a tool, and the final `AIMessage` carrying the natural-language answer — and SHALL persist that sequence into the response by serializing it via `langchain_core.messages.messages_to_dict` and calling `choice.set_state({"messages": [...]})`. Before serialization, the app SHALL traverse every message's `content` and, for every LangChain v1 `ImageContentBlock` carrying a `base64` field, replace the inline data with a `url` reference produced by the **Tool-message image content uploaded to DIAL files before persistence** requirement, so that the persisted state SHALL NOT contain image byte payloads. DIAL SHALL store the resulting list under `assistant.custom_content.state.messages` on the assistant message produced by the request. The DIAL `assistant.tool_calls` and `assistant.tool_call_id` native fields SHALL NOT be populated by the app; the `custom_content.state["messages"]` blob is the sole authoritative carrier of tool-call structure across turns.

#### Scenario: Multi-step tool loop is fully persisted
- **WHEN** a turn produces the sequence `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[Y]) → ToolMessage(Y_result) → AIMessage(content="...")` (multi-step ReAct)
- **THEN** the assistant message persisted by DIAL SHALL carry, under `custom_content.state.messages`, the same five entries in the same order, each encoded as a `messages_to_dict` element with the matching `type` discriminator (`ai`, `tool`, `ai`, `tool`, `ai`); and the assistant message's native `content` field SHALL carry only the final `AIMessage`'s text

#### Scenario: Single-step tool loop is fully persisted
- **WHEN** a turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(content="...")`
- **THEN** `custom_content.state.messages` SHALL carry exactly those three entries in order (`ai`, `tool`, `ai`)

#### Scenario: No-tool turn is fully persisted
- **WHEN** a turn produces only a single final `AIMessage(content="...")` with no tool calls
- **THEN** `custom_content.state.messages` SHALL carry exactly one `ai` entry whose content matches the final assistant text

#### Scenario: Multimodal tool loop persists with image URLs, not image bytes
- **WHEN** a turn produces a `ToolMessage` whose `content` is a list containing one or more `{type: "image", base64, mime_type}` blocks
- **THEN** the entry persisted under `custom_content.state.messages` for that `ToolMessage` SHALL contain the same blocks rewritten to the `{type: "image", url, mime_type}` form (with `base64` absent and `url` referencing a DIAL files object); and the size of the serialized state blob SHALL NOT include the original image byte payload

### Requirement: Reconstruction of LangChain history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the LangChain message history fed to the agent by walking `request.messages` in order and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["messages"]` is present and non-empty, emitting `messages_from_dict(custom_content.state["messages"])` (the full intermediate-plus-final slice) instead of consulting the native `content` or `tool_calls` fields, then traversing the reconstructed messages and re-inlining every LangChain v1 `ImageContentBlock` carrying a `url` (and no `base64`) by downloading the file from DIAL and replacing the block with the same `ImageContentBlock` populated with `base64` and `mime_type` (so the rehydrated block satisfies the in-flight contract from `multimodal-tool-output`);
- if `role == assistant` AND `custom_content.state["messages"]` is absent (legacy turn produced before this change), emitting a single `AIMessage(content=msg.content)` as a fallback so legacy conversations continue to work without a migration step.

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

## ADDED Requirements

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
