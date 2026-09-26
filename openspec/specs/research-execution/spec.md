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

#### Scenario: A tool the server rejects does not abort research

- **WHEN** an MCP server rejects a tool call and reports it in its own result, for example because argument validation refused it
- **THEN** the error SHALL be returned to research-agent as an error `ToolMessage` carrying the server's own content, and surfaced as a stage marked ❌, and research-agent MAY try again within the allowance of **Research-agent and research-review act on a failed tool call** without failing the turn

#### Scenario: A tool that fails before the server answers does not abort research either

- **WHEN** a tool call fails without a result from the server — a transport failure, a gateway error, or an unexpected exception
- **THEN** it SHALL reach research-agent as an error `ToolMessage` too, composed by the app per the **tool-call-fault-tolerance** capability rather than by the tool adapter, and the turn SHALL NOT abort

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

### Requirement: Every research review's findings are visible as a DIAL stage

Each research-review call SHALL emit one DIAL stage, so a user can see why research ran another
iteration or stopped. The stage SHALL carry:

- the number of the iteration just reviewed, counting from 1;
- the reviewer's assessment of which plan items the findings cover and which they do not;
- the next-iteration steps, as a numbered markdown list — one entry per step (stage content renders
  as markdown). An empty list is the verdict that research is complete, and the stage SHALL say so
  in words rather than render an empty list.

Its title SHALL follow the shape the report-review stage uses (see **report-composition**): its own
prefix rather than `[TOOL]`, the review's outcome, and the elapsed time. The outcome names which way
the loop went from here — another iteration, or the report.

This stage records a decision already taken, which is what separates it from the activity stage the
same node opens on entry: the activity stage is open while the review call runs and says what is
happening now, and this one is closed the moment it appears and says what came of it.

A review that ran SHALL be visible whichever verdict it reached. A failed review call is not caught —
the turn ends as an error and the open activity stage closes as failed — so no findings stage is
emitted for it.

**An iteration the cap left unreviewed SHALL be announced too**, so that "the review found no gaps"
and "nothing reviewed this" stay distinguishable, exactly as they do for a report the version budget
left unreviewed (see **report-composition**). When the just-finished iteration is the last one the
cap permits, the app SHALL emit one stage stating that the review budget is exhausted and the
findings go to the report unreviewed, carrying the iteration number and the configured cap. It is
rendered from the state alone, with no model call, and carries no elapsed time, no assessment and no
next steps, there being no review to report. Because it announces a decision taken while research is
still running, it SHALL be emitted at the moment the routing decision is made, so it appears among
the stages of the run it belongs to rather than after the report's.

A cap of **one** makes no review call and exhausts nothing — a coverage review could never be acted
on, so review is off by configuration — and SHALL emit no stage at all, the same rule a version
budget of one follows in the report loop. The exception covers the stage only: the INFO record SHALL
still fire, the hand-off to the report having happened whatever the reason.

The assessment and the next steps are LLM response text: they SHALL appear in the stage and SHALL NOT
appear in any log record, where the research-review event carries the step count only. This is the
same asymmetry the report-review stage rests on, under **logging-policy**'s content allowlist.

#### Scenario: A review that demands another iteration is visible

- **WHEN** research-review judges iteration 1 short of the plan and returns three next steps
- **THEN** a stage SHALL appear carrying iteration number 1, the assessment, and the three steps as a
  numbered list, and its title SHALL state that another iteration follows, with the elapsed time

#### Scenario: A review that completes research is visible too

- **WHEN** research-review finds every plan item covered and returns no next steps
- **THEN** a stage SHALL still be emitted, carrying the assessment and stating in words that research
  is complete, and its title SHALL state that the report follows

#### Scenario: An unreviewed last iteration is announced as such

- **WHEN** an instance permits 10 iterations and the tenth finishes, so the router routes to the
  report node without a review call
