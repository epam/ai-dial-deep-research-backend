## MODIFIED Requirements

### Requirement: Reconstruction of LangChain history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the LangChain message history fed to the agent by walking `request.messages` in order and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["messages"]` is present and non-empty, emitting `messages_from_dict(custom_content.state["messages"])` (the full intermediate-plus-final slice) instead of consulting the native `content` or `tool_calls` fields, then traversing the reconstructed messages and re-inlining every LangChain v1 `ImageContentBlock` carrying a `url` (and no `base64`) by downloading the file from DIAL and replacing the block with the same `ImageContentBlock` populated with `base64` and `mime_type` (so the rehydrated block satisfies the in-flight contract from `multimodal-tool-output`);
- if `role == assistant` AND `custom_content.state["messages"]` is absent (legacy turn produced before this change), emitting a single `AIMessage(content=msg.content)` as a fallback so legacy conversations continue to work without a migration step.

This asymmetry — user turns read from native `content`, assistant turns read from `custom_content.state["messages"]` — exists because the assistant's native `content` is a display-only concatenation of every streamed text segment (intermediate reasoning plus `"\n\n"` separators plus the final answer; see **Assistant message content contains only model text**) and cannot be decomposed back into the `AIMessage` / `ToolMessage` / `tool_call` interleaving the agent needs. The persisted state slice — which includes the final `AIMessage`, per **Tool messages persisted via DIAL custom_content state** — is the only structurally faithful source for assistant turns, so the native assistant `content` and `tool_calls` fields SHALL NOT be consulted when a usable state slice is present. User turns carry no such structure, so their flat native `content` is sufficient.

A rehydrating download SHALL be judged by the bytes it returns, not by the status it reports. A
download that completes without raising but carries **no bytes** SHALL count as a failure and take
the same fail-closed path as one that raises. Trusting the status here would write `base64: ""`
onto the block and send an empty image to the model, with nothing logged and nothing visible in the
reconstructed message — the one download outcome that would otherwise lose an image silently.

The system message provided by the DIAL request SHALL continue to be ignored on reconstruction; the app's own system prompt is supplied to `create_agent` directly.

#### Scenario: Assistant turn with state replays the full slice
- **WHEN** a request includes an assistant message whose `custom_content.state["messages"]` holds an encoded slice of `AIMessage` / `ToolMessage` entries
- **THEN** the reconstructed history at that position SHALL be exactly `messages_from_dict(...)` of that slice, in order, and the DIAL message's native `content` and `tool_calls` fields SHALL NOT be consulted

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

#### Scenario: An empty download is a failure, not an empty image
- **WHEN** the download of a referenced DIAL file completes without raising but returns no bytes (e.g. DIAL core answers `HTTP 200` with an empty body for a file whose stored content is gone)
- **THEN** the image block SHALL be replaced by the same `TextContentBlock` placeholder used for a raising download, the failure SHALL be logged server-side at WARNING, and the block SHALL NOT be left as an image carrying an empty `base64` value
