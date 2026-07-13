# Design — Deep Research Preparation Agent

## Goal

Put an alignment gate in front of the (deferred) research loop. Before any
research runs, the app must:

1. Resolve ambiguity in the user's request by asking clarifying questions.
2. Draft a research plan and align with the user on it.
3. Only then launch research, using the finalized query + approved plan.

Both clarification and plan alignment may take **multiple natural-language
rounds** — there is no sentinel "approve" string. The user must also be able to
hold a normal conversation during this phase (ask side questions, refer back to
earlier answers), not be trapped in a rigid form.

## The core decision: an agent, not a deterministic graph

The first implementation was a deterministic `StateGraph` (`clarify_decide ⇄
clarify_ask → plan_decide ⇄ plan_ask → END`) with `interrupt()` pauses and a
checkpointer. It worked, but the architecture fought us on two fronts:

**1. Walled-off conversation.** Separate per-phase nodes/prompts mean the user
can't ask cross-context questions or refer to what they said in another phase.
`data/issues.md` calls this out directly: while in clarification a user may ask
"where would you look for info on X?" (the clarify prompt has no data-source
knowledge), or a general "what is CPI?" — and a phase graph simply can't field
those. The whole "agent — alternative to workflow architecture" section of
`issues.md` argues for a single context with tools.

**2. Heavy, fragile pause machinery.** `interrupt()` forced: a checkpointer
(in-memory `MemorySaver`, single-worker-only); a `{thread_id, checkpoint_id}`
pointer protocol round-tripped through DIAL; rewind detection by comparing stored
vs latest checkpoint; terminal-checkpoint refusal; and a spike that *disproved*
fork-on-rewind on LangGraph 1.1 (re-resuming a past checkpoint keeps the original
resume value). That is a large amount of code written to work around the
framework's persistence model.

Switching the preparation phase to a **single-context tool-calling agent**
(`create_agent`, which the retained research path already uses) fixes both at
once. The agent holds one conversation; "side questions" are just the agent
answering. And because the agent loop ends a turn naturally when the model stops
emitting tool calls, **we don't need `interrupt()` at all** — which lets us drop
the checkpointer and the entire pointer/rewind apparatus (see "Stateless turns").

### What we give up, and why it's fine

A deterministic graph gives a *structural* guarantee that phases run in order. We
replace that with **tool-level hard gates**: `start_research()` refuses unless
`PrepState` shows the query clear and the plan approved, and `update_plan()`
refuses unless clarifications are resolved. The ordering guarantee now comes from
Python preconditions the model cannot bypass, instead of graph topology. For the
*execution* phase (research → reflect → report) we will **keep** a deterministic
subgraph, launched from the `start_research` tool — that is where the
"reflection always follows research" structural guarantee still matters (deferred
to a later change).

## Control model: tools mutate state, the agent cannot

The central requirement (from the design discussion): the agent must **not** be
able to flip readiness flags itself, or it could talk itself into launching
research on an unclear query or an unapproved plan. So:

- The agent's only outputs are (a) tool calls, whose arguments are constrained by
  each tool's schema, and (b) natural-language text. It has **no channel** to
  write `PrepState` fields.
- `PrepState` is mutated **only** by tool code (plain Python). The agent reads the
  consequences via each tool's returned message, but the readiness flags are set
  by the tools' own logic — `approve_plan` runs an independent judge over the real
  conversation; the agent saying "approved" does nothing.

**Implementation choice (made autonomously):** `PrepState` is held in a per-turn
holder that the tool callables close over, and tools mutate it directly as a side
effect, returning a plain string to the agent. We considered the more "LangGraph
native" route — a custom `state_schema` extending `AgentState`, tools returning
`Command(update=...)`, and reading state via `ToolRuntime`. Both enforce the same
guarantee (the LLM still only emits tool calls). We chose the holder because, now
that there is **no checkpointer**, graph state is ephemeral within a single
`ainvoke` anyway, so routing `PrepState` through the graph buys nothing and costs
real complexity (TypedDict gymnastics, `Command` returns, extracting the final
custom field from the stream). The one place we *do* read graph state is the
approval check, which needs the message history — there we use `ToolRuntime`.

This satisfies the original question — "can tools update state without the agent
being able to edit it?" — yes: the agent literally has no write path; tool Python
code is the sole mutator.

## State schema

`PrepState` (defined in `app/history.py`, alongside the unified `DialState` it
rides in) is the per-turn working state, persisted across turns (see
"Stateless turns"). Pydantic models throughout, per project convention.