- **THEN** a stage SHALL be emitted stating that the review budget is exhausted and that the run
  proceeds to the report, carrying iteration 10 and the cap of 10, with no elapsed time and no
  assessment

#### Scenario: The announcement precedes the report's own stages

- **WHEN** the iteration cap is reached and the report is then written and reviewed
- **THEN** the exhausted-budget stage SHALL appear before the stages of the report and its review,
  in the order the work happened

#### Scenario: A cap of one emits no stage

- **WHEN** an instance configures a cap of one iteration and that iteration finishes
- **THEN** no research-review stage SHALL be emitted — not the exhausted-budget one either — because
  no review call is made and nothing is exhausted, while the research-iteration-budget-exhausted INFO
  record SHALL still fire

#### Scenario: The assessment never reaches a log record

- **WHEN** a research review records an assessment and next steps, at any configured log level
  including DEBUG
- **THEN** no log record SHALL contain any of that text; only the number of next-plan steps SHALL be
  logged

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

Citations SHALL use inline `[doc <id>, page <ix>]` for document-sourced facts,
`[data_query <id>]` for facts drawn from a data query, and `[dataset <urn>]` for facts about a
dataset as a whole that no data query produced — such as when a dataset was last updated, or what
it covers. **Every fact drawn from a data query SHALL be cited `[data_query <id>]`**, never
`[dataset <urn>]`, even though the query's result names its dataset too: the query citation is the
one that opens the cited data, and the dataset it ran against still reaches the References section
through it (see **report-citations**).

**What identifies a source in each form is part of this contract**, not a detail left to the
writer, because the app parses these markers and resolves what it finds back against the server
that reported it. The instructions SHALL state each:

- A **document** is referenced by its **document id and the index of the cited page** — two values,
  both required. A document citation without a page is not a weaker citation but an unparseable
  one, because a document server attributes at page level and the reader is scrolled to that page.
- A **dataset** is referenced by its **URN**, the identifier the dataset server reports for that
  dataset, written whole. A URN carries punctuation — typically a colon, and often a parenthesised
  version — and every character of it is part of the identifier, so it SHALL NOT be abbreviated,
  case-changed, percent-encoded, or stripped of its version. The **source-attribution** capability
  owns why: the identifier is sent back to the server, and a transformed one resolves nothing.
- A **data query** is referenced by its **query id**, the identifier the data-query tool reports
  for that query in its result, written whole. It SHALL NOT be abbreviated, case-changed or
  replaced by the dataset's URN or name.

**Only a data query that returned data SHALL be cited.** A data-query tool also reports ids for
queries that returned nothing: a query it constructed and did not execute, the query it offers for
each candidate dataset when it asks for a dataset to be selected, and an executed query whose
result was empty. The instructions SHALL tell the writer never to cite such an id, because such a
query backs no value, so no fact can come from it. Whether a query's result carries a data explorer
link is not the writer's concern: the writer does not see the link, and a missing one costs the
citation its pill and nothing else (see **report-citations**). The app also checks every draft's
query ids against what the turn captured and asks for a revision when one breaks this rule
(**report-composition**), but the instruction is what keeps a first draft right.

Naming these is what separates the three forms from a formatting convention. The writer cannot infer
from the shape of a marker which values belong in it, and a writer that puts a dataset's display
name where its URN belongs, or omits a page from a document citation, produces a citation that
parses into nothing and silently loses its pill.

**How the writer gets from a tool's attribution to those forms is owned by the
**source-attribution** capability**, and its rule bears on this prompt directly: the instructions
SHALL describe what a tool's attribution conveys — which part names the document or dataset, which
part names the page — and SHALL present any concrete spelling as one example among others. They
SHALL NOT state that the tools report attribution in one particular form, because that makes one
server's formatting load-bearing for this application while breaking no test when it changes.

**Those three forms SHALL be the only way the report references a source.** The report cites what the
research retrieved and nothing else, so it SHALL carry no hyperlink in any form. Which forms count,
what the writer is told, what the app checks and what is removed before delivery are owned by the
**report-composition** capability.

