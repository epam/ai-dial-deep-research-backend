## 1. System prompt — two-phase contract

- [x] 1.1 In `app/prompts.py`, add a "Research phases" section: research phase always uses tools and emits a short tool-less "research complete" signal when done; report phase writes the final report only when explicitly asked; the model never moves itself between phases.
- [x] 1.2 Add the explicit instruction "do not write the final report until asked" so the first tool-less message is a completion signal, not the report. Phrase the completion cue softly, e.g. "if you think you are done, do not emit tool calls; wait to be asked for the report".
- [x] 1.3 Reword §Research strategy point 2 (plan preamble) to stay consistent with the deferred-report contract.

## 2. Configuration

- [x] 2.1 In `settings.py`, add an `AgentSettings(BaseSettings)` class (`env_prefix=""`) with `max_reflections: int = Field(default=10, ge=1)` (no alias) and instantiate `agent_settings = AgentSettings()`.
- [x] 2.2 Document `MAX_REFLECTIONS` in `.env.example` (research-depth/cost knob).

## 3. ReflectionMiddleware

- [x] 3.1 Create `utils/reflection.py` with `ReflectionMiddleware(AgentMiddleware)` taking `max_reflections: int` in `__init__`, tags `gap_check` / `report_request`, and the two nudge prompt texts.
- [x] 3.2 Implement `after_model` decorated `@hook_config(can_jump_to=["model"])` returning `{"messages": [HumanMessage(name=...)], "jump_to": "model"}` or `None`.
- [x] 3.3 Implement `_current_turn_start` (index of the last `HumanMessage` whose `name` is not a reflection tag) and scope all checks to that slice.
- [x] 3.4 Implement the decision table in order: `tool_calls` → None; `report_request` already present → None; `gap_check` count ≥ `max_reflections` → inject `report_request`; previous `AIMessage` tool-less → inject `report_request`; else → inject `gap_check`.
- [x] 3.5 Add the no-op `_token_budget_exhausted(state) -> False` stub with a TODO for a future per-turn token budget.

## 4. AgentRunner wiring

- [x] 4.1 In `app/agent.py`, add `ReflectionMiddleware(max_reflections=agent_settings.max_reflections)` to the `create_agent` middleware list.
- [x] 4.2 In `run()`'s `updates` dispatch, guard each `node_update` with `isinstance(node_update, dict)` (a returning-`None` `after_model` emits a `None` update value).
- [x] 4.3 Add a `HumanMessage` branch in the `updates` dispatch calling a new `_handle_human_message` that appends the nudge to `self._messages` (for persistence) and sets `_separator_pending = True`; do not append nudge text to visible content.
- [x] 4.4 Import `HumanMessage`, `ReflectionMiddleware`, and `agent_settings` in `app/agent.py`.

## 5. Tests

- [x] 5.1 Unit-test `ReflectionMiddleware.after_model` decision table: mid-research (`tool_calls`) → None; tool-less after research → `gap_check`; two sequential tool-less → `report_request`; exit when `report_request` already present → None; cap reached (small `max_reflections`) → forces `report_request`.
- [x] 5.2 Unit-test per-UI-turn scoping: a history with a prior turn's trailing tool-less `AIMessage` + tagged nudges followed by a new untagged user message yields `gap_check` (not a spurious exit) on the new turn's first tool-less message.
- [x] 5.3 End-to-end test with `GenericFakeChatModel`: confirm the `research-complete → gap_check → confirm → report_request → report → end` loop runs and that injected nudges surface on the `updates` stream and are captured into `self._messages`.

## 6. Verify

- [x] 6.1 Run `make format` and `make lint` (or repo equivalent) and fix findings.
- [x] 6.2 Run the unit test suite and confirm existing streaming/persistence/history tests stay green.
- [x] 6.3 Run `openspec validate agent-research-reflection-loop --strict` and resolve any issues.
- [x] 6.4 Smoke-test the prompt against the deployed model: confirm the model emits a short tool-less completion *signal* (not a full report) on first completion, and writes the report only after the `report_request` nudge. Tune the prompt if it writes the report prematurely.