```python
class Clarification(BaseModel):
    questions: list[str]            # [] = clarity check ran and found nothing to ask

class Plan(BaseModel):
    steps: list[str]                # authored only by update_plan; order = list order

class PrepState(BaseModel):
    current_query: str | None = None
    clarification: Clarification | None = None   # None = never checked
    plan: Plan | None = None
    plan_approved: bool = False      # set only by approve_plan
    research_started: bool = False   # set only by start_research
```

Readiness is no longer a `PrepState` property — the earlier `clarification_resolved`
and `ready_for_research` were dropped. The tools derive it directly:
`tools._query_failure_reason` reports the first unmet query-gate condition, and
`start_research` additionally checks the plan is recorded and approved.

Note the tri-state is split across two levels so the None/empty distinction stays
meaningful: `clarification is None` means "no check has run" (blocks research);
`clarification.questions == []` means "checked, nothing to ask" (allows it). The
same for `plan is None` vs an unapproved plan. **`plan_approved` lives on
`PrepState`, not on `Plan`** — so `approve_plan` (which sets it) never has to
touch the `Plan` object, keeping plan authorship solely in `update_plan`.

## The tools

### `update_query(query: str)`

Merges three steps into one atomic tool: (1) set `current_query`; (2) reset
`plan` and `plan_approved` (a changed query invalidates any prior plan); (3) run
an **independent** LLM clarity check and record `clarification`.

- **Why merge set + check.** Two separate tools would leave a window where the
  query changed but the clarification check is stale — the agent could slip
  `start_research` in between. Merging removes that window.
- **Why the check reads the conversation, and is strict.** It judges the candidate
  query *together with the conversation so far* (like the approval check), against
  strict criteria: every material dimension — intent, region, time period, focus —
  must be **explicitly settled by the user**; vague time words ("latest",
  "recent") must be pinned to a concrete period; and a dimension already asked but
  left unanswered is re-asked, not silently dropped. An earlier query-only version
  proved too weak — a smooth-reading refined query could slip past with a dimension
  the user never actually answered (e.g. it stopped asking about the angle once the
  user ignored it, and never pinned "latest"). The agent still folds answers into
  the query so the finalized query stays self-contained, but completeness is judged
  against what the user *actually said*. Scope is clarity only — never data-source
  presence (the agent, not the intake check, knows the sources).

### `update_plan(steps: list[str])`

Records the **agent-authored** plan (a `list[str]`, order = list order) and resets
`plan_approved`. Numbering is purely a rendering concern: the tool's returned
message presents the steps as a numbered list (via `enumerate`), so the user can
refer to a step by its number and the agent sees the number→step mapping. We
deliberately do **not** store a per-step number field — it's unnecessary, and a
list-element `index` field would be corrupted by the DIAL SDK's chunk-merge (see
the `CLAUDE.md` convention). Errors unless clarifications are resolved.

- **Why the agent drafts the plan** (rather than an independent LLM): the agent
  has the conversation and — in a later change — the data-source tools in context,
  so it can ground the plan in specific sources, which `issues.md` wants. Plan
  *quality* is the agent's job (steered by the system prompt); plan *approval* is
  the gated, independent decision.

### `approve_plan()`

An **independent** LLM reads the full conversation and the recorded `Plan`, and
decides approval. On success it sets `plan_approved = True`. It **never** edits
plan content.

Reasoning first, then the two checks (precondition first), then a short
user-facing failure summary — per `CLAUDE.md`. The schema lives in
`app/preparation/prompts.py`, next to the prompt it serves:

```python
class PlanReviewResponse(BaseModel):
    assessment: str               # brief analysis before the verdict (reasoning-first)
    recorded_plan_matches: bool   # does PrepState.plan match the plan discussed/approved?
    user_approved_a_plan: bool    # did the user approve it?
    failure_reason: str           # short user-facing summary of what to fix; "" when nothing to fix

    @property
    def approved(self) -> bool:   # computed, not emitted: true only when both checks hold
        return self.recorded_plan_matches and self.user_approved_a_plan
```

`approved` is a computed property, not an LLM-emitted field, so the verdict can
never contradict its two preconditions (this replaces an earlier emitted
`approved` field guarded by a model validator).

- **Why read the full history** (unlike `update_query`): approval is an *agreement
  recorded across turns*, impossible to judge from a query string. This is not
  unfair — the judge is reading the user's actual words.
- **Why `recorded_plan_matches` exists.** It catches a real failure: the agent
  revises the plan in chat (v2), the user approves v2, but the agent forgot to
  `update_plan(v2)` so `PrepState.plan` is still v1. Approving v1 would be wrong.
  When the recorded plan is stale, `approve_plan` refuses and tells the agent to
  `update_plan` the latest version first — the agent re-records and re-approves.
  This makes `approve_plan` the **integrity check on the whole plan-recording
  loop**, and it's why the gate stays read-only on plan content (a single
  authoring path through `update_plan`; the judge never fabricates steps).

