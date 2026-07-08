## 1. State & schemas (`app/research/state.py`, `app/research/prompts.py`)

- [x] 1.1 `ResearchState` graph state: `messages` (`Annotated[list[BaseMessage], add_messages]`), `original_query: str`, `plans: list[list[str]]`, `iteration: int`, `report: str | None`
- [x] 1.2 Reviewer structured-output schema `ResearchReview` (`assessment` then `next_steps: list[str]`; empty `next_steps` = complete) — verdict-last per CLAUDE.md
- [x] 1.3 Helper to seed the initial state from `PrepState` (original_query + `plans=[approved plan]` + first plan rendered as a `HumanMessage`)

## 2. Prompts (`app/research/prompts.py`)

- [x] 2.1 Researcher prompt — investigate against the current iteration plan using the MCP tools; read pages not just search; both text+image for visuals; call `finish_iteration` when done; **no report instructions**; reasoning may accompany tool calls
- [x] 2.2 Reviewer prompt — independent coverage judge over query + all plans + accumulated tool results; emit only genuinely uncovered next steps (do not expand scope); empty = complete
- [x] 2.3 Report prompt — final cited report from query + plans + tool messages; carry over the `## Formatting` rules (Markdown structure, inline `[doc <id>, page <ix>]`, Sources table) from the old `app/prompts.py`

## 3. Researcher node (`app/research/tools.py`, `app/research/middleware.py`, `app/research/nodes.py`)

- [x] 3.1 Move MCP-client construction + `hoist_defs_to_root` wiring + `enable_tool_error_handling` out of `app/agent.py` into `app/research/tools.py` (reused, not duplicated)
- [x] 3.2 `finish_iteration` sentinel tool — no args, `return_direct=True`, returns a fixed sentinel string
- [x] 3.3 `ForceToolChoiceMiddleware` — async `awrap_model_call` → `handler(request.override(tool_choice="any"))`
- [x] 3.4 `build_researcher_agent(...)` → `create_agent` over MCP tools + `finish_iteration`, with `ForceToolChoiceMiddleware`, researcher prompt; per-turn `recursion_limit` step cap set on the graph run
- [x] 3.5 Researcher node = the compiled agent added directly as a subgraph node (subgraph composition worked; fallback not needed)

## 4. Reviewer & report nodes (`app/research/nodes.py`)

- [x] 4.1 Reviewer node — `with_structured_output(ResearchReview)`; on non-empty `next_steps`, append to `plans` and inject a plan `HumanMessage`; increment iteration accounting
- [x] 4.2 Report node — streamed `get_chat_model(...)` call; write report into `state["report"]`; its tokens are the only node text routed to assistant content

## 5. Graph assembly (`app/research/graph.py`)

- [x] 5.1 `StateGraph(ResearchState)` with nodes `researcher`, `reviewer`, `report`; no checkpointer, no interrupts
- [x] 5.2 Edges: `START → researcher → reviewer`; conditional `reviewer → researcher` (next plan non-empty AND `iteration < max_research_iterations`) else `→ report`; `report → END`
- [x] 5.3 `build_research_graph(...)` compiles and returns the graph

## 6. Per-turn runner & handoff (`app/research/runner.py`, `app/completion.py`, preparation runner)

- [x] 6.1 `ResearchRunner` — `astream(stream_mode=["updates","messages"], subgraphs=True)`; render researcher tool stages (reuse `DialStageToolCallFormatter` / `PendingToolCall`); append to `choice` only `report`-node `messages` chunks; suppress researcher/reviewer text; dedupe messages by id across the subgraph/parent emissions
- [x] 6.2 Same-turn handoff: after the preparation agent run, if `research_started` became true this turn, seed and run the research graph on the same `Choice` (coordinator lives in `app/completion.py`)
- [x] 6.3 Persist the combined `DialState` once at turn end (preparation slice + research slice; `preparation` carries `research_started=True`); keep refuse-after-launch for a later turn
- [x] 6.4 Attach the Opik tracer to the research graph run (reuse `build_opik_tracer` / `extract_thread_id`)

## 7. Settings & cleanup

- [x] 7.1 `settings.py`: `AgentSettings.max_reflections` → `max_research_iterations` (env `MAX_RESEARCH_ITERATIONS`, default 10, ge 1)
- [x] 7.2 `.env.example`: replace `MAX_REFLECTIONS` doc with `MAX_RESEARCH_ITERATIONS`
- [x] 7.3 Delete `app/agent.py` (`AgentRunner`), `utils/reflection.py` (`ReflectionMiddleware`), and the two-phase `app/prompts.py` system prompt (report formatting moved into `app/research/prompts.py`)
- [x] 7.4 `app/completion.py`: drop the disabled-research import note; wire the handoff

## 8. Verify

- [x] 8.1 `make format && make lint` (ruff, black, isort, mypy clean)
- [x] 8.2 `openspec validate research-execution-loop --strict` passes
- [x] 8.3 Manual (via `evals/send_conversation.py`, server launched): clear query → plan → approve → research stages stream → cited report (with Sources table) in the same turn — 22 tool stages, 83 MCP calls, ~2.3 min
- [x] 8.4 Loop-back decision (`route_after_review`) covered by unit tests for the continue/stop/cap cases; the live run completed in one iteration (reviewer returned empty `next_steps`), so the multi-iteration loop-back was unit-verified, not yet live-exercised
- [x] 8.5 Manual: a message sent after research completed is refused with "start a new conversation"
- [x] 8.6 Manual: researcher never emitted a free-form report (forced tool choice); `finish_iteration` ended the iteration cleanly (no premature report observed)
- [x] 8.7 Unit: `tests/test_research_dispatch.py` (report-only content routing, finish_iteration stage suppression, injected-plan persistence, id dedupe) and `tests/test_research_routing.py` (loop edge)
