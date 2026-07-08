## Why

The **clarification-and-plan-alignment** change put a preparation gate in front of
research: the app clarifies the query, aligns on a plan, and `start_research`
stops at a ready-to-research summary. Research execution was deferred (its task
8.1: "Launch research→reflect→report from `start_research`"). This change is that
follow-up — it re-enables research, but **not** as the old single-agent loop.

The retained research path (`AgentRunner` + `ReflectionMiddleware`) is one
`create_agent` loop that does research *and* report in two prompt-defined phases.
`data/issues.md` records its problems: the model has "no technical possibility to
prevent" it writing the report before reflection (we only ask it nicely in the
prompt), reflection reasoning is tangled with research reasoning so the gap-check
is not independent, and there is no clean control over phase transitions. The
issues list asks directly to "refactor research to use langgraph nodes for control
flow" and to "use separate prompts and contexts for research and reflection".

## What Changes

- **Replace the single-agent reflection loop with a deterministic research graph**
  (`langgraph.StateGraph`, no checkpointer, no `interrupt()`) with three nodes:
  - **researcher** — a `create_agent` tool-calling loop over the MCP tools that
    acts on the current iteration plan and the accumulated history. It is bound
    with **forced tool choice** (`tool_choice="any"` via middleware) so it can
    never emit a free-form terminal summary or report; when it has nothing more to
    research it calls a no-op **`finish_iteration`** sentinel tool (`return_direct`)
    that ends the iteration. The researcher has no report instructions at all.
  - **reviewer** — an independent structured LLM call that reads the original
    query, all prior iteration plans, and the accumulated researcher messages, and
    decides whether the findings cover every plan item. It emits the plan for the
    next iteration (an empty plan means research is complete). It is prompted to add
    only genuinely uncovered work, and the loop is bounded by a hard cap.
  - **report** — a streamed LLM call that writes the final cited report from the
    original query, the iteration plans, and the accumulated tool messages. This is
    the only node whose text becomes the user-visible assistant content.
- **Control flow is deterministic graph edges, not the model's discretion:**
  `START → researcher → reviewer → (researcher if the next plan is non-empty and
  under the cap, else report) → END`. The model cannot skip reflection or jump to
  the report early.
- **Same-turn handoff.** When the preparation agent's `start_research` fires (plan
  approved), the research graph runs in the **same** chat-completion turn, seeded
  with the approved query and plan, and streams the report as that turn's assistant
  message. The first iteration plan is exactly the approved `PrepState.plan`.
- **Separate contexts.** Researcher, reviewer, and report each get their own focused
  prompt; reviewer reasoning is independent of researcher reasoning, per the
  `issues.md` ask.
- **BREAKING (behavioral, pre-prod):** the old two-phase system prompt, the
  research-complete signal, and the `gap_check` / `report_request` nudges are gone.
  During research only the report streams to assistant content (researcher and
  reviewer output surface as tool stages / progress, not as answer text). The
  `MAX_REFLECTIONS` setting is repurposed as the research-iteration cap
  (`max_research_iterations`); `ReflectionMiddleware` and `AgentRunner` are deleted.

## Capabilities

### New Capabilities
- `research-execution`: the deterministic research graph launched after plan
  approval — researcher (forced-tool-choice `create_agent` + `finish_iteration`),
  reviewer (independent re-planning, cumulative coverage, hard iteration cap),
  report (streamed cited report); same-turn handoff seeded by the approved query +
  plan; only the report node's text becomes assistant content; autonomous
  single-turn execution.

### Modified Capabilities
- `dial-agent-with-mcp`: the per-request research agent is now the **researcher
  node** of the research graph (forced tool choice + `finish_iteration`), launched
  by the preparation agent's `start_research` rather than running directly on the
  first message; the **Reflection-driven research/report loop** requirement is
  removed (replaced by `research-execution`); persisted `custom_content.state`
  carries the research graph's messages (researcher `AIMessage`/`ToolMessage`s,
  the injected next-iteration plan `HumanMessage`s, and the final report) instead
  of the reflection nudges.

## Impact

- **Code:**
  - New package `app/research/`: `state.py` (graph state), `prompts.py`
    (researcher / reviewer / report prompts + the reviewer schema), `tools.py`
    (`finish_iteration` + MCP-client/tool-prep helpers moved from `app/agent.py`),
    `middleware.py` (`ForceToolChoiceMiddleware`), `nodes.py` (researcher / reviewer
    / report node builders), `graph.py` (`StateGraph` assembly), `runner.py`
    (per-turn streaming driver).
  - `app/completion.py` / preparation runner: after `start_research` sets
    `research_started` in the turn, run the research graph on the same `Choice`;
    persist the combined `DialState` once at turn end. Refuse-after-launch still
    applies to a *later* turn.
  - **Deleted:** `app/agent.py` (`AgentRunner`), `utils/reflection.py`
    (`ReflectionMiddleware`), and the two-phase `app/prompts.py` system prompt
    (replaced by the per-node prompts). MCP-client construction, `hoist_defs_to_root`
    wiring, and `enable_tool_error_handling` are reused (moved into `app/research/`).
  - `settings.py`: `AgentSettings.max_reflections` → `max_research_iterations`
    (env `MAX_RESEARCH_ITERATIONS`); optionally a per-iteration researcher step cap.
- **State:** `custom_content.state` stays `{messages, preparation}`; on a research
  turn `messages` additionally carries the research graph's slice. Image content in
  tool messages is uploaded to DIAL files before persistence by the existing
  `multimodal-tool-output` path.
- **Dependencies:** none new (uses `langgraph.StateGraph` / `ToolNode`, already a
  dependency via `create_agent`).
- **Out of scope (future changes):** wall-clock / token budget graceful shutdown
  (the cap is iteration-count only today); a graceful report on MCP failure mid-run;
  summarizing/compacting the accumulated context on very long runs (today the
  context grows unbounded across iterations, per the design decision to not
  summarize); suppressing internal researcher/reviewer stages from the UI.