**The inline citation format SHALL NOT be configurable, per instance or otherwise.** It is not a
style choice but a machine-readable interface: the app parses these markers out of the delivered
report to build DIAL inline citation annotations from them (see the **report-citations**
capability), so a deployment that emitted a different form would break that step rather than
merely look different. Every report from every instance therefore carries the same inline form,
and only a change to this requirement may change it.

Every cited source SHALL be decoded in the report's references section, whenever the configured
structure includes one (the default does). **The report node SHALL NOT write that section**: the
app builds it after the loop settles, from the metadata the servers reported about the sources the
delivered report actually cites (see **report-citations**). The writer is given the other sections
only, and what a row holds comes from configuration rather than from this requirement (see
**application-config-schema**).

The delivered report SHALL be the **only** node output that becomes the user-visible assistant
message content. A draft SHALL NOT reach the assistant content while the report review loop is
still running: the content SHALL be appended once, after the loop settles on the draft to
deliver. Research-agent reasoning, research-review structured output, and report-review
structured output SHALL NOT be appended to the assistant content; research-agent tool calls SHALL
surface as DIAL stages, and report-review's findings SHALL surface as a DIAL stage of their own (see
**report-composition**). Not being assistant content does not mean being invisible: the stage channel
carries what the user needs to see about how the answer was produced. A blank-line separator SHALL precede the report only when text was already streamed
into the assistant content earlier in the same turn.

What is appended is the settled draft **after the citation step**, which removes the hyperlinks the
report may not carry, replaces each convertible citation marker with that citation's marker tag,
appends the References section, and leaves every other character alone (see the **report-citations**
capability). That step is the single permitted transformation between the draft
the review settled on and the text the user reads; nothing else may alter a settled draft, and the
annotations it emits SHALL be the only other thing the app adds to the message alongside that text.

**The report SHALL be delivered as assistant message content, never as an attachment.** A citation
pill is drawn only inside the assistant message bubble, where the client injects it while rendering
that message's Markdown; an attachment opened in the client's side canvas is rendered by a path that
resolves no annotations. A report moved into a `text/markdown` attachment would therefore show as
plain text with no pill anywhere, and the annotations, which name marker tags standing in the
message text, would have nothing to anchor to.

The delivered content therefore carries markup a reader's client is expected to resolve: a client
that understands the marker tags renders a pill for each, and one that does not either drops a tag
or shows it. A converted citation's readable text lives in its annotation rather than in the report
text, so a client that discards the annotations loses that citation rather than degrading to a
visible marker. Which citations are converted at all is decided by the **report-citations**
capability's conversion conditions, whose deliberate consequence is that every citation left unconverted
stays fully readable in the text — and the References section lists every cited source whether or
not its citations converted, naming in text every source whose citations did not, so an unconverted
marker still resolves to a named source. A source whose citations converted is named in its
References row by a pill, on the same condition, so a client that discards the annotations loses
that row's name exactly as it loses the source's inline citations.

#### Scenario: Report is the assistant answer

- **WHEN** the report review loop settles on a draft
- **THEN** exactly that draft's text SHALL be appended to the assistant message content as the answer — with each converted citation's marker replaced by its marker tag, every unconverted citation marker in place as written, and the app-built references section decoding them

#### Scenario: The writer is not asked to write the references section

- **WHEN** the report writer's prompt is rendered from the configured structure
- **THEN** no references section SHALL appear among the sections the writer is told to write, the
  prompt SHALL state that the application appends that section itself, and a draft that writes one
  anyway SHALL be reported as a structure violation (see **report-composition**)

#### Scenario: An unfamiliar attribution spelling still yields correct markers

- **WHEN** a tool message attributes a fact in a labelled form the writer's instructions never named,
  such as `[Document 207, Page 1]` where the examples showed another spelling
