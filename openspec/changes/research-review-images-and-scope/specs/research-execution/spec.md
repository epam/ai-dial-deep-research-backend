## MODIFIED Requirements

### Requirement: Reviewer independently judges coverage and produces the next plan

The research-review node SHALL be an independent structured LLM call that reads the
original query, all prior iteration plans, and the accumulated research-agent messages
(reasoning and tool results, including images), and SHALL decide whether the findings cover
every plan item. It SHALL emit the plan for the next iteration as an ordered list of steps; an
**empty** list SHALL mean research is complete. Research-review SHALL be prompted to
include only genuinely uncovered work judged against the existing findings, and
SHALL NOT expand scope to manufacture new iterations. Research-review's structured
output SHALL place its reasoning before its next-plan list. When the next plan is
non-empty, the node SHALL record it (appending to the plan list) and inject it into
the message stream as a `HumanMessage` that becomes the next research-agent iteration's
instruction.

Research-review SHALL judge only the research-related portion of the query and plan. A
formatting instruction MAY still name a genuine research requirement — "compare X and Y in a
table" requires data for both X and Y — and research-review SHALL treat a missing one as an
ordinary coverage gap, phrased as evidence still needed. An instruction that names no data (e.g.
"keep it brief", "answer in two sentences") SHALL NOT become, or remain, a next-plan step, since
it implies no research and no amount of research-agent tool calls could satisfy it as a step of
its own. Research-review SHALL also treat an image content block among the findings as evidence
in its own right: a plan item a fetched image already shows SHALL count as covered, and SHALL
NOT be re-listed as a next step asking research-agent to re-fetch or re-describe it.

Research-review SHALL NOT ask, as a next step, for the report itself, a summary, or a specific
presentation of the findings — research-agent has forced tool choice and cannot write one, and no
report exists until research ends. Such a request would recur every iteration research-review
runs, since research-agent could only repeat the same tool calls in response. For the same
reason, research-review SHALL NOT judge whether a delivered answer would honor the request's
format: that is not decidable before the report is written.

#### Scenario: Uncovered plan item drives another iteration

- **WHEN** research-review finds that a plan item is not yet supported by the findings
- **THEN** it SHALL return a non-empty next plan covering that item, the node SHALL inject it as the next research-agent instruction, and the graph SHALL route back to research-agent

#### Scenario: Full coverage completes research

- **WHEN** research-review finds every plan item supported by the findings
- **THEN** it SHALL return an empty next plan and the graph SHALL route to the report node

#### Scenario: A pure format instruction is never listed as a next step

- **WHEN** the query or plan asks for a report property that names no data, such as its length or tone (e.g. "keep it brief")
- **THEN** research-review SHALL NOT list a next step whose purpose is to satisfy that instruction, whether or not research-agent has produced anything toward it

#### Scenario: A format instruction's data requirement still becomes a next step

- **WHEN** the query or plan asks for a table or comparison naming specific data (e.g. "compare X and Y in a table") and the findings are missing one of the named data points
- **THEN** research-review SHALL list a next step for the missing data, phrased as evidence still needed, not as a formatting instruction

#### Scenario: An image already covers a plan item

- **WHEN** a plan item asks for a fact and a fetched page's image content block (already in the findings research-review reads) shows that fact
- **THEN** research-review SHALL treat the item as covered and SHALL NOT list a next step asking research-agent to re-fetch or re-describe that page

#### Scenario: Research-review never asks for the report

- **WHEN** research-review is deciding the next plan, at any iteration
- **THEN** it SHALL NOT return a next step asking for the final answer, a summary, or a specific presentation of the findings, and SHALL NOT judge whether such an answer would honor the request's format

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

- System prompt: the research-review instructions, filled with today's date. They state that
  report format, tone, length, or structure is out of this call's scope, and that no report
  exists yet to judge or to ask for.
- Messages: one human message carrying the original query, the rendered findings, and the plans
  pursued so far. The findings rendering carries the instructions given, the name and arguments
  of every tool call, any notes research-agent wrote, the text of every tool result, and **each
  tool result's own image content blocks**, placed where that result's text sits. Image blocks are
  subject to the image budget (see **image-budget**) — the same clamped set research-agent's own
  call receives, since both read the same accumulated `messages`.
- **The status announcements are NOT included**: `update_status` calls and their acknowledgements
  are removed before the findings are rendered, so no announced status appears among the tool
  calls this call weighs when judging coverage.
- Output: a structured verdict — the assessment, then the next-iteration steps (empty means
  research is complete).

**3. report** (one call per draft: the first, and each revision)

- System prompt: the report instructions, filled with today's date — the configured section
  structure, the protected sections, the word ceiling, the prohibited meta-annotations, and the
  citation rules (see **report-composition**).
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
  that the app checks the headings and the length itself. Length is not its to judge: the app
  measures the draft and adds the length violation on its own (see **report-composition**).
- **The research findings are NOT included** — no transcript, no tool results, no images, and so
  no status announcements either. Every criterion this call judges is decidable from the draft, the
  configuration, and the query and plan.
- Output: a structured verdict — one list of report violations, where an empty list is the
  approval. There is no separate approval field, so a remark the model does not want acted on
  cannot be expressed and forces a revision instead.

#### Scenario: research-review judges coverage with the images

- **WHEN** research-agent fetched a page in image mode and research-review runs afterwards
- **THEN** the review call SHALL receive that page's image content blocks alongside the rendered findings, subject to the same image budget research-agent's own call observes

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
