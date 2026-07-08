## 1. State & schemas (`app/history.py`, `app/preparation/prompts.py`)

- [x] 1.1 `PrepState` pydantic model (`current_query`, `clarification`, `plan`, `plan_approved`, `research_started`), plus the `Clarification` and `Plan` nested models — all in `app/history.py`; readiness is derived by the tools, not exposed as `PrepState` properties
- [x] 1.2 LLM check schemas (in `app/preparation/prompts.py`): `QueryReviewResponse` (`assessment`, `questions`) and `PlanReviewResponse` (`assessment`, `recorded_plan_matches`, `user_approved_a_plan`, `failure_reason`) with `approved` as a computed property — true only when both checks hold, so the verdict can't contradict its preconditions (no emitted verdict field, no model validator)
- [x] 1.3 `PrepState` (de)serialization as the `preparation` field of the unified `DialState` under `custom_content.state` (load latest, fail soft to a fresh state)

## 2. Prompts (`app/preparation/prompts.py`)

- [x] 2.1 Preparation agent system prompt — the clarify → plan → approve → launch contract; present questions/plan in natural language; fold answers into a refined query and re-call `update_query`; on stale-plan refusal, re-`update_plan` then re-`approve_plan`; only `start_research` once approved; answer general side questions and steer back
- [x] 2.2 Clarity-check prompt (query-only; intent/scope/region/period/focus; no obvious questions; no data-source assessment; no injected defaults)
- [x] 2.3 Approval-check prompt (read full conversation + recorded plan; assessment, recorded-plan-matches and user-approved, and a user-facing failure summary of what's needed)

## 3. Tools (`app/preparation/tools.py`)

- [x] 3.1 A holder/factory that builds the four tools closing over a per-turn `PrepState` and the LLM config
- [x] 3.2 `update_query(query)` — set query, reset plan + approval, run clarity check, record `clarification`
- [x] 3.3 `update_plan(steps)` — gate via `_query_failure_reason` (raise `ToolException` otherwise); record plan, reset approval
- [x] 3.4 `approve_plan()` — gate via `_query_failure_reason` + plan present; read history via `ToolRuntime`; run approval check; set `plan_approved` on success; never edit plan
- [x] 3.5 `start_research()` — hard gate: query gate (`_query_failure_reason`) + plan recorded + approved (raise naming the missing precondition); set `research_started`; return ready-to-research summary
- [x] 3.6 Mark the tools `handle_tool_error=True` so gate `ToolException`s reach the agent as error `ToolMessage`s

## 4. Agent build (`app/preparation/agent.py`)

- [x] 4.1 `build_prep_agent(state, agent_name, today_date)` → `create_agent` with the prep prompt and the four tools (no MCP, no checkpointer, no middleware)

## 5. Per-turn runner (`app/preparation/runner.py`)

- [x] 5.1 Load `PrepState` from the latest assistant message; if `research_started`, emit the refuse message and return
- [x] 5.2 Reconstruct history (`app/history.py`), build the agent over a holder seeded with the loaded `PrepState`, `astream` it
- [x] 5.3 Stream assistant text token-by-token; render control-tool calls as DIAL stages (reuse `DialStageToolCallFormatter`); attach the Opik tracer
- [x] 5.4 Persist the unified `DialState` (`{messages, preparation}`) via `choice.set_state` at turn end

## 6. Wiring & cleanup

- [x] 6.1 `app/completion.py` — drive the preparation runner (drop the old import note as needed; research path stays commented retained)
- [x] 6.2 `app/factory.py` — remove the eager graph build (`get_graph`)
- [x] 6.3 Delete `app/preparation/graph.py`; remove LangGraph `StateGraph`/`interrupt`/`MemorySaver`/`Command` usage
- [x] 6.4 Delete the superseded root design doc `clarification-flow-design.md`
- [x] 6.5 `__main__.py` / comments — drop the single-worker-only checkpointer caveat (no longer applies)

## 7. Verify

- [x] 7.1 `make format && make lint` (ruff, black, isort, mypy clean)
- [x] 7.2 `openspec validate clarification-and-plan-alignment` (passes `--strict`)
- [x] 7.3 Manual (via `evals/send_conversation.py`): ambiguous query → questions → answer → plan → revision → approval → ready-to-research summary
- [x] 7.4 Manual: specific query → no questions → straight to plan
- [x] 7.5 Manual: message after launch → refuse-after-launch
- [x] 7.6 Manual: `start_research` blocked before approval; `update_plan` blocked before clarification; approval validator can't be forced (verified by exercising the tools directly)
- [x] 7.7 Manual: a general side question mid-flow is answered, then the flow continues (state unchanged)
