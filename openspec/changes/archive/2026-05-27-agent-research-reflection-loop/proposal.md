## Why

Today the per-request ReAct agent stops as soon as the model produces a tool-less message, so the depth of research is entirely at the model's discretion and the agent often answers before fully covering the planned analytical dimensions. We want a thin reflection loop that (a) challenges the model to find gaps and keep researching, and (b) cleanly separates research from a single final report-generation step — without building the full planner/researcher graph yet.

## What Changes

- Introduce a **two-phase contract** in the system prompt: a *research phase* (always uses tools; emits a short tool-less "research complete" signal when done) and a *report phase* (writes the final report only when explicitly asked). **BREAKING** to current behavior: the model no longer writes the report as its first tool-less message — the report is deferred until prompted.
- Add a new **`ReflectionMiddleware`** (langchain `AgentMiddleware`, `after_model` hook) that injects tagged "fake user" messages and uses `jump_to: "model"` to loop the agent back, with no new LangGraph nodes:
  - a **`gap_check`** nudge after a tool-less message that followed research — asks the model to verify plan coverage and either keep researching or briefly confirm completion;
  - a **`report_request`** nudge once the model produces two sequential tool-less messages (declined to research after a nudge) — asks it to write the final report.
- The loop is **repeatable** (`research → gap_check → research → gap_check → …`) and bounded by a configurable cap (`MAX_REFLECTIONS`, default 10); hitting the cap forces a `report_request` (so the user always gets a report, never a bare exit).
- Wire the middleware into `agent.py`, and capture injected nudges into the persisted message buffer so cross-turn history reconstructs as `ai → human → ai`.
- Streaming behavior is unchanged (every `AIMessage`'s text still streams inline); hiding/redirecting reflection turns is explicitly deferred.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `dial-agent-with-mcp`:
  - **Modify** "Tool-calling agent over MCP-loaded tools": the agent still has only MCP tools, but the prohibition on planning/reflection middleware is relaxed to allow this in-process reflection middleware (no subagents, skills, or persistent memory). Add scenarios for the deferred-report contract and the research → gap-check loop.
  - **Add** a new "Reflection-driven research/report loop" requirement describing the phase contract, the two tagged nudges, the per-UI-turn state machine, the `MAX_REFLECTIONS` cap forcing a report, and exit when a report has been requested.
  - **Modify** "Tool messages persisted via DIAL custom_content state" / "Reconstruction of LangChain history from DIAL request": injected `gap_check` / `report_request` nudges are persisted into `custom_content.state["messages"]` and reconstructed as tagged `HumanMessage`s, so history replays as `ai → human → ai`; the per-UI-turn scope is the slice after the last *real* (untagged) user message.

## Impact

- **Code**:
  - `src/dial_deep_research/app/prompts.py`: add a "Research phases" section (deferred report) and reword §Research strategy point 2 (plan-preamble) to stay consistent.
  - `src/dial_deep_research/utils/reflection.py` (new): `ReflectionMiddleware` with the `after_model` decision table, the two nudge texts, tags `gap_check` / `report_request`, a `max_reflections` constructor arg, and a no-op `_token_budget_exhausted` stub.
  - `src/dial_deep_research/settings.py`: new `AgentSettings` class (`env_prefix=""`) with `max_reflections: int = Field(default=10, ge=1)` → env var `MAX_REFLECTIONS`; instantiated as `agent_settings`.
  - `src/dial_deep_research/app/agent.py`: add `ReflectionMiddleware(max_reflections=agent_settings.max_reflections)` to the `create_agent` middleware list; guard `run()`'s `updates` dispatch against `None` node updates (a returning-`None` `after_model` emits a `None` update value); add a `HumanMessage` branch + `_handle_human_message` that buffers nudges for persistence and sets `_separator_pending`.
  - `.env.example`: document `MAX_REFLECTIONS` (research-depth/cost knob a contributor may tune).
- **Dependencies**: none (langgraph 1.1.10 / langchain 1.2.15 already provide `AgentMiddleware`, `hook_config`, and `jump_to`).
- **Configuration**: new optional `MAX_REFLECTIONS` env var (default 10) caps the per-turn gap-check reflections.
- **DIAL surface**: `assistant.message.content` now includes the intermediate "research complete" signal text plus the final report (still excluding tool calls/results). `custom_content.state["messages"]` additionally carries the tagged nudges. Stages unchanged.
- **Tests**: unit tests for the `after_model` decision table and per-UI-turn scoping; optionally one `GenericFakeChatModel` end-to-end test for the loop and nudge capture.
