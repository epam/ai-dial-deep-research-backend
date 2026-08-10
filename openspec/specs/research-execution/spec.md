# research-execution Specification

## Purpose
TBD - created by archiving change research-execution-loop. Update Purpose after archive.
## Requirements
### Requirement: Research runs as a deterministic graph launched after plan approval

The app SHALL run research as a deterministic LangGraph graph with four nodes —
**research-agent**, **research-review**, **report**, and **report-review** — once the
preparation agent approves a plan (its `start_research` tool fires, setting
`research_started`), in the **same** chat-completion turn, seeded with the approved query and
plan. The graph SHALL have no checkpointer and SHALL NOT use `interrupt()`. Phase transitions
SHALL be graph edges decided by Python over the graph state, never by the model:
`START → research-agent → (research-review when another iteration may still run, else report —
the last permitted iteration's findings go to the report without a review call) →
(research-agent when research-review returns a non-empty next plan, else report) → (END when
this call was a revision whose own model call failed, or when the draft is the last version the
budget permits — it is delivered without review — else report-review) → (report when the
draft's measured word count exceeds the ceiling or report-review asks for a revision, else
END)`.

The first of those exits is what makes the failed-revision rule terminate: a swallowed revision
failure leaves the previous draft in place unchanged, so returning to report-review would re-judge it
and route straight back to a call that fails again — and because a failed revision writes nothing,
the revision counter never advances to bound the cycle. Whether a revision failed is app-owned state
carried in the graph state, not a model verdict.

The measured count is part of that decision, not only the review's verdict: an over-ceiling draft
routes back to report even when report-review approved it or its call failed (see
**report-composition**).

The last permitted version SHALL be delivered without calling report-review, rather than calling
it and ignoring a verdict that could not be acted on; a version budget of one thereby skips the
review entirely.

Each node name SHALL distinguish the two review steps and separate the research agent from the
graph that contains it: **research-review** judges evidence coverage and **report-review**
judges the written report, while **research-agent** is the tool-calling agent inside the
research graph, not the graph itself.

Research SHALL NOT run before a plan is approved; an unprepared or unapproved turn
SHALL stop at the preparation stage as before.

#### Scenario: Approval launches research in the same turn

- **WHEN** the preparation agent approves the plan and calls `start_research` during a turn
- **THEN** the app SHALL run the research graph in that same turn, seeded with the approved query and plan, and deliver the final report as that turn's assistant message

#### Scenario: Research does not run without approval

- **WHEN** a turn ends with clarifying questions or an unapproved plan (no `start_research`)
- **THEN** the research graph SHALL NOT run, and the turn SHALL produce only the preparation output

#### Scenario: Review precedes every further iteration

- **WHEN** research-agent finishes an iteration with the iteration budget not yet exhausted
- **THEN** control SHALL pass to research-review before anything else runs, and another iteration SHALL start only on research-review's non-empty next plan

#### Scenario: The last permitted iteration is not reviewed

- **WHEN** research-agent finishes the last iteration the cap permits
- **THEN** the graph SHALL route straight to the report node with no research-review call — a "continue" verdict could not be acted on — and the hand-off SHALL be logged

#### Scenario: Report review always precedes delivery

- **WHEN** the report node produces a draft that is not the last version the budget permits
- **THEN** control SHALL pass to report-review before the turn ends, and the routing decision after it SHALL be made by Python over the graph state, not by the model

### Requirement: First iteration plan is the approved preparation plan

The first research-agent iteration SHALL be driven by exactly the plan the user
approved during preparation (`PrepState.plan`). The graph's initial state SHALL
record the original (aligned) query and seed the plan list with the approved plan;
the first plan SHALL be presented to research-agent as its instruction.

#### Scenario: Approved plan seeds the first iteration

- **WHEN** the research graph starts
- **THEN** its first iteration plan SHALL equal the approved `PrepState.plan`, unchanged, and the original query SHALL be the aligned query from preparation

### Requirement: Researcher investigates with forced tool choice and a finish_iteration sentinel

The research-agent node SHALL be a tool-calling agent over the MCP-loaded tools plus one
sentinel tool, `finish_iteration`. The agent SHALL be run with **forced tool choice**
(every model call issued with `tool_choice="any"`) so that every model step emits a
tool call and the model cannot produce a free-form assistant message (in particular,
it cannot write a summary or a report).

