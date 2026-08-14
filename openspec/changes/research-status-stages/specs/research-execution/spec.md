## MODIFIED Requirements

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

## ADDED Requirements

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

A review that ran SHALL be visible whichever verdict it reached. The last permitted iteration gets no
review call (see the iteration-cap requirement), so it emits no stage; the INFO record for the
exhausted iteration budget is the only trace of that hand-off (see **logging-policy**). A failed
review call is not caught either — the turn ends as an error and the open activity stage closes as
failed — so no findings stage is emitted for it.

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

#### Scenario: An unreviewed last iteration emits no stage

- **WHEN** the iteration cap is reached, so the router routes to the report node without a review call
- **THEN** no research-review stage SHALL be emitted

#### Scenario: The assessment never reaches a log record

- **WHEN** a research review records an assessment and next steps, at any configured log level
  including DEBUG
- **THEN** no log record SHALL contain any of that text; only the number of next-plan steps SHALL be
  logged