- **THEN** the draft SHALL cite that fact as `[doc 207, page 1]`, because the instructions describe
  what the attribution conveys rather than the characters one server writes it in

#### Scenario: Drafts under review are not visible

- **WHEN** the first draft is rejected by the report review and a revision is written
- **THEN** the rejected draft SHALL NOT appear in the assistant message content, and the user SHALL see only the draft the loop finally delivers

#### Scenario: Research-agent and review output are not the answer

- **WHEN** research-agent emits reasoning alongside tool calls and research-review and report-review emit their structured verdicts
- **THEN** none of that text SHALL appear in the assistant message content; research-agent's tool calls SHALL appear only as DIAL stages

#### Scenario: No leading separator when the report is the whole answer

- **WHEN** a turn's preparation stage streamed no assistant text before research started
- **THEN** the assistant message content SHALL begin with the report's first character, with no leading blank line

#### Scenario: The writer is told what identifies each kind of source

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that a document is referenced by its document id and cited page index,
  and that a dataset is referenced by its URN written whole, with its punctuation and version intact

#### Scenario: A data-query fact is cited by its query id

- **WHEN** a data-query tool reports a query whose id is `dq_0123abcd45`, run against the dataset
  `IMF:WEO(1.0.0)`, and the report states a value from that query's data
- **THEN** the report SHALL cite the value as `[data_query dq_0123abcd45]`, and SHALL NOT cite it as
  `[dataset IMF:WEO(1.0.0)]`

#### Scenario: A statement about a dataset as a whole cites the dataset

- **WHEN** the report states when a dataset was last updated, taken from the dataset catalogue
  rather than from a data query
- **THEN** the report SHALL cite that statement as `[dataset <urn>]`

#### Scenario: A candidate dataset's query is never cited

- **WHEN** a data-query tool result asks for a dataset to be selected and lists two candidate
  datasets, each with a query id, and runs no query
- **THEN** the report SHALL cite neither id, and SHALL state no value as drawn from either query

#### Scenario: The writer is told to cite only queries that returned data

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that only a data query that returned data is cited, and that the ids of
  candidate queries, of queries that were not executed, and of queries that returned nothing are
  never cited

#### Scenario: The writer is told what identifies a data query

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that a data query is referenced by the query id the tool reported,
  written whole, and that every fact drawn from a data query is cited that way

#### Scenario: A dataset's display name is not its reference

- **WHEN** a dataset-query tool reports a dataset with both a human name and a URN
- **THEN** the instructions SHALL direct the writer to cite the URN, and the report SHALL carry the
  URN in the marker rather than the name

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
  `client_name`. They state when to announce a step with `update_status`, and the rules that it is
  called at most once per assistant message, never as a message's only tool call, and never
  together with `finish_iteration`.
- Messages: the graph's accumulated `messages` — the seed instruction (the aligned query and the
  approved plan), every `AIMessage` and `ToolMessage` of the turn so far **including image
  content blocks**, and each research-review-injected next-plan instruction. Image blocks are
  subject to the image budget (see **image-budget**), which may have substituted the newest
  image-carrying results with error messages. This call is the only one that receives its own
  `update_status` calls and their acknowledgements.
- Tools bound: the MCP-loaded tools plus `finish_iteration` and `update_status`, with forced tool
  choice.
- Output: tool calls only — never free-form text.

**2. research-review** (one call per completed iteration)

- System prompt: the research-review instructions, filled with today's date.
- Messages: one human message carrying the original query, the rendered findings, and the plans
  pursued so far. The findings rendering carries the instructions given, the name and arguments
  of every tool call, any notes research-agent wrote, and the **text** of every tool result.
- **Images are NOT included**: an image-carrying tool result is rendered with a marker noting an
  image was returned, and the image itself is omitted. This call therefore judges coverage
  without seeing what research-agent saw in charts, tables, and figures.
