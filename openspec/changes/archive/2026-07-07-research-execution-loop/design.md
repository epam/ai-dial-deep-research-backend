# Design — Deterministic Research Execution Graph

## Goal

Re-enable research as the execution phase after plan approval. Replace the single
`create_agent` + `ReflectionMiddleware` loop (retained but suspended in
`app/agent.py` / `utils/reflection.py`) with a deterministic LangGraph graph that
separates three concerns into three nodes with three independent prompts:

1. **researcher** — investigate against an iteration plan using the MCP tools.
2. **reviewer** — independently judge coverage and produce the next iteration's
   plan (empty = done).
3. **report** — write the final cited report.

The flow loops `researcher → reviewer → researcher …` until the reviewer returns
an empty plan (or a hard cap is hit), then runs `report` once. Research runs in
the **same chat-completion turn** as the `start_research` approval, seeded with the
approved query and plan.

## The core decision: a deterministic graph, not a single agent

The retained loop does research and report in one `create_agent` context, steered
by a long two-phase system prompt (`app/prompts.py`) and nudges
(`utils/reflection.py`). `data/issues.md` (§"Deep Research") records why that
hurts:

- **No real control over the report.** "No technical possibility to prevent LLM
  from generating report before reflection — currently we rely on LLM respecting
  the prompt." The whole `## Research phases (CRITICAL — READ CAREFULLY)` section
  of `app/prompts.py` exists only to beg one model not to write the report yet.
- **Reflection is not independent.** The gap-check runs in the same context as the
  research, so it inherits the model's own "I'm done" bias. `issues.md` asks for
  "separate prompts and contexts for research and reflection … it should work
  independently to find all possible gaps."
- The issues list states the fix directly: "refactor research to use langgraph
  nodes for control flow: planning, research, reflection and report generation".

Splitting into three nodes fixes all three: the researcher prompt has **no report
instructions**, so there is nothing to prematurely emit; the reviewer is a
**separate LLM call with a separate prompt and its own context framing**; and phase
transitions are **graph edges**, not model decisions.

### Why a `StateGraph` here, when preparation dropped it