A research-agent iteration SHALL therefore end **only** when research-agent calls
`finish_iteration`. That tool SHALL be declared `return_direct=True`, so the agent
loop returns as soon as it executes, with no further model round-trip. Since the
loop's only other exit is a tool-call-free assistant message, which forced tool choice
makes unreachable, `finish_iteration` is the single exit from a research-agent iteration
and research-agent cannot stop early. `finish_iteration` SHALL be a no-op signal that only
ends the iteration; it SHALL NOT decide whether to review or report. Research-agent's
prompt SHALL contain no report-writing instructions.

A research-agent that never calls `finish_iteration` SHALL be bounded by the step budget
of the **A per-graph-run step budget bounds every graph run** requirement below.

#### Scenario: research-agent cannot emit a free-form report

- **WHEN** the research-agent model is invoked at any step of an iteration
- **THEN** it SHALL be constrained to call a tool (an MCP tool or `finish_iteration`) and SHALL NOT be able to return a free-form assistant message containing a summary or report

#### Scenario: finish_iteration ends the iteration

- **WHEN** research-agent calls `finish_iteration`
- **THEN** the current research-agent iteration SHALL end immediately (no additional model call) and control SHALL pass to research-review

#### Scenario: MCP tool error does not abort research

- **WHEN** an MCP tool raises during research (e.g. argument validation rejects the call)
- **THEN** the error SHALL be returned to research-agent as an error `ToolMessage` (via `handle_tool_error`) and surfaced as an `error ❌` stage, and research-agent MAY retry without failing the turn

### Requirement: Reviewer independently judges coverage and produces the next plan

The research-review node SHALL be an independent structured LLM call that reads the
original query, all prior iteration plans, and the accumulated research-agent messages
(reasoning and tool results), and SHALL decide whether the findings cover every plan
item. It SHALL emit the plan for the next iteration as an ordered list of steps; an
**empty** list SHALL mean research is complete. Research-review SHALL be prompted to
include only genuinely uncovered work judged against the existing findings, and
SHALL NOT expand scope to manufacture new iterations. Research-review's structured
output SHALL place its reasoning before its next-plan list. When the next plan is
non-empty, the node SHALL record it (appending to the plan list) and inject it into
the message stream as a `HumanMessage` that becomes the next research-agent iteration's
instruction.

#### Scenario: Uncovered plan item drives another iteration

- **WHEN** research-review finds that a plan item is not yet supported by the findings
- **THEN** it SHALL return a non-empty next plan covering that item, the node SHALL inject it as the next research-agent instruction, and the graph SHALL route back to research-agent

#### Scenario: Full coverage completes research

- **WHEN** research-review finds every plan item supported by the findings
- **THEN** it SHALL return an empty next plan and the graph SHALL route to the report node

### Requirement: A hard iteration cap bounds the research loop

The research loop SHALL be bounded by a configurable hard cap on the number of
research iterations (the `max_research_iterations` application property, default 10, minimum 1;
see the **application-config-schema** capability). It is not an environment setting — no
`MAX_RESEARCH_ITERATIONS` env var exists.
When the cap is reached, the graph SHALL route to the report node without another
research-review call — its verdict could not be acted on — so the turn always ends with a
report rather than looping indefinitely.

#### Scenario: Cap forces the report

- **WHEN** every research-review demands another iteration and the number of completed research iterations reaches `max_research_iterations`
- **THEN** the graph SHALL route to the report node instead of reviewing again, and the turn SHALL still produce a report

#### Scenario: Cap default and override

- **WHEN** a turn runs on a channel that omits `max_research_iterations`, the cap SHALL resolve to 10; **AND WHEN** the channel sets it to a valid integer ≥ 1, the loop SHALL use that value as the maximum number of research iterations

### Requirement: A per-graph-run step budget bounds every graph run

The app SHALL pass a step budget to the research graph as LangGraph's
`recursion_limit`, configured per channel by the `max_research_graph_steps`
application property (default 500, minimum 1; see the
**application-config-schema** capability).

What the budget limits SHALL be read precisely. It counts LangGraph super-steps — node
executions — within a single graph run, and each nested graph run receives the budget
again instead of drawing on what the parent has left. The research-agent node is itself a
compiled graph, so one research-agent iteration gets its own budget.

The budget therefore constrains research-agent's own loop, whose length nothing else
bounds, while the outer graph's length is already fixed by its own caps —
`max_research_iterations` for the research loop and `max_report_versions` for the report loop.
Each node execution is one super-step, and in both loops the last permitted unit of work is not
followed by a review, so the outer graph is bounded at
`2 × max_research_iterations + 2 × max_report_versions − 2` super-steps — 24 at the default
caps, and the same formula gives 20 for a version budget of one, where the single draft is
never reviewed. Both are far below the default budget. Tool
calls research-agent requests together execute in a single super-step (they are fanned out
with `Send`, and dispatches made in one tick share that tick), so the budget limits the
research-agent's model calls rather than the number of tool calls it may issue.