- **The status announcements are NOT included**: `update_status` calls and their acknowledgements
  are removed before the findings are rendered, so no announced status appears among the tool
  calls this call weighs when judging coverage.
- Output: a structured verdict — the assessment, then the next-iteration steps (empty means
  research is complete).

**3. report** (one call per draft: the first, and each revision)

- System prompt: the report instructions, filled with today's date — the configured section
  structure, the protected sections, the word ceiling, the prohibited meta-annotations, the
  citation rules, and the rule that a source is referenced only by an inline citation form and
  never by a hyperlink (see **report-composition**).
- Messages: the accumulated `messages` transcript **including images** (already clamped by
  the image budget) with the `update_status` calls and their acknowledgements removed, then the
  report request carrying the aligned query and the plans pursued. Removal is deterministic, so
  successive report calls in a run still share a byte prefix (see **prompt-caching**).
- **The status announcements are NOT included**: what research told the user it was doing is not
  evidence, and SHALL NOT reach the model that writes the report.
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
  that the app checks the headings, the length and the hyperlinks itself. None of the three is
  its to judge: the app checks the draft and adds their violations on its own (see
  **report-composition**).
- **The research findings are NOT included** — no transcript, no tool results, no images, and so
  no status announcements either. Every criterion this call judges is decidable from the draft, the
  configuration, and the query and plan.
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

#### Scenario: Status announcements reach research-agent but no other call

- **WHEN** research-agent has announced several steps with `update_status` during an iteration
- **THEN** research-agent's own next call SHALL still receive those calls and their
  acknowledgements, while research-review's rendered findings and the report call's transcript
  SHALL contain neither the calls nor the acknowledgements nor any announced status text

#### Scenario: Removing a status leaves the rest of its message intact

- **WHEN** one assistant message carried `update_status` alongside research tool calls, and that
  transcript is prepared for research-review or the report node
- **THEN** the research tool calls of that message SHALL be preserved with their results, and only
  the `update_status` call and its acknowledgement SHALL be removed, leaving every remaining tool
  call paired with its result

### Requirement: Research-agent and research-review act on a failed tool call

A tool call that fails reaches research-agent as an error result rather than ending the turn, per
the **tool-call-fault-tolerance** capability. Both nodes that see those results SHALL be told what
to do with them, because the behaviour of a model that is handed a failure without instruction is
unspecified and varies between runs.

**Research-agent.** Its prompt SHALL state that a tool call may fail and that the failed result
carries a verdict on retrying, and SHALL give it one action per verdict, matching the three the
**tool-call-fault-tolerance** capability defines:

- *Retrying may help* — research-agent MAY call the same tool again.
- *Retry later* (the tool is rate limited) — research-agent SHALL prefer to move on to other work
  in the same iteration and return to the tool afterwards if the evidence is still wanted, because
  reordering its work is the only way it can let a rate limit clear. Where no other work is
  outstanding it MAY call the tool again directly; even that repeat lands a model round-trip after
  the rejection, and stranding the agent would abandon the evidence rather than delay it.
- *Retrying will not help* — research-agent SHALL NOT call that tool again for the same evidence;
  it SHALL seek it from another tool, or proceed without it.

A failed result that carries no verdict is the tool's or its server's own error message.
Research-agent SHALL correct its arguments and call again, within the allowance, when the message
names a mistake in them, and SHALL otherwise treat it as *retrying will not help*. A result the
image budget substituted is not a failed call: it follows the **image-budget** capability and does
not count against the allowance.

The prompt SHALL state the retry allowance as a specific number rather than leaving it to the
model's judgement, because an unstated allowance produces a different number of attempts on every
run and cannot be tested. That allowance SHALL be **at most two repeat calls to the same failed
tool**, counted across the whole research rather than per iteration: calls made in earlier
iterations count, and a later plan asking for the same evidence does not renew them. Having spent
it, research-agent SHALL move on. Evidence that only a tool research-agent may no longer call could
provide SHALL NOT keep the iteration from ending: the plan item counts as done without it.