The clarification-and-plan-alignment design dropped `StateGraph` for *preparation*
because `interrupt()` + a checkpointer were heavy and fragile — that pain was
specific to **pausing for user input**. Its design doc explicitly said the
*execution* phase would **keep a deterministic subgraph** ("that is where the
'reflection always follows research' structural guarantee still matters"). Research
execution is **autonomous and single-turn** — no `interrupt()`, no checkpointer,
no pause machinery — so the `StateGraph` here is just routing logic and carries
none of the preparation-phase cost.

## Node design

### researcher

A `create_agent` (`langchain.agents.create_agent`) over the MCP tools plus one
extra sentinel tool, `finish_iteration`. Two mechanisms combine to make "done"
cheap and controllable:

- **Forced tool choice.** `create_agent` does not accept a `tool_choice` argument —
  it always calls the model with `tool_choice=None`
  (`.venv/.../langchain/agents/factory.py`). We force a tool call on **every** model
  step with a tiny middleware whose async `awrap_model_call` re-issues the request
  with `tool_choice="any"`:

  ```python
  class ForceToolChoiceMiddleware(AgentMiddleware):
      async def awrap_model_call(self, request, handler):
          return await handler(request.override(tool_choice="any"))
  ```

  `ModelRequest.override(tool_choice=...)` and the `"any"`/`"required"` value are
  supported by `langchain_openai.AzureChatOpenAI.bind_tools`. With this, the model
  can never emit a free-standing prose turn — every step is either an MCP tool call
  or `finish_iteration`. There is no terminal report to suppress because the model
  is structurally prevented from writing one.

- **Termination via the sentinel.** `create_agent`'s built-in loop stops when the
  last `AIMessage` has no tool calls — but forced tool choice means that never
  happens. So `finish_iteration` is declared with `return_direct=True`
  (`BaseTool.return_direct`); `create_agent` ends the loop right after a
  `return_direct` tool executes (`factory.py`, "All executed tools have
  return_direct=True"). The researcher signals completion by calling
  `finish_iteration` (instructed by its prompt); the iteration then ends with no
  extra model round-trip.

`finish_iteration` is a **signal**, not a control tool: it only ends the iteration.
It does **not** decide to review or report — the graph does that deterministically.
(Per the design discussion: a signal tool is reliable; a control tool that the
model must remember to call at the right time is the unreliability we are avoiding.)

A per-iteration **step cap** (the agent's `recursion_limit`, plus the outer
iteration cap) bounds a researcher that never calls `finish_iteration`.

The researcher's `AIMessage` content (reasoning it attaches to forced tool calls)
is **not** streamed to the user-visible answer; only its tool calls surface, as
DIAL stages. MCP tool errors are handled exactly as today
(`enable_tool_error_handling`, `handle_tool_error=True`).

### reviewer

An independent `get_chat_model(...).with_structured_output(...)` call (the same
pattern as preparation's `approve_plan`). It reads the **original query**, **all
prior iteration plans**, and the **accumulated researcher messages** (reasoning +
tool results), and returns:

```python
class ResearchReview(BaseModel):
    assessment: str          # reasoning before the verdict (reasoning-first, per CLAUDE.md)
    next_steps: list[str]    # plan for the next iteration; [] = research complete
```

`next_steps` last, after the supporting `assessment`, per the CLAUDE.md
"verdict last" convention. An empty `next_steps` is the completion verdict.

To avoid an endless "one more angle" loop (the reviewer can always invent another
comparison — exactly criterion 6 of the old prompt), the reviewer is prompted to
list **only genuinely uncovered** plan items, judged against what the tool results
already establish — not to expand scope. The loop is additionally bounded by a hard
cap (`max_research_iterations`, default 10, from `MAX_RESEARCH_ITERATIONS`); on
reaching it the graph routes to `report` regardless of the reviewer's verdict, so
the turn always ends with a report.

When `next_steps` is non-empty, the node records it (appends to `plans`) and injects
it into the message stream as a `HumanMessage` so the next researcher pass sees the
new plan as its instruction — mirroring how `ReflectionMiddleware` injected nudges,
but now carrying an explicit, independently-authored plan.

### report

A streamed `get_chat_model(...)` call (no tools) that writes the final report from
the original query, the iteration plans, and the accumulated tool messages, using
the formatting + citation rules carried over from the old `app/prompts.py`
`## Formatting` section (Markdown structure, inline `[doc <id>, page <ix>]`
citations, Sources table). This is the **only** node whose streamed text becomes
the assistant message content.

## Graph and control flow

```
START → researcher → reviewer → ┬─ (next_steps non-empty AND iteration < cap) → researcher
                                 └─ (else) → report → END
```

- `researcher` and `reviewer` share the graph's `messages` channel. The reviewer's
  injected plan `HumanMessage` becomes the next researcher pass's instruction.
- The conditional edge after `reviewer` is the sole loop/termination decision, and
  it is pure Python over `state` — never the model.

The researcher is a compiled `create_agent` graph added as a **subgraph node** so
that token/stage streaming works through one `astream` over the whole graph (see
"Surfacing to DIAL"). Both the parent state and the `create_agent` `AgentState`
share the `messages` key, so messages the researcher adds merge into the parent via
the `add_messages` reducer. (Fallback if subgraph composition misbehaves on the
pinned versions: wrap the researcher in a node function that calls
`agent.astream(...)` and forward chunks — kept as a contingency, not the plan.)

## State schema

The graph channel state uses a `messages` channel with the `add_messages` reducer
(required for `create_agent` subgraph composition and `ToolNode`), plus plain
fields. Because LangGraph state schemas need the annotated-reducer channel, this is
the one place we use a graph state object rather than a free-standing Pydantic model
held in a closure (preparation's pattern); the plan/review payloads themselves stay
Pydantic.

```python
class ResearchState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # researcher AI/Tool + injected plan HumanMessages
    original_query: str          # = PrepState.current_query (the aligned query)
    plans: list[list[str]]       # [approved prep plan, reviewer plan 1, …]; current = plans[-1]
    iteration: int               # researcher iterations completed (cap guard)
    report: str | None           # final report text (also streamed)
```

The initial state seeds `original_query` and `plans=[approved prep plan]` from the
loaded `PrepState`, and `messages` with a single `HumanMessage` rendering the first
plan as the researcher's instruction.

## Same-turn handoff

Research runs in the same turn as approval (decision: "research starts right after
initial plan gets approved"). The per-turn flow becomes:

1. Load `PrepState` (`load_last_prep_state`). If `research_started` is already true
   (research ran on an earlier turn), refuse with "start a new conversation" exactly
   as today and return.
2. Run the preparation agent (unchanged). It may end the turn with questions / a
   plan, or call `start_research`, which sets `research_started=True`.
3. **If `research_started` became true this turn**, build the research graph seeded
   from `PrepState` and run it on the **same** `Choice`, streaming the report.
4. Persist the combined `DialState` (`{messages, preparation}`) **once** at the end:
   `messages` = the preparation slice followed by the research-graph slice;
   `preparation` = the final `PrepState` (with `research_started=True`).

Refuse-after-launch therefore applies to the *next* turn (research already
completed in the turn it started). The TODO at `app/agent.py:167-171` — "the research
turn must preserve the existing preparation state instead of overwriting it" — is
resolved here: there is one combined persist, and `PrepState` is carried through,
not replaced with a fresh one.

## Surfacing to DIAL

One `astream` over the whole graph with `stream_mode=["updates", "messages"]` and
`subgraphs=True`. Routing in the runner:

- **`messages` chunks** → append to `choice` **only** when the chunk comes from the
  `report` node (`metadata["langgraph_node"] == "report"`). Researcher reasoning and
  reviewer structured-output tokens are **not** appended (the preparation runner
  already filters by `langgraph_node` for the same reason).
- **`updates`** → researcher `AIMessage(tool_calls)` / `ToolMessage` are rendered as
  timed DIAL stages, reusing `DialStageToolCallFormatter` and the
  `PendingToolCall` bookkeeping the existing runners use.

So during research the user sees tool stages stream (progress), then the report
streams as the answer. This is a **behavioral change** from the retained path, which
streamed intermediate research text into the answer; only the report is the answer
now.

## Context strategy

**No summarization** (decision). The `messages` channel grows across iterations —
the researcher always sees the full prior history, and the reviewer and report see
all accumulated tool results. Unbounded growth on very long runs is an accepted risk
for now; compaction is a documented follow-up. This keeps citations intact (the raw
`[(doc_id, page_ix)]` identifiers survive into the report) and the implementation
simple.

## Persistence

Reuses `app/history.py` (`create_dial_state`, the `multimodal-tool-output` image
upload). The research-graph messages are persisted alongside the preparation slice.
Tool-message images are uploaded to DIAL files and replaced with URLs before
`set_state`, as today. Large *text* tool outputs across many iterations could still
grow the state blob; this is noted as a follow-up (compaction), not addressed here.

## Decisions made autonomously (flagged for review)

- **Forced tool choice via `awrap_model_call` + `finish_iteration(return_direct)`**
  rather than a hand-built model/tool loop — reuses `create_agent` and its
  streaming/stage integration. (User approved "force tool call and use
  `finish_iteration()` signaling tool".)
- **Researcher as a `create_agent` subgraph node** inside an outer `StateGraph`,
  with a node-function fallback if subgraph composition misbehaves on
  langchain 1.2 / langgraph 1.1.
- **`MAX_REFLECTIONS` renamed to `MAX_RESEARCH_ITERATIONS`** (the cap now bounds
  research iterations, not gap-check nudges). Per the no-new-aliases convention the
  field name maps directly to the env var.
- **Only the report node's text becomes assistant content**; researcher/reviewer
  output is stages/suppressed. Breaking vs. the retained path's intermediate-text
  streaming; acceptable pre-prod.
- **Persist the full research-graph slice** (researcher messages + injected plans +
  report) into `custom_content.state`, accepting text-size growth for now.
- **Delete `AgentRunner`, `ReflectionMiddleware`, and the two-phase system prompt**
  rather than keep them suspended — they are fully superseded.

## Open questions / deferred

- Wall-clock and token-budget graceful shutdown (`issues.md`): today only an
  iteration-count cap bounds the run.
- Graceful report despite failed tool calls / MCP outage mid-run (`issues.md`):
  today an MCP failure surfaces through the existing top-level error funnel.
- Summarize/compact the accumulated context on long runs to bound state size and
  model context.
- Whether the reviewer and report nodes should use a different (e.g. larger-context
  or cheaper) model than the researcher; today all reuse the default
  `LLMModelConfig`.
- Suppress internal researcher/reviewer stages from the user-facing UI (shared with
  the preparation follow-up).