The budget SHALL NOT be read as a cap on the number of research iterations (that is
`max_research_iterations`, a separate property), as one allowance shared across the whole
turn, or as a per-tool-call cap — it bounds tool calls only indirectly, through the number
of model calls, with no limit on how many tools one of them may request.

Exhausting the budget SHALL raise LangGraph's `GraphRecursionError` and fail the turn
through the DIAL error protocol (see **dial-agent-with-mcp**'s **Failures delivered as
DIAL protocol errors** requirement), never deliver a half-finished answer as a success.

#### Scenario: Budget comes from the channel configuration

- **WHEN** a research turn starts on a channel that sets `max_research_graph_steps`
- **THEN** the research graph SHALL be invoked with `recursion_limit` equal to that value; **AND WHEN** the channel omits the property, the value SHALL be 500

#### Scenario: A research-agent that never finishes is bounded

- **WHEN** research-agent keeps calling MCP tools without ever calling `finish_iteration`, until its agent run exhausts the step budget
- **THEN** the turn SHALL fail through the DIAL error protocol with the step-budget message, and SHALL NOT deliver a partial report as a successful answer

### Requirement: Report node writes the final cited report and is the only assistant content

The report node SHALL be an LLM call (with no tools) that writes the report from the original
query, the iteration plans, and the accumulated tool messages, following the citation rules
below and the composition rules of the **report-composition** capability. The same node writes
the first draft and each subsequent revision; on a revision it SHALL also receive the review's
instructions and the draft they refer to.

Citations SHALL use inline `[doc <id>, page <ix>]` for document-sourced facts and
`[dataset <id>]` for dataset-sourced facts.

**The inline citation format SHALL NOT be configurable, per instance or otherwise.** It is not a
style choice but a machine-readable interface: DIAL chat will render citations from it, so a
deployment that emitted a different form would break that rendering rather than merely look
different. Every report from every instance therefore carries the same inline form, and only a
change to this requirement may change it.

Every cited source SHALL be decoded in the report's references section, whenever the configured
structure includes one (the default does). How that decoding is rendered is carried by that
section's configured description, not by this requirement (see **report-composition**, which also
states what a structure configured without such a section means).

The delivered report SHALL be the **only** node output that becomes the user-visible assistant
message content. A draft SHALL NOT reach the assistant content while the report review loop is
still running: the content SHALL be appended once, after the loop settles on the draft to
deliver. Research-agent reasoning, research-review structured output, and report-review
structured output SHALL NOT be appended to the assistant content; research-agent tool calls SHALL
surface as DIAL stages, and report-review's findings SHALL surface as a DIAL stage of their own (see
**report-composition**). Not being assistant content does not mean being invisible: the stage channel
carries what the user needs to see about how the answer was produced. A blank-line separator SHALL precede the report only when text was already streamed
into the assistant content earlier in the same turn.

#### Scenario: Report is the assistant answer

- **WHEN** the report review loop settles on a draft
- **THEN** exactly that draft's text SHALL be appended to the assistant message content as the answer, with inline citations and a references section decoding them

#### Scenario: Drafts under review are not visible

- **WHEN** the first draft is rejected by the report review and a revision is written
- **THEN** the rejected draft SHALL NOT appear in the assistant message content, and the user SHALL see only the draft the loop finally delivers

#### Scenario: Research-agent and review output are not the answer

- **WHEN** research-agent emits reasoning alongside tool calls and research-review and report-review emit their structured verdicts
- **THEN** none of that text SHALL appear in the assistant message content; research-agent's tool calls SHALL appear only as DIAL stages

#### Scenario: No leading separator when the report is the whole answer

- **WHEN** a turn's preparation stage streamed no assistant text before research started
- **THEN** the assistant message content SHALL begin with the report's first character, with no leading blank line

### Requirement: Research executes autonomously within a single turn

The research graph SHALL run to completion autonomously within the single
chat-completion turn that launched it — with no user interaction, no `interrupt()`,
and no checkpointer. Across iterations the accumulated message context SHALL grow
without summarization (research-agent always sees the full prior history, and
research-review and the report nodes see all accumulated tool results).

#### Scenario: Whole loop runs in one turn

