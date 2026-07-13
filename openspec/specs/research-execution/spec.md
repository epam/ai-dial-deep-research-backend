# research-execution Specification

## Purpose
TBD - created by archiving change research-execution-loop. Update Purpose after archive.
## Requirements
### Requirement: Research runs as a deterministic graph launched after plan approval

The app SHALL run research as a deterministic LangGraph graph with three nodes —
**researcher**, **reviewer**, and **report** — once the preparation agent approves
a plan (its `start_research` tool fires, setting `research_started`), in the
**same** chat-completion turn, seeded with the approved query and plan. The
graph SHALL have no checkpointer and SHALL NOT use `interrupt()`. Phase transitions
SHALL be graph edges decided by Python over the graph state, never by the model:
`START → researcher → reviewer → (researcher when the reviewer returns a non-empty
next plan and the iteration cap is not yet reached, else report) → END`.

Research SHALL NOT run before a plan is approved; an unprepared or unapproved turn
SHALL stop at the preparation stage as before.

#### Scenario: Approval launches research in the same turn

- **WHEN** the preparation agent approves the plan and calls `start_research` during a turn
- **THEN** the app SHALL run the research graph in that same turn, seeded with the approved query and plan, and stream the final report as that turn's assistant message

#### Scenario: Research does not run without approval

- **WHEN** a turn ends with clarifying questions or an unapproved plan (no `start_research`)
- **THEN** the research graph SHALL NOT run, and the turn SHALL produce only the preparation output

#### Scenario: Reflection always precedes the report

- **WHEN** the researcher finishes an iteration
- **THEN** control SHALL pass to the reviewer before any report is produced, and the report node SHALL run only after the reviewer returns an empty next plan (or the iteration cap is reached)

### Requirement: First iteration plan is the approved preparation plan

The first researcher iteration SHALL be driven by exactly the plan the user
approved during preparation (`PrepState.plan`). The graph's initial state SHALL
record the original (aligned) query and seed the plan list with the approved plan;
the first plan SHALL be presented to the researcher as its instruction.

#### Scenario: Approved plan seeds the first iteration

- **WHEN** the research graph starts
- **THEN** its first iteration plan SHALL equal the approved `PrepState.plan`, unchanged, and the original query SHALL be the aligned query from preparation

### Requirement: Researcher investigates with forced tool choice and a finish_iteration sentinel

The researcher node SHALL be a tool-calling agent over the MCP-loaded tools plus one
sentinel tool, `finish_iteration`. The agent SHALL be run with **forced tool
choice** so that every model step emits a tool call and the model cannot produce a
free-form assistant message (in particular, it cannot write a summary or a report).
When the researcher judges the current iteration complete, it SHALL call
`finish_iteration`, which SHALL end the iteration without a further model
round-trip. `finish_iteration` SHALL be a no-op signal that only ends the
iteration; it SHALL NOT decide whether to review or report. The researcher's prompt
SHALL contain no report-writing instructions. A per-iteration step cap SHALL bound a
researcher that never calls `finish_iteration`.

#### Scenario: Researcher cannot emit a free-form report

- **WHEN** the researcher model is invoked at any step of an iteration
- **THEN** it SHALL be constrained to call a tool (an MCP tool or `finish_iteration`) and SHALL NOT be able to return a free-form assistant message containing a summary or report

#### Scenario: finish_iteration ends the iteration

- **WHEN** the researcher calls `finish_iteration`
- **THEN** the current researcher iteration SHALL end immediately (no additional model call) and control SHALL pass to the reviewer

#### Scenario: MCP tool error does not abort research

- **WHEN** an MCP tool raises during research (e.g. argument validation rejects the call)
- **THEN** the error SHALL be returned to the researcher as an error `ToolMessage` (via `handle_tool_error`) and surfaced as an `error ❌` stage, and the researcher MAY retry without failing the turn

### Requirement: Reviewer independently judges coverage and produces the next plan

The reviewer node SHALL be an independent structured LLM call that reads the
original query, all prior iteration plans, and the accumulated researcher messages
(reasoning and tool results), and SHALL decide whether the findings cover every plan
item. It SHALL emit the plan for the next iteration as an ordered list of steps; an
**empty** list SHALL mean research is complete. The reviewer SHALL be prompted to
include only genuinely uncovered work judged against the existing findings, and
SHALL NOT expand scope to manufacture new iterations. The reviewer's structured
output SHALL place its reasoning before its next-plan list. When the next plan is
non-empty, the node SHALL record it (appending to the plan list) and inject it into
the message stream as a `HumanMessage` that becomes the next researcher iteration's
instruction.

#### Scenario: Uncovered plan item drives another iteration

- **WHEN** the reviewer finds that a plan item is not yet supported by the findings
- **THEN** it SHALL return a non-empty next plan covering that item, the node SHALL inject it as the next researcher instruction, and the graph SHALL route back to the researcher

#### Scenario: Full coverage completes research

- **WHEN** the reviewer finds every plan item supported by the findings
- **THEN** it SHALL return an empty next plan and the graph SHALL route to the report node

### Requirement: A hard iteration cap bounds the research loop

The research loop SHALL be bounded by a configurable hard cap on the number of
research iterations (the `MAX_RESEARCH_ITERATIONS` setting, default 10, minimum 1).
When the cap is reached, the graph SHALL route to the report node regardless of the
reviewer's verdict, so the turn always ends with a report rather than looping
indefinitely.

#### Scenario: Cap forces the report

- **WHEN** the number of completed research iterations reaches `MAX_RESEARCH_ITERATIONS` and the reviewer still returns a non-empty next plan
- **THEN** the graph SHALL route to the report node instead of looping back, and the turn SHALL still produce a report

#### Scenario: Cap default and override

- **WHEN** the process starts without `MAX_RESEARCH_ITERATIONS` set, the cap SHALL resolve to 10; **AND WHEN** it is set to a valid integer ≥ 1, the loop SHALL use that value as the maximum number of research iterations

### Requirement: Report node writes the final cited report and is the only assistant content

The report node SHALL be a streamed LLM call (with no tools) that writes the final
report from the original query, the iteration plans, and the accumulated tool
messages, following the report formatting and citation rules (Markdown structure,
inline `[doc <id>, page <ix>]` citations, and a Sources table). The report node's
streamed text SHALL be the **only** node output that becomes the user-visible
assistant message content. Researcher reasoning and reviewer structured output SHALL
NOT be appended to the assistant content; researcher tool calls SHALL surface as
DIAL stages.

#### Scenario: Report is the assistant answer

- **WHEN** the report node runs
- **THEN** its streamed text SHALL be appended to the assistant message content as the answer, formatted per the report rules with inline citations and a Sources table

#### Scenario: Researcher and reviewer output are not the answer

- **WHEN** the researcher emits reasoning alongside tool calls and the reviewer emits its structured verdict
- **THEN** none of that text SHALL appear in the assistant message content; the researcher's tool calls SHALL appear only as DIAL stages

### Requirement: Research executes autonomously within a single turn

The research graph SHALL run to completion autonomously within the single
chat-completion turn that launched it — with no user interaction, no `interrupt()`,
and no checkpointer. Across iterations the accumulated message context SHALL grow
without summarization (the researcher always sees the full prior history, and the
reviewer and report see all accumulated tool results).

#### Scenario: Whole loop runs in one turn

- **WHEN** research is launched
- **THEN** the researcher/reviewer loop and the report SHALL all run within that one turn without pausing for user input, and the turn SHALL complete with the report as the assistant message
