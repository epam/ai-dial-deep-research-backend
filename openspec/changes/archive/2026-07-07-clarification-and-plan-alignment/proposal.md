## Why

Today the deployment runs straight into the research/reflection loop on the first
user message, with no chance to resolve ambiguity or agree on scope. When the
query is under-specified, that burns a long, expensive research run on the wrong
thing. We want the app to first ask clarifying questions and align with the user
on an initial research plan, and only then run research against the agreed plan.

The first cut of this change built that gate as a **deterministic LangGraph
`StateGraph`** with `clarify` / `plan` phases, `interrupt()`-based pauses, and a
checkpointer. Working through it surfaced two problems worth correcting before we
build further:

- **A deterministic phase graph walls off the conversation.** Each phase has its
  own prompt/context, so the user cannot ask cross-context questions ("what is
  CPI?", "where would you look for that?") and cannot refer back to things they
  said in another phase. That conversational rigidity is the top complaint in
  `data/issues.md` (the "agent — alternative to workflow architecture" section).
- **`interrupt()` + checkpointer carry heavy, fragile machinery.** It forced an
  in-memory `MemorySaver` (single-worker only), a `{thread_id, checkpoint_id}`
  pointer protocol, rewind detection, terminal-checkpoint refusal, and a spike
  that *disproved* fork-on-rewind on the pinned LangGraph version. A lot of code
  to work around the framework.

This change replaces that deterministic graph with a **single-context
tool-calling agent** for the preparation phase. The conversational benefits and
the simplifications both fall out of one decision (see `design.md` for the full
reasoning).

## What Changes

- Replace the clarify/plan `StateGraph` with a **preparation agent**: one
  LangChain `create_agent` tool-calling loop, single context, that drives the
  clarify → plan → approve → launch flow by calling tools. Research execution is
  still **not run** in this change (the launch tool reports readiness and stops).
- **Control lives in the tools, not in the agent's discretion.** The agent reads
  a typed `PrepState` but cannot write it; only the tools mutate it. The launch
  tool hard-gates on `PrepState`, so the agent structurally cannot start research
  on an unclear query or an unapproved plan. The tools are:
  - `update_query(query)` — set/replace the working query (resetting any plan),
    then run an **independent** LLM clarity check on that query alone; records the
    clarifying questions (empty = clear).
  - `update_plan(steps)` — record the agent-authored plan; errors unless the
    clarifications are resolved.
  - `approve_plan()` — an **independent** LLM reads the full conversation and
    decides whether the user approved the plan **and** whether the recorded plan
    still matches the one discussed; sets the approval flag on success. Never
    edits the plan itself.
  - `start_research()` — hard gate; errors (naming the missing precondition)
    unless the query is clear and the plan is approved. Research execution is
    deferred, so on success it emits the ready-to-research summary and stops.
- **Drop the checkpointer, `interrupt()`, and the pointer protocol.** The turn is
  stateless, like the retained research path: the message transcript **and** the
  `PrepState` are persisted in `assistant.custom_content.state` and reconstructed
  each turn. Rewind is handled natively — DIAL truncates the transcript on
  edit/regenerate, so the surviving last assistant message carries the correct
  prior state with no detection code.
- **BREAKING (behavioral, pre-prod):** the persisted `custom_content.state` shape
  changes from the prior `{dr_thread_id, checkpoint_id}` pointer to
  `{messages, preparation}`. Conversations persisted under the pointer shape are not
  resumable; acceptable pre-production. The research `AgentRunner` /
  `ReflectionMiddleware` remain retained-but-not-invoked, as before.

## Capabilities

### New Capabilities
- `clarification-and-plan-alignment`: the pre-research preparation agent —
  single-context tool-calling loop; tool-gated `PrepState` the agent cannot write
  directly; `update_query` / `update_plan` / `approve_plan` / `start_research`
  tools; independent LLM checks for clarity and approval; stateless turns with
  `PrepState` + transcript persisted in DIAL custom state; native rewind via DIAL
  truncation; exit-after-launch (research execution deferred).

### Modified Capabilities
- `dial-agent-with-mcp`: request handling now runs the preparation agent and
  stops after the plan is approved (research/reflection/report execution stays
  suspended — retained in code, not invoked). The persisted
  `custom_content.state` shape is `{messages, preparation}`; no MCP client is
  constructed during a preparation turn.

## Impact

- **Code:** `app/completion.py` drives the preparation agent. The old graph package
  `app/clarification/` is renamed to `app/preparation/` and rewritten as an agent
  package (`prompts.py`, `tools.py`, `agent.py`, `runner.py`); the old
  `graph.py` is deleted. `app/factory.py` drops the eager graph build.
  `app/history.py` transcript helpers are reused, and it also hosts the
  preparation state (`PrepState`, `Clarification`, `Plan`) and the unified
  `DialState`. `app/agent.py` and
  `utils/reflection.py` stay retained but not invoked. (The OpenSpec capability
  keeps its name `clarification-and-plan-alignment`.)
- **State / protocol:** `custom_content.state` becomes `{messages, preparation}`. No
  `thread_id` / `checkpoint_id` pointer; no server-side session store.
- **Dependencies:** no longer uses LangGraph `StateGraph` / `interrupt` /
  `MemorySaver` / `Command` directly (LangGraph remains a transitive dependency of
  `create_agent`). No new dependencies.
- **Persistence / scaling:** with no in-memory checkpointer, the
  single-worker-only constraint is removed — the app is process-stateless again,
  so it can run multiple workers/replicas.
- **Out of scope (future changes):** running research/reflection/report from the
  launch tool (re-enabling the suspended path); exposing read-only lookup tools
  (e.g. dataset/term descriptions) to the preparation agent for richer
  cross-context answers; suppressing the internal control-tool stages from the
  user-facing UI.
