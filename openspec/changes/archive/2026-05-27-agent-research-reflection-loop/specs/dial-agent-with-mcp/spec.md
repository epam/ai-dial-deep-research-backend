## MODIFIED Requirements

### Requirement: Tool-calling agent over MCP-loaded tools
On each chat completion request the app SHALL construct a fresh MCP client, fetch the current tool list, and use those tools to construct a fresh LangChain tool-calling agent which is run to completion. The agent SHALL have access only to MCP-loaded tools — no built-in tools, subagents, skills, or persistent memory. In-process LangChain `AgentMiddleware` that injects messages into the agent's state and redirects the agent's own control flow within a single run (specifically the reflection middleware introduced by **Reflection-driven research/report loop**) is permitted; external planning subsystems, subagents, on-demand skills, and persistent cross-session memory remain out of scope.

The MCP client SHALL NOT be cached across requests, the app SHALL NOT open a long-lived SSE listening stream on the MCP endpoint (the GET-method stream that the Streamable HTTP transport reserves for server-initiated notifications), and the app SHALL NOT issue or retain an `Mcp-Session-Id`. Tool-list freshness across requests is therefore achieved by re-polling `tools/list` at the start of every turn, not by subscribing to `notifications/tools/list_changed`. This matches the generic-RAG server's deployment with `stateless_http=True`, under which the server does not register its GET SSE route, does not assign a session id, and therefore cannot deliver unsolicited server-initiated notifications to the client; persistent-session features (long-lived sessions, `Mcp-Session-Id`, `Last-Event-ID` resumability, `notifications/tools/list_changed`, `notifications/resources/*`, `notifications/prompts/list_changed`) are out of scope for this capability.

#### Scenario: Agent invokes an MCP tool
- **WHEN** the user message is best answered by calling an MCP-exposed tool
- **THEN** the agent SHALL emit a tool call, the MCP server SHALL execute the tool, and the agent SHALL incorporate the result into its final assistant message

#### Scenario: Agent answers without tool calls
- **WHEN** the user message can be answered from the agent's prior context without an MCP tool call
- **THEN** the response SHALL emit no tool stages, and the turn SHALL still pass through the reflection loop (research-complete signal → `gap_check` → `report_request`) before the model produces the final report, per **Reflection-driven research/report loop**

#### Scenario: Per-request agent and MCP scoping
- **WHEN** the MCP server's tool list changes between two chat completion requests (e.g. the generic-RAG MCP server is redeployed)
- **THEN** the second request SHALL discover and use the new tool list without restarting the dial-deep-research process

#### Scenario: Tool-list refresh via re-polling, not via push
- **WHEN** the MCP server changes its tool list between two chat completion requests
- **THEN** the app SHALL learn about the change by re-issuing `tools/list` as part of the next request's fresh-client construction and SHALL NOT rely on receiving a `notifications/tools/list_changed` push; the app SHALL NOT issue an HTTP GET against the MCP endpoint to subscribe to server-initiated notifications

#### Scenario: No session reuse across requests
- **WHEN** the app processes two chat completion requests in sequence
- **THEN** the app SHALL construct a new MCP client for the second request rather than reusing the first request's, the second request's MCP traffic SHALL NOT carry an `Mcp-Session-Id` derived from the first request, and any in-flight progress / logging notifications received during the first request's POST SSE response SHALL have terminated with that request

### Requirement: Tool messages persisted via DIAL custom_content state

For every chat completion request, the app SHALL accumulate the full ordered sequence of `AIMessage`, `ToolMessage`, and injected reflection `HumanMessage` instances observed during the agent's `astream` run — every intermediate `AIMessage` carrying `tool_calls`, every `ToolMessage` returned by a tool, every reflection nudge (`gap_check` / `report_request` tagged `HumanMessage`) injected by the reflection middleware, and the final `AIMessage` carrying the natural-language answer — and SHALL persist that sequence into the response by serializing it via `langchain_core.messages.messages_to_dict` and calling `choice.set_state({"messages": [...]})`. The reflection nudges SHALL be captured from the `updates` stream and buffered in run order so the persisted slice interleaves them at the positions the model saw them, preserving an `ai → human → ai` shape across the turn; the nudges SHALL NOT be appended to the user-visible assistant `content`. Before serialization, the app SHALL traverse every message's `content` and, for every LangChain v1 `ImageContentBlock` carrying a `base64` field, replace the inline data with a `url` reference produced by the **Tool-message image content uploaded to DIAL files before persistence** requirement, so that the persisted state SHALL NOT contain image byte payloads. DIAL SHALL store the resulting list under `assistant.custom_content.state.messages` on the assistant message produced by the request. The DIAL `assistant.tool_calls` and `assistant.tool_call_id` native fields SHALL NOT be populated by the app; the `custom_content.state["messages"]` blob is the sole authoritative carrier of tool-call structure across turns.