The allowance is the agent's alone and SHALL NOT be described to it as the total number of
attempts, because each call the agent makes already carries the retries of **In-process retries
precede the relay** in the **tool-call-fault-tolerance** capability. Three agent-level calls at
three attempts each therefore invoke the tool up to nine times for one piece of evidence in the
whole research.
The agent's retry is worth having despite that duplication because it lands a model round-trip
after the in-process retries gave up — tens of seconds into the failure rather than the three
seconds they cover — which is a different interval over which an outage may clear.

The arithmetic differs for the two other verdicts. A rate-limited call carries no in-process
retries, so each agent-level attempt is **one** invocation and the whole allowance costs three attempts,
spread across the other work research-agent does in between; that spacing is the point of
returning to it rather than repeating it at once. A call marked as not worth retrying costs one
attempt in total, because research-agent is told not to repeat it at all — the allowance is a
ceiling on a model that ignores that instruction, not an expected path.

**Research-review.** Its prompt SHALL state that a result saying a tool failed is not evidence,
and that the evidence it would have given is unavailable, because research-agent has already
retried it as far as its allowance permits. Research-review SHALL NOT plan that evidence again and
SHALL NOT treat a failed tool as coverage; an item whose only missing evidence is unavailable this
way needs no further step. Planning it again would renew research-agent's allowance in every
iteration, multiplying the calls to a failed tool by the iteration cap.

Its prompt SHALL also state that a result the image budget substituted is not a tool failure and
is not evidence. Whether its content is still missing is judged from the rest of the findings, and
what may be fetched again is what the substituted result itself says about the image slots left;
the prompt SHALL NOT restate that message.

Neither node SHALL be told to abandon the iteration because a tool failed.

#### Scenario: Research-agent retries a tool the result says is worth retrying

- **WHEN** research-agent receives an error result stating that retrying may help
- **THEN** it MAY call the same tool again within the same iteration, and the iteration SHALL continue either way

#### Scenario: The retry allowance is spent and research-agent moves on

- **WHEN** research-agent has called the same failed tool twice more after its first failure, counting calls in earlier iterations, and it fails again
- **THEN** research-agent SHALL stop calling that tool for that evidence and SHALL either seek it from another tool or continue without it

#### Scenario: Research-agent defers a rate-limited tool while other work remains

- **WHEN** research-agent receives an error result saying the tool is rate limited, and other evidence in the iteration is still ungathered
- **THEN** it SHALL carry on with that other work before calling the tool again, and SHALL NOT call it again as its next action

#### Scenario: Research-agent retries a rate-limited tool when nothing else remains

- **WHEN** research-agent receives an error result saying the tool is rate limited, and there is no other evidence left to gather in the iteration
- **THEN** it MAY call that tool again as its next action, within its retry allowance, rather than ending the iteration without the evidence

#### Scenario: Research-agent routes around a tool that cannot recover

- **WHEN** research-agent receives an error result stating that retrying now will not help
- **THEN** it SHALL NOT keep calling that tool, and SHALL either seek the evidence from another tool or continue without it

#### Scenario: Research-review does not plan evidence a failed tool left missing

- **WHEN** a plan item is unsupported by the findings because the tool that would have covered it failed
- **THEN** research-review SHALL NOT include that evidence in the next plan, and SHALL NOT judge the item covered by the failed result

#### Scenario: A failed tool does not hold the iteration open

- **WHEN** the only tool that could provide a plan item's evidence has failed and research-agent may no longer call it for that evidence
- **THEN** research-agent SHALL treat that plan item as done without the evidence and SHALL be able to end the iteration with `finish_iteration`

#### Scenario: A failed tool does not end the iteration

- **WHEN** one of several tool calls in an iteration fails and is relayed as an error result
- **THEN** research-agent SHALL continue the iteration and SHALL still end it by calling `finish_iteration`