### `start_research()`

Hard gate. Errors, naming the unmet precondition, unless the query gate passes
and the plan is both recorded and approved.
Because research execution is deferred in this change, on success it sets
`research_started = True` and returns the ready-to-research summary (finalized
query + approved plan); a later change replaces that body with the
research→reflect→report subgraph.

### Gate violations are tool errors

Precondition failures raise `ToolException` (with `handle_tool_error=True`, as the
research path already does for MCP tools), so they reach the agent as an error
`ToolMessage` it can react to — and surface as the `error ❌` DIAL stage variant.
The error text names the missing precondition so the agent self-corrects.

## Stateless turns and persistence

There is **no checkpointer and no `interrupt()`**. A turn is processed exactly
like the retained research path:

1. Reconstruct the LangChain message history from the DIAL transcript
   (`app/history.py:reconstruct_history`), and load `PrepState` via
   `load_last_prep_state` — the `preparation` field of the unified `DialState` on
   the latest assistant message's `custom_content.state` (absent → fresh `PrepState`).
2. Build the preparation agent (prompt + the four tools, closing over a holder
   seeded with that `PrepState`) and run it with `astream`.
3. The agent calls tools (which mutate the holder) and ends the turn by emitting
   text with no tool calls — that text (the questions, the plan, an answer) is the
   assistant message.
4. Persist the unified `DialState` (`{messages, preparation}`) into
   `custom_content.state` via `choice.set_state`.

`custom_content.state` carries **both** the transcript (so the agent has
conversational context next turn) and `PrepState` (the authoritative gate state,
so `start_research` need not re-derive readiness by parsing messages).

### Rewind fixes itself

Because the state rides on the assistant message, a DIAL rewind (edit/regenerate
an earlier message) is handled with **zero** detection code: DIAL truncates the
transcript to the edit point, so the surviving last assistant message carries the
correct prior `PrepState`, and the next turn simply continues from it. This is the
behavior the prior change spent a spike and a rewind-detection branch failing to
achieve with checkpoint forking.

### Refuse after launch

Once `start_research` has run (`research_started == True`), a further user message
is refused with "start a new conversation" — derived from `PrepState`, returned by
the runner before invoking the agent. (When research execution is wired up, this
is where the research turn resumes instead.)

## Cross-context conversation

The single context is what makes side questions work: "what is CPI?" is just the
agent answering from its own knowledge mid-flow, then steering back. **Decision
(autonomous):** in this change the preparation agent has only the four control
tools — *no* MCP/data tools — so data-grounded side questions ("describe dataset
X") are out of scope for now; the agent answers general questions conversationally
and keeps the flow moving. Exposing read-only lookup tools during preparation is a
documented follow-up. Rationale: it keeps this change tractable and prevents the
agent from wandering into premature research, while still delivering the main
conversational win.

## Surfacing to DIAL

The agent's natural-language text streams token-by-token to `choice` (the
questions / plan / answers). **Decision (autonomous):** the control tools
(`update_query` etc.) are rendered as DIAL stages, reusing the research path's
stage formatter. This exposes internal plumbing in the UI, which is noise for
production but useful while developing and reviewing test runs; suppressing the
control-tool stages is a documented follow-up.

## Decisions made autonomously (flagged for review)

- Held `PrepState` in a per-turn holder (closure) rather than LangGraph
  `state_schema` + `Command` — see "Control model".
- Preparation agent has no MCP/data tools this change — see "Cross-context".
- Control-tool calls rendered as DIAL stages — see "Surfacing to DIAL".
- Gate violations raise `ToolException` (agent-visible error message) — the
  agent-facing equivalent of "raise an informative error".
- Renamed the code package `app/clarification/` → `app/preparation/` so the name
  reflects that it hosts the preparation agent, not a clarification graph. (The
  OpenSpec capability keeps its name `clarification-and-plan-alignment`.)
- Deleted the superseded root design doc `clarification-flow-design.md`; this
  document is now the single source of truth for the design.

## Open questions / deferred

- Run research→reflect→report from `start_research` (a deterministic subgraph),
  replacing the ready-to-research stub.
- Expose read-only lookup tools (dataset/term descriptions) to the preparation
  agent for richer, data-grounded cross-context answers.
- Suppress the internal control-tool stages from the user-facing UI.
- Render the recorded plan programmatically into the assistant message instead of
  relying on the agent to echo it verbatim (today the prompt + `update_plan`'s
  returned block ask the agent to reproduce the recorded steps exactly).
- Whether `update_query`'s clarity check and `approve_plan`'s approval check
  should use a smaller/cheaper model than the main agent (today they reuse the
  default `LLMModelConfig`).