The **final** `AIMessage` SHALL be persisted into this slice too — not just the intermediate tool-call messages — because the next turn cannot recover it from the native `assistant.content` field. Per **Assistant message content contains only model text**, that native field is a flat concatenation of every streamed text segment (intermediate reasoning, `"\n\n"` separators, and the final answer) and carries no boundaries from which the original `AIMessage` / `ToolMessage` structure could be split back out. The persisted slice is therefore the only faithful carrier of the whole assistant turn across requests; the native `content` field is for human display only and SHALL NOT be parsed back into messages.

#### Scenario: Multi-step tool loop is fully persisted
- **WHEN** a turn produces the sequence `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(tool_calls=[Y]) → ToolMessage(Y_result) → AIMessage(content="...")` (multi-step ReAct)
- **THEN** the assistant message persisted by DIAL SHALL carry, under `custom_content.state.messages`, the same five entries in the same order, each encoded as a `messages_to_dict` element with the matching `type` discriminator (`ai`, `tool`, `ai`, `tool`, `ai`); and the assistant message's native `content` field SHALL carry the concatenation of every streamed text segment (the text of each intermediate `AIMessage` plus the final answer, joined by `"\n\n"` separators), per **Assistant message content contains only model text**

#### Scenario: Single-step tool loop is fully persisted
- **WHEN** a turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(content="...")`
- **THEN** `custom_content.state.messages` SHALL carry exactly those three entries in order (`ai`, `tool`, `ai`)

#### Scenario: No-tool turn is fully persisted
- **WHEN** a turn produces only a single final `AIMessage(content="...")` with no tool calls
- **THEN** `custom_content.state.messages` SHALL carry exactly one `ai` entry whose content matches the final assistant text

#### Scenario: Reflection nudges are persisted between the messages they separated
- **WHEN** a turn produces `AIMessage(tool_calls=[X]) → ToolMessage(X_result) → AIMessage(content="research complete") → [injected gap_check] → AIMessage(content="confirmed") → [injected report_request] → AIMessage(content="<report>")`
- **THEN** `custom_content.state.messages` SHALL carry all seven entries in run order — `ai`, `tool`, `ai`, `human(name="gap_check")`, `ai`, `human(name="report_request")`, `ai` — so the next turn reconstructs an `ai → human → ai` alternation, and the two `human` nudge entries SHALL NOT appear in the assistant message's native `content`

#### Scenario: Multimodal tool loop persists with image URLs, not image bytes
- **WHEN** a turn produces a `ToolMessage` whose `content` is a list containing one or more `{type: "image", base64, mime_type}` blocks
- **THEN** the entry persisted under `custom_content.state.messages` for that `ToolMessage` SHALL contain the same blocks rewritten to the `{type: "image", url, mime_type}` form (with `base64` absent and `url` referencing a DIAL files object); and the size of the serialized state blob SHALL NOT include the original image byte payload

## ADDED Requirements

### Requirement: Reflection-driven research/report loop

The app SHALL run the agent in two prompt-defined phases — a **research phase** and a **report phase** — and SHALL steer the transition between them with an in-process `AgentMiddleware` (the *reflection middleware*) that injects tagged `HumanMessage` nudges and redirects control flow back to the model via `jump_to: "model"`, without adding any LangGraph node.

The system prompt SHALL instruct the model that, in the research phase, it investigates using tools and, when it believes research is complete, emits a short message **with no tool calls** stating that research is complete — and that it SHALL NOT write the final report until explicitly asked. The model's first tool-less `AIMessage` is therefore a research-complete *signal*, not the report. The report SHALL be produced only in the report phase, when prompted, following the existing `## Formatting` rules.

The reflection middleware SHALL act in its `after_model` hook, scoped to the **current UI turn** — the slice of `state["messages"]` after the last *real* user message, where a real user message is a `HumanMessage` whose `name` is neither `gap_check` nor `report_request`. Within that scope it SHALL apply this decision table, in order:
1. if the latest `AIMessage` carries `tool_calls`, it SHALL take no action (research in progress);
2. if a `report_request` nudge already exists in the current turn, it SHALL take no action (the latest tool-less `AIMessage` is the report — the agent ends);
3. if the number of `gap_check` nudges already injected in the current turn is greater than or equal to the configurable reflection cap (the `MAX_REFLECTIONS` app setting, default 10), it SHALL inject a `report_request` nudge and jump back to the model (forcing a report rather than ending without one);
4. if the previous `AIMessage` in the current turn is also tool-less (the model declined to research after a nudge), it SHALL inject a `report_request` nudge and jump back to the model;
5. otherwise (the latest tool-less `AIMessage` was preceded by research), it SHALL inject a `gap_check` nudge and jump back to the model.

