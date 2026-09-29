## MODIFIED Requirements

### Requirement: Reviewer independently judges coverage and produces the next plan

The research-review node SHALL be an independent structured LLM call that reads the
original query, all prior iteration plans, and the accumulated research-agent messages
(reasoning and tool results), and SHALL decide whether the findings cover every plan
item. It SHALL emit the plan for the next iteration as an ordered list of steps; an
**empty** list SHALL mean research is complete. Research-review SHALL be prompted to
include only genuinely uncovered work judged against the existing findings, and
SHALL NOT expand scope to manufacture new iterations. What counts as uncovered work is the plan's
items and the gaps that the research-review parts of the quality rules define (see
**source-selection**): a gap such a rule defines, such as a fact with no check for a later edition,
is part of fulfilling the plan and SHALL NOT be treated as new scope. Every text that tells the
model when research is complete SHALL say so: the prompt's task sentence, its list of gaps, its
sentence on returning an empty next plan, its scope paragraph and its "prefer to finish" guidance,
and the output schema's own description and its two field descriptions, which the model receives
with the output schema.
"Prefer to finish" SHALL apply only once both the plan and those rules are substantively covered.
Every next step SHALL be a retrieval the research agent can carry out with its tools; the prompt
SHALL say that a summary, a comparison, a note or a calculation is the report writer's and is
never a next step.
Research-review's structured
output SHALL place its reasoning before its next-plan list. When the next plan is
non-empty, the node SHALL record it (appending to the plan list) and inject it into
the message stream as a `HumanMessage` that becomes the next research-agent iteration's
instruction.

#### Scenario: Uncovered plan item drives another iteration

- **WHEN** research-review finds that a plan item is not yet supported by the findings
- **THEN** it SHALL return a non-empty next plan covering that item, the node SHALL inject it as the next research-agent instruction, and the graph SHALL route back to research-agent

#### Scenario: Full coverage completes research

- **WHEN** research-review finds every plan item supported by the findings, and none of the gaps
  the quality rules define is open
- **THEN** it SHALL return an empty next plan and the graph SHALL route to the report node

#### Scenario: A source-selection gap is not new scope

- **WHEN** every plan item has evidence, but a forecast the plan asks about was found in one
  publication and the findings show no check for a later edition
- **THEN** research-review SHALL return a next plan asking for that check, even though the plan
  does not name it

### Requirement: Every research LLM call's inputs and outputs are specified

The research graph makes four kinds of LLM call, one per node. Each one's inputs SHALL be exactly
what is listed here — nothing else reaches a model, and adding an input SHALL require updating
this requirement. Where a call deliberately omits something another call receives, the omission
is part of the contract, not an accident of implementation.

**1. research-agent** (one call per agent step)

- System prompt: the research-agent instructions, filled with today's date, the instance's
  `client_name`, and the turn's data-sources string in a `<data_sources>` block: the instance's
  `data_sources_descriptions`, followed by the datasets section when the channel has a dataset
  server and by the rendered glossary when the channel configures one (see
  **data-sources-discovery**). They state when to announce a step with `update_status`, and the
  rules that it is called at most once per assistant message, never as a message's only tool call,
  and never together with `finish_iteration`. When the glossary's list failed or some of its terms
  did not resolve, they also carry the instruction to repeat what the app's glossary fetch missed,
  with at most three calls, each part only when its tool is bound. When the fetch obtained the
  whole glossary, they instead tell the agent not to call the bound glossary tools. On a channel with a dataset server, they also
  carry the instruction that says, for each bound dataset tool, whether the app's own calls
  succeeded: the agent does not call a tool again for an answer the datasets section shows, and
  calls it when the app's calls failed, with at most three calls (see **data-sources-discovery**).
- System prompt, additionally: the research-agent part of every generic quality rule, after the
  statement of the kinds of source the channel's configured servers give it, and, when
  a rule of the channel's `prompts.client_rules` has a research-agent part, those parts in a
  `<client_rules>` block after them (see **source-selection**).
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
- System prompt, additionally: the turn's data-sources string in a `<data_sources>` block, the
  same string research-agent receives, so the next-iteration plan this call writes points at the
  data sources that exist.
- System prompt, additionally: the research-review part of every generic quality rule, which
  defines gaps beyond the plan items, after the statement of the kinds of source the channel's
  configured servers give it, and, when a rule of the channel's `prompts.client_rules` has
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
  not the app's glossary fetch succeeded (see **report-composition**). They carry no instruction to request missing definitions, because this
  call has no tools.
- System prompt, additionally: the report-writer part of every generic quality rule, after the
  statement of the kinds of source the channel's configured servers give it, and, when a
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

**4. report-review** (one call per draft)

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
- System prompt, additionally: the report-review part of every generic quality rule, as checks
  beside the numbered ones, after the statement of the kinds of source the channel's configured
  servers give it, and, when a rule of the channel's `prompts.client_rules` has a
  report-review part, those parts in a `<client_rules>` block after them (see
  **source-selection**).
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
- **The research findings are NOT included** — no transcript, no tool results other than the
  glossary tool results above, no images, and so no status announcements either. Every criterion this call judges is decidable from the draft, the
  configuration, the query and plan, and the data-sources string.
- Model: the default chat model with reasoning effort `medium`. The call judges every
  numbered check and every source-selection check in one pass, and without reasoning it passed
  drafts that broke the dates checks and misread a year column as a missing period.
- Output: a structured verdict — one list of report violations, where an empty list is the
  approval. There is no separate approval field, so a remark the model does not want acted on
  cannot be expressed and forces a revision instead.

#### Scenario: research-review judges coverage without the images

- **WHEN** research-agent fetched a page in image mode and research-review runs afterwards
- **THEN** the review call SHALL receive a marker recording that an image was returned and SHALL
  NOT receive the image content itself

#### Scenario: report-review sees the draft but not the findings

- **WHEN** report-review judges a draft
- **THEN** its input SHALL contain the draft, the configured structure, the protected sections, the
  query and plan, the data-sources string, and the research agent's successful glossary tool
  results when there are any, and SHALL NOT contain any other tool result, any transcript message,
  image, measured word count, or ceiling

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

#### Scenario: Every research graph call receives the data-sources string

- **WHEN** a research turn runs on a channel whose glossary listed terms
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the same data-sources string, ending in the rendered glossary

#### Scenario: A channel without a glossary still gives research the topics map

- **WHEN** a research turn runs on a channel that configures no glossary and has no dataset server
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the instance's `data_sources_descriptions`, and no prompt of the
  research graph SHALL carry a datasets section, a glossary or the glossary-terminology rule

#### Scenario: Every research graph call receives the datasets section

- **WHEN** a research turn runs on a channel with a dataset server that configures no glossary
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the instance's `data_sources_descriptions` followed by the same
  datasets section, and only research-agent's SHALL carry the instruction about the dataset
  tools