- **WHEN** research is launched
- **THEN** the research-agent/research-review loop and the report loop SHALL all run within that one turn without pausing for user input, and the turn SHALL complete with the report as the assistant message
### Requirement: Every research LLM call's inputs and outputs are specified

The research graph makes four kinds of LLM call, one per node. Each one's inputs SHALL be exactly
what is listed here — nothing else reaches a model, and adding an input SHALL require updating
this requirement. Where a call deliberately omits something another call receives, the omission
is part of the contract, not an accident of implementation.

**1. research-agent** (one call per agent step)

- System prompt: the research-agent instructions, filled with today's date and the instance's
  `client_name`.
- Messages: the graph's accumulated `messages` — the seed instruction (the aligned query and the
  approved plan), every `AIMessage` and `ToolMessage` of the turn so far **including image
  content blocks**, and each research-review-injected next-plan instruction. Image blocks are
  subject to the image budget (see **image-budget**), which may have substituted the newest
  image-carrying results with error messages.
- Tools bound: the MCP-loaded tools plus `finish_iteration`, with forced tool choice.
- Output: tool calls only — never free-form text.

**2. research-review** (one call per completed iteration)

- System prompt: the research-review instructions, filled with today's date.
- Messages: one human message carrying the original query, the rendered findings, and the plans
  pursued so far. The findings rendering carries the instructions given, the name and arguments
  of every tool call, any notes research-agent wrote, and the **text** of every tool result.
- **Images are NOT included**: an image-carrying tool result is rendered with a marker noting an
  image was returned, and the image itself is omitted. This call therefore judges coverage
  without seeing what research-agent saw in charts, tables, and figures.
- Output: a structured verdict — the assessment, then the next-iteration steps (empty means
  research is complete).

**3. report** (one call per draft: the first, and each revision)

- System prompt: the report instructions, filled with today's date — the configured section
  structure, the protected sections, the word ceiling, the prohibited meta-annotations, and the
  citation rules (see **report-composition**).
- Messages: the full accumulated `messages` transcript **including images** (already clamped by
  the image budget), then the report request carrying the aligned query and the plans pursued.
- On a revision, additionally: the draft being revised, the revision instruction, and the draft's
  measured word count alongside the ceiling. The instruction is the review step's findings, the
  app-rendered length direction when the count forced the revision, or both merged — a revision is
  never issued without one (see **report-composition**). These SHALL be **appended after** the
  original report request rather than replacing it, so the byte prefix is unchanged and the
  provider's prompt cache can serve it (see **prompt-caching**).
- Tools bound: none.
- Output: the report text. It is not streamed to the assistant content (see the report-node
  requirement below).

**4. report-review** (one call per draft)

- System prompt: the report-review instructions, filled with today's date — what to check and what
  not to.
- Messages: one human message, assembled **stable content first** so successive review calls in a run
  share a byte prefix (the same rule as research-review's assembly, see **prompt-caching**): the
  configured report structure with each section's description, the protected sections, the aligned
  research question, and **the approved preparation plan only** — the plan list's first entry,
  since later entries are authored by research-review rather than the user and cannot carry a
  user's formatting instruction. The draft comes **last**, being the only part that differs between
  the calls of one run.
- **Neither the measured word count nor the ceiling is included**, and the message tells this call
  that the app checks the headings and the length itself. Length is not its to judge: the app
  measures the draft and adds the length violation on its own (see **report-composition**).
- **The research findings are NOT included** — no transcript, no tool results, no images. Every
  criterion this call judges is decidable from the draft, the configuration, and the query and
  plan.
- Output: a structured verdict — one list of report violations, where an empty list is the
  approval. There is no separate approval field, so a remark the model does not want acted on
  cannot be expressed and forces a revision instead.

#### Scenario: research-review judges coverage without the images

- **WHEN** research-agent fetched a page in image mode and research-review runs afterwards
- **THEN** the review call SHALL receive a marker recording that an image was returned and SHALL
  NOT receive the image content itself

#### Scenario: report-review sees the draft but not the findings

- **WHEN** report-review judges a draft
- **THEN** its input SHALL contain the draft, the configured structure, the protected sections, and
  the query and plan, and SHALL NOT contain any tool result, transcript message, image, measured
  word count, or ceiling

#### Scenario: A revision's prompt extends the draft's prompt

- **WHEN** the report node writes a revision after a first draft
- **THEN** the revision call's messages SHALL begin with the same system prompt, transcript, and
  report request as the first draft's, with the draft, the instructions, and the counts appended
  after them