The `gap_check` nudge SHALL ask the model to verify that the plan is fulfilled and to identify any gaps or under-explored angles; if gaps remain it SHALL continue researching by calling tools, and if research is genuinely complete it SHALL NOT call any tools but briefly confirm, still without writing the report. The `report_request` nudge SHALL instruct the model to write the final report per the `## Formatting` rules. Both nudges SHALL be tagged via the `HumanMessage` `name` field (`gap_check` / `report_request`) so they are distinguishable from real user messages for turn-scoping and decision-table purposes. The middleware MAY consult a `_token_budget_exhausted` check that is a no-op today (reserved for a future per-turn token budget).

The reflection cap SHALL be configurable through the `MAX_REFLECTIONS` environment variable (an optional integer setting, default 10, minimum 1) and SHALL be supplied to the reflection middleware at construction time so it is not hard-coded.

This capability DEPENDS on the model honoring the system-prompt contract — in particular, deferring the report (emitting a tool-less completion *signal* rather than the report itself) and confirming completion without tool calls when it has nothing left to research. The phase machine is structural (it keys off `tool_calls` presence and tagged nudges), so it cannot itself force semantic compliance. When the model violates the contract (e.g. it writes a full report as its first tool-less message), the loop's termination guarantees — the `report_request`-present exit and the reflection cap — still bound the turn, but the user-visible output MAY contain a premature or duplicated report. The system prompt is therefore the primary control for correct behavior and is expected to be tuned against the deployed model.

Because the report is deferred until the model is prompted for it, EVERY turn — including those needing little or no tool research — SHALL pass through at least one `gap_check` reflection and a `report_request` before the report is produced. The resulting extra model round-trips are an accepted cost of the deep-research workflow, not a defect.

#### Scenario: Reflection cap default and override
- **WHEN** the process starts without `MAX_REFLECTIONS` set, the cap SHALL resolve to 10; **AND WHEN** `MAX_REFLECTIONS` is set to a valid integer ≥ 1, the reflection middleware SHALL use that value as the maximum number of `gap_check` nudges per turn before forcing a `report_request`

#### Scenario: Research-complete signal is not the report
- **WHEN** the model finishes its first research pass and emits a tool-less `AIMessage`
- **THEN** that message SHALL be treated as a research-complete signal, the reflection middleware SHALL inject a `gap_check` nudge and jump back to the model, and the final report SHALL NOT have been produced yet

#### Scenario: Gap-check loop drives further research
- **WHEN** the model responds to a `gap_check` nudge by emitting one or more `AIMessage`s carrying `tool_calls` and then another tool-less `AIMessage`
- **THEN** the reflection middleware SHALL inject another `gap_check` nudge (because research occurred since the last tool-less message) and jump back to the model, allowing the `research → gap_check → research` loop to repeat

#### Scenario: Two sequential tool-less messages trigger the report
- **WHEN** the model produces a tool-less `AIMessage` immediately after a `gap_check` nudge without calling any tools (the previous `AIMessage` in the turn was also tool-less)
- **THEN** the reflection middleware SHALL inject a `report_request` nudge and jump back to the model

#### Scenario: Report request terminates the loop
- **WHEN** a `report_request` nudge already exists in the current turn and the model produces a tool-less `AIMessage` (the report)
- **THEN** the reflection middleware SHALL take no action and the agent SHALL end, with the report as the final assistant message

#### Scenario: Reflection cap forces a report rather than a bare exit
- **WHEN** the number of `gap_check` nudges injected in the current turn reaches `MAX_REFLECTIONS` and the model emits another tool-less `AIMessage`
- **THEN** the reflection middleware SHALL inject a `report_request` nudge (not end the turn), so the user receives a report even at the cap

#### Scenario: Reflection state is scoped per UI turn
- **WHEN** a follow-up request's reconstructed history contains a prior UI turn's trailing tool-less `AIMessage` and tagged nudges, followed by a new real (untagged) user `HumanMessage`, and the model then emits its first tool-less `AIMessage` for the new turn
- **THEN** the reflection middleware SHALL count only nudges after the new real user message (zero so far) and SHALL inject a `gap_check` nudge, not be misled by the previous turn's tool-less messages or nudges
