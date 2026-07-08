## MODIFIED Requirements

### Requirement: Assistant message content contains only model text
The DIAL response message content SHALL contain only the agent's natural-language assistant text. Tool calls, tool results, and intermediate agent messages SHALL be conveyed via stages (for UI display) and via `assistant.custom_content.state["messages"]` (for cross-turn replay) and SHALL NOT appear in the assistant message content.

#### Scenario: Tool-using turn
- **WHEN** the agent makes one or more tool calls before producing its final answer
- **THEN** the DIAL response content SHALL contain only the final assistant text and SHALL NOT contain serialized tool calls, tool results, or intermediate agent reasoning

#### Scenario: Cross-turn replay of tool messages
- **WHEN** a follow-up chat completion request arrives after an earlier tool-using turn
- **THEN** the second turn's agent SHALL receive the prior turn's intermediate `AIMessage(tool_calls=…)` and `ToolMessage(...)` slice plus the prior turn's final `AIMessage` as conversation history, reconstructed from the prior assistant message's `custom_content.state["messages"]` field, in the original order, instead of being limited to prior assistant text

## ADDED Requirements

### Requirement: Tool messages persisted via DIAL custom_content state

For every chat completion request, the app SHALL accumulate the full ordered sequence of `AIMessage` and `ToolMessage` instances observed during the agent's `astream` run — every intermediate `AIMessage` carrying `tool_calls`, every `ToolMessage` returned by a tool, and the final `AIMessage` carrying the natural-language answer — and SHALL persist that sequence into the response by serializing it via `langchain_core.messages.messages_to_dict` and calling `choice.set_state({"messages": [...]})`. DIAL SHALL store the resulting list under `assistant.custom_content.state.messages` on the assistant message produced by the request. The DIAL `assistant.tool_calls` and `assistant.tool_call_id` native fields SHALL NOT be populated by the app; the `custom_content.state["messages"]` blob is the sole authoritative carrier of tool-call structure across turns.

#### Scenario: Multi-step tool loop is fully persisted
- **WHEN** a turn produces the sequence `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[Y]) → ToolMessage(Y_result) → AIMessage(content="...")` (multi-step ReAct)
- **THEN** the assistant message persisted by DIAL SHALL carry, under `custom_content.state.messages`, the same five entries in the same order, each encoded as a `messages_to_dict` element with the matching `type` discriminator (`ai`, `tool`, `ai`, `tool`, `ai`); and the assistant message's native `content` field SHALL carry only the final `AIMessage`'s text

#### Scenario: Single-step tool loop is fully persisted
- **WHEN** a turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(content="...")`
- **THEN** `custom_content.state.messages` SHALL carry exactly those three entries in order (`ai`, `tool`, `ai`)

#### Scenario: No-tool turn is fully persisted
- **WHEN** a turn produces only a single final `AIMessage(content="...")` with no tool calls
- **THEN** `custom_content.state.messages` SHALL carry exactly one `ai` entry whose content matches the final assistant text

### Requirement: Reconstruction of LangChain history from DIAL request

On each incoming chat completion request, the app SHALL reconstruct the LangChain message history fed to the agent by walking `request.messages` in order and, for each message:
- if `role == user`, emitting a `HumanMessage` whose content is taken from the DIAL message's native `content` field;
- if `role == assistant` AND `custom_content.state["messages"]` is present and non-empty, emitting `messages_from_dict(custom_content.state["messages"])` (the full intermediate-plus-final slice) instead of consulting the native `content` or `tool_calls` fields;
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
