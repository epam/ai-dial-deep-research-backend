## MODIFIED Requirements

### Requirement: Research runs as a deterministic graph launched after plan approval

The app SHALL run research as a deterministic LangGraph graph with four nodes —
**research-agent**, **research-review**, **report**, and **report-review** — once the
preparation agent approves a plan (its `start_research` tool fires, setting
`research_started`), in the **same** chat-completion turn, seeded with the approved query and
plan — or, on a resumed run, with the channels of the snapshot a failed run saved
(**research-resume**). The graph SHALL have no checkpointer and SHALL NOT use `interrupt()`. Phase
transitions SHALL be graph edges decided by Python over the graph state, never by the model:
`START → (research-agent on a fresh run; on a resumed run, the node the snapshot's resume point
names — research-agent, research-review, report or report-review) →` and from research-agent on:
`research-agent → (research-review when another iteration may still run, else report —
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

#### Scenario: A resumed run enters at the node that failed

- **WHEN** research starts in a turn and the latest snapshot in the history is a resumable snapshot of the current plan whose resume point is report review
- **THEN** the graph SHALL go from `START` straight to report-review, seeded with the snapshot's channels, and no research-agent, research-review or report call SHALL run before it

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

### Requirement: Research executes autonomously within a single turn

The research graph SHALL run to completion autonomously within the single
chat-completion turn that launched it — with no user interaction, no `interrupt()`,
and no checkpointer. Across iterations the accumulated message context SHALL grow
without summarization (research-agent always sees the full prior history, and
research-review and the report nodes see all accumulated tool results).

A run that an exception ends is the one case that continues in a later turn: its snapshot lets a
later turn, started by the user's request to continue, resume it (**research-resume**). A failure
a resume would repeat leaves a snapshot that is never resumed, and research on a later turn starts
fresh. The resumed run is again autonomous within its own turn, and its accumulated message context
is the snapshot's transcript followed by what the resumed run adds, still without summarization.

#### Scenario: Whole loop runs in one turn

- **WHEN** research is launched
- **THEN** the research-agent/research-review loop and the report loop SHALL all run within that one turn without pausing for user input, and the turn SHALL complete with the report as the assistant message

#### Scenario: A failed run continues in a later turn

- **WHEN** a research run fails with a quota error in its second iteration, and on a later turn the user asks to continue
- **THEN** the later turn SHALL run the rest of the research from the snapshot without pausing for user input, research-agent SHALL see the snapshot's whole transcript, and the turn SHALL complete with the report as the assistant message

### Requirement: Every research LLM call's inputs and outputs are specified

The research graph makes five kinds of LLM call: one per node, and a second one in the
report-review node. Each one's inputs SHALL be exactly what is listed here — nothing else reaches
a model, and adding an input SHALL require updating this requirement. Where a call deliberately
omits something another call receives, the omission
is part of the contract, not an accident of implementation.

On a resumed run (**research-resume**), the graph's accumulated `messages` begin with the
transcript the snapshot restored — written by the failed turn, with its images downloaded back to
base64 — and every call below that reads the transcript reads it including that part. The other
channels a call reads (the query, the plans, the iteration count, the draft and its number, the
revision instruction) come from the snapshot too. No call receives the failed-turn note or the
preparation messages of any turn.

**1. research-agent** (one call per agent step)

- System prompt: the research-agent instructions, filled with today's date, the instance's
  `client_name`, and the turn's data-sources string in a `<data_sources>` block: the configured
  servers' descriptions, the document statistics block, the datasets section and the rendered
  glossary, each when its condition holds (see **data-sources-discovery**). They state when to
  announce a step with `update_status`, and the rules that it is called at most once per assistant
  message, never as a message's only tool call, and never together with `finish_iteration`. When the
  glossary's list failed or some of its terms did not resolve, they also carry the instruction to
  repeat what the app's glossary fetch missed, with at most three calls, each part only when its
  tool is bound. When the fetch obtained the whole glossary, they instead tell the agent not to call
  the bound glossary tools. On a channel with a dataset server, they also carry the instruction that
  says, for each bound dataset tool, whether the app's own calls succeeded: the agent does not call
  a tool again for an answer the datasets section shows, and calls it when the app's calls failed,
  with at most three calls (see **data-sources-discovery**).
- System prompt, additionally: the research-agent part of every generic quality rule, in one
  block per policy — source selection, opened by the statement of the kinds of source the channel's
  configured servers give it, then faithful relay, then, on a channel that configures a glossary,
  terminology — and, when
  a rule of the channel's `prompts.client_rules` has a research-agent part, those parts in a
  `<client_rules>` block after them (see **source-selection**).
- Messages: the graph's accumulated `messages` — the seed instruction (the aligned query and the
  approved plan), every `AIMessage` and `ToolMessage` of the run so far **including image
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
- System prompt, additionally: the turn's data-sources string in a `<data_sources>` block, the
  same string research-agent receives, so the next-iteration plan this call writes points at the
  data sources that exist.
- System prompt, additionally: the research-review part of every generic quality rule, which
  defines gaps beyond the plan items, in one block per policy — source selection, opened by the
  statement of the kinds of source the channel's configured servers give it, then faithful relay —
  and, when a rule of the channel's `prompts.client_rules` has
  a research-review part, those parts in a `<client_rules>` block after them (see
  **source-selection**).
- Model: the default chat model with reasoning effort `medium`, where the other research calls
  use none. The gaps the quality rules define need the call to weigh each fact of the question
  against the findings, and without reasoning it closed research on a listing or a title alone.
- Output: a structured verdict — the assessment, then the next-iteration steps (empty means
  research is complete).

**3. report** (one call per draft: the first, and each revision)

- System prompt: the report instructions, filled with today's date — the configured section
  structure, the protected sections, the word ceiling, the prohibited meta-annotations, the
  citation rules, and the rule that a source is referenced only by an inline citation form and
  never by a hyperlink (see **report-composition**) — and the turn's data-sources string in a
  `<data_sources>` block, the same string research-agent receives. On a channel that configures a
  glossary, they also carry the rule that the report uses the glossary's terminology, whether or
  not the app's glossary fetch succeeded (see **report-composition**). They carry no instruction to
  request missing definitions, because this
  call has no tools.
- System prompt, additionally: the report-writer part of every generic quality rule, in one block
  per policy — source selection, opened by the statement of the kinds of source the channel's
  configured servers give it, then faithful relay, terminology, language and style, and removal,
  each where it has a
  report-writer part — and, when a
  rule of the channel's `prompts.client_rules` has a report-writer part, those parts in a
  `<client_rules>` block after them (see **source-selection**).
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

**4. blind review** (one call per draft, in the report-review node)

- System prompt: the report-review instructions, filled with today's date — what to check and what
  not to — and the turn's data-sources string in a `<data_sources>` block, the same string
  research-agent receives. When the glossary fetch listed at least one term, or research-agent
  obtained a successful glossary tool result, the checks include the glossary-terminology check
  (see **report-composition**).
- System prompt, additionally, on a channel that configures a glossary: the text of every
  **successful** result of the two configured glossary tools (the list-terms tool and the
  term-definitions tool) that research-agent obtained during the turn, in the order they were
  obtained, in a `<glossary_tool_results>` block. The app selects them from the transcript by the
  configured tool names, and passes their text as the server sent it, without parsing it. A result
  marked as an error is left out. The block is absent when there is no such result. This is the one
  kind of tool result this call receives: it is the glossary the check judges against when the
  app's own fetch missed terms or definitions.
- System prompt, additionally: the blind-review part of every generic quality rule, as checks
  beside the numbered ones, in one block per policy — source selection, opened by the statement of
  the kinds of source the channel's configured servers give it, then faithful relay, language and
  style, and removal, each where it has a blind-review
  part — and, when a
  rule of the channel's `prompts.client_rules` has a
  blind-review part, those parts in a `<client_rules>` block after them (see
  **source-selection**).
- Messages: one human message, assembled **stable content first** so successive review calls in a
  run
  share a byte prefix (the same rule as research-review's assembly, see **prompt-caching**): the
  configured report structure with each section's description, the protected sections, the aligned
  research question, and **the approved preparation plan only** — the plan list's first entry,
  since later entries are authored by research-review rather than the user and cannot carry a
  user's formatting instruction. The draft comes **last**, being the only part that differs between
  the calls of one run.
- **Neither the measured word count nor the ceiling is included**, and the message tells this call
  that the app checks the headings, the length, the hyperlinks and the emojis itself. None of the
  four is
  its to judge: the app checks the draft and adds their violations on its own (see
  **report-composition**).
- **The research findings are NOT included** — no transcript, no tool results other than the
  glossary tool results above, no images, and so no status announcements either. Every criterion
  this call judges is decidable from the draft, the
  configuration, the query and plan, and the data-sources string. Whether a claim is faithful to
  its source is judged by call 5, which sees the transcript.
- Model: the default chat model with reasoning effort `medium`. The call judges every
  numbered check and every check of its rule sections in one pass, and without reasoning it passed
  drafts that broke the dates checks and misread a year column as a missing period.
- Output: a structured verdict — one list of report violations, where an empty list is the
  approval. There is no separate approval field, so a remark the model does not want acted on
  cannot be expressed and forces a revision instead.

**5. grounded review** (one call per draft, in the report-review node, concurrent with call 4; see
**faithful-relay**)

- System prompt: a short neutral message saying that the messages after it are the research the
  assistant did for the question, and that the last messages say what to do with it. It carries no
  rule, no date and no data sources.
- Messages, after it: the research transcript exactly as call 3 receives it — the accumulated
  `messages` **including images**, already clamped by the image budget, with the `update_status`
  calls and their acknowledgements removed — and no report request.
- Then a system message with the grounded review's instructions: today's date, the
  instruction to compare every claim with the source passage it relays, the generic policy blocks
  — source selection, opened by the statement of the kinds of source the channel's configured
  servers give it, with its terms and its rules' **report-writer** parts; faithful relay, with its
  terms and its rules' **report-writer** parts; and terminology and language and style with their
  rules' **grounded-review** parts — then call 3's "No calculations" section, then, when a rule of
  the channel's `prompts.client_rules` has a grounded-review part, those parts in a
  `<client_rules>` block, then, when a client rule has a report-writer part, those parts as context
  it does not check, in a `<client_writer_rules>` block, then the turn's data-sources string in a
  `<data_sources>` block, the
  statement that the transcript is the findings, what is not its job, and the answer format: one
  item per violation, in the numbered layout its answer is read by, with an example.
- Then a system message with the review request call 4 receives: the configured report
  structure with each section's description, the protected sections, the aligned research
  question, the approved preparation plan only, and the draft, last.
- **Not included:** the client rules' research and blind parts, call 4's numbered checks, the
  glossary rule and the glossary tool results apart from what the transcript carries, the
  blind-review parts of any rule, the measured word count and the ceiling, and the drafts before
  this one.
- Model: the default chat model with reasoning effort `medium`, chosen for the turn's time: at
  `high` the grounded review found slightly more and was more precise, but took about half again
  as long.
- Tools bound: none. No output schema.
- Output: free text, read as a numbered list of violations; `No violations.` adds none.

#### Scenario: research-review judges coverage without the images

- **WHEN** research-agent fetched a page in image mode and research-review runs afterwards
- **THEN** the review call SHALL receive a marker recording that an image was returned and SHALL
  NOT receive the image content itself

#### Scenario: The blind review sees the draft but not the findings

- **WHEN** report-review judges a draft
- **THEN** the blind review's input SHALL contain the draft, the configured structure, the
  protected sections, the query and plan, the data-sources string, and the research agent's
  successful glossary tool results when there are any, and SHALL NOT contain any other tool result,
  any transcript message, image, measured word count, or ceiling

#### Scenario: The grounded review sees the findings but not the rules of other steps

- **WHEN** the grounded review judges a draft on a channel with client rules
- **THEN** its input SHALL contain the neutral system message, the report call's transcript with
  its images, the instructions and the review request as two trailing system messages, and
  SHALL NOT contain a client rule's research or blind part, a blind-review part of any rule or the
  status announcements

#### Scenario: A revision's prompt extends the draft's prompt

- **WHEN** the report node writes a revision after a first draft
- **THEN** the revision call's messages SHALL begin with the same system prompt, transcript, and
  report request as the first draft's, with the draft, the instructions, and the counts appended
  after them

#### Scenario: Status announcements reach research-agent but no other call

- **WHEN** research-agent has announced several steps with `update_status` during an iteration
- **THEN** research-agent's own next call SHALL still receive those calls and their
  acknowledgements, while research-review's rendered findings, the report call's transcript and
  the grounded review's transcript SHALL contain neither the calls nor the acknowledgements nor
  any announced status text

#### Scenario: Removing a status leaves the rest of its message intact

- **WHEN** one assistant message carried `update_status` alongside research tool calls, and that
  transcript is prepared for research-review or the report node
- **THEN** the research tool calls of that message SHALL be preserved with their results, and only
  the `update_status` call and its acknowledgement SHALL be removed, leaving every remaining tool
  call paired with its result

#### Scenario: Every research graph call receives the data-sources string

- **WHEN** a research turn runs on a channel whose glossary listed terms
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the same data-sources string, ending in the rendered glossary

#### Scenario: A channel without a dataset server still gives research the topics map

- **WHEN** a research turn runs on a channel that has no dataset server and whose document server
  sets a `description`
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry that description, and no prompt of the research graph SHALL carry
  a datasets section, a glossary or the glossary-terminology rule

#### Scenario: Every research graph call receives the datasets section

- **WHEN** a research turn runs on a channel with a dataset server that configures no glossary
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the same data-sources string, including the same datasets
  section, and only research-agent's SHALL carry the instruction about the dataset
  tools

#### Scenario: A resumed research-agent call receives the snapshot's transcript

- **WHEN** a run resumes inside research-agent from a snapshot whose transcript holds the seed
  instruction and two completed agent turns, one of whose tool results carries an image
- **THEN** research-agent's next model call SHALL receive those messages in order, with the image
  as a base64 block, and SHALL NOT receive the failed turn's preparation messages or the
  failed-turn note
