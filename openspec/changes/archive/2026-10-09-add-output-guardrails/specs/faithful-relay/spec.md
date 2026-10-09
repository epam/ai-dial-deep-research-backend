## MODIFIED Requirements

### Requirement: The faithful-relay rules are a generic policy of quality rules

The faithful-relay rules SHALL be generic quality rules (see **source-selection**), rendered as a
block of their own in each step's system prompt, under a heading that names faithful relay, after
the source-selection block and before the other generic policies and the client rules. The blind
review's block SHALL present the rules' parts as checks. The grounded review's block SHALL carry
the rules' report-writer parts (see "The grounded review checks the draft against the sources"). The
rules SHALL name no client, dataset, publication or tool.

The block SHALL open with the definitions of the terms the rules use, under a name distinct from
the source-selection terms, presented as definitions rather than as a rule, and every step, the
grounded review included, SHALL receive them. The terms are the policy's terms, not one of its
rules (see **source-selection**, "A quality rule is one bundle of step instructions"). The
definitions SHALL say that the source-selection terms, such as value, stated date
and described period, apply here too, which is why the faithful-relay block comes after the
source-selection block that defines them.

- **Source**: the result of a research tool call, or the data sources the prompt carries, such as
  the knowledge base's descriptions and what the application fetched from the dataset server. A
  search tool's answer is not a source: it summarises pages, and a summary can change, distort or
  invent what the pages say, such as a value, a sum or a characterisation that no page states. It
  only points at where the evidence lives, and the page is read instead. A page read as text or as
  an image, and a chunk a retrieval tool returns word for word, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say and
  adds nothing to them.
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic or modelling that produces a number no source gives: a growth rate
  derived from two levels, a difference or a gap in percentage points, a ratio, a multiple such as
  "twice as large", a share, a sum, an average, an elasticity or a regression estimate. A comparison
  is not a calculation, and neither is writing a value in another notation, such as a fraction as a
  percentage, or rounding a value given with more digits than a reader can use. This is the
  definition of **report-composition**, "Reports contain no calculations", in the terms' own
  wording.
- **Inference**: a conclusion no source states: a causal link, a forecast, an extrapolated trend,
  an implication, a recommendation, or a position attributed to an organisation.
- **Forecast** and **estimate**: a value its source calls a forecast, a projection, an outlook, an
  estimate or a preliminary figure, or a value for a period that had not ended when the source
  stated it, such as a figure "for 2023" in a note of December 2023, or growth "in 2026" in a report
  of April 2026.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario.
- **Statement about the evidence**: a sentence that says what the research covered, as a section's
  description may ask, that the sources do not give some evidence, or that the report does not
  cover a topic. It states no fact from a source, so it needs no citation.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent, research review, the report writer, the blind
  review and the grounded review SHALL each carry the faithful-relay block, opening with the
  definitions above, after the source-selection block

#### Scenario: The blind review reads the rules as checks

- **WHEN** the blind review's system prompt is rendered
- **THEN** its faithful-relay block SHALL introduce the parts below it as checks to judge the draft
  against, and SHALL come before its "Not your job" section

### Requirement: Rule 3 — the grounded review judges the "No calculations" rule

The rule that neither research nor the report calculates is owned by **research-execution**,
"Research looks for a stated figure rather than planning to compute one", by
**clarification-and-plan-alignment**, "The plan never asks for a calculation", and by
**report-composition**, "Reports contain no calculations". It SHALL NOT be a faithful-relay quality
rule, so the faithful-relay block SHALL carry no part of it at any step.

The grounded review SHALL judge the draft against the writer's "No calculations" rule as well as
against the faithful-relay rules: its instructions SHALL carry the writer's "No calculations"
section in the one wording the writer receives, as a section of its own after the generic policy
blocks and before the client rules, which never override it. The
blind review's "No calculations" check can judge only a number the draft presents as computed;
the grounded review can also find a computed number the draft presents as stated, because it sees
that no source gives it.

#### Scenario: The grounded review and the writer share the rule's wording

- **WHEN** the grounded review's instructions and the writer's system prompt are rendered
- **THEN** both SHALL carry the writer's "No calculations" section in the same wording

#### Scenario: A computed gap presented as stated is found

- **WHEN** a draft says that one region grew 1.2 percentage points faster than another, citing a
  page that gives only the two growth rates
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: Rule 8 — missing evidence is stated, not filled

Where the sources lack the evidence, the report SHALL state the limitation instead of filling the
gap.

- **Report writer:** says what is missing and what therefore cannot be concluded, and never fills
  the gap with its own knowledge or an inference.
- **Blind review:** a fact that the research question or the approved plan asks for, and that the
  draft neither answers nor declares unavailable, is a violation. A plan item that names a source is
  answered when its fact is answered, from that source or from another, since the source-selection
  rules let the report leave out a source that only repeats another. A fact that a rule excludes
  from the report is the exception: leaving it out without comment is correct, and mentioning it is
  a violation of
  the removal rule (see **prohibited-content**). The blind review judges this because it sees the
  client rules that exclude content. This blind part is the one faithful-relay text this change
  rewrites. The sentence it replaces accepted a "does not cover" sentence as declaring a part,
  which the removal rule forbids for excluded content. A part that is not excluded is declared
  unavailable by saying that the sources do not give it.

#### Scenario: An unanswered part of the question

- **WHEN** the question asks for a forecast for two regions and the draft covers one region and says
  nothing of the other
- **THEN** the blind review SHALL report the missing region as a violation

#### Scenario: An unanswered plan item

- **WHEN** the approved plan has an item on import prices and the draft neither covers it nor says
  that the sources do not give it
- **THEN** the blind review SHALL report the plan item as a violation

#### Scenario: A plan item naming a source is answered from another

- **WHEN** a plan item asks to search a named publication for a 2026 forecast, the publication
  only repeats the dataset value, and the draft gives the dataset value
- **THEN** the blind review SHALL NOT report the plan item

#### Scenario: An excluded part of the question is left out

- **WHEN** the question asks for the results of named companies, a client rule excludes company
  results, and the draft leaves them out without comment
- **THEN** the blind review SHALL NOT report the omission

### Requirement: The grounded review checks the draft against the sources

Report review SHALL make two model calls for every draft it reviews. The **blind review** sees the
draft, the configured sections, the question and the plan, but not the research findings (see
**report-composition**). The **grounded review** judges the draft against the research transcript.
The two SHALL run concurrently, so the review takes as long as the slower of the two.

Its messages SHALL be, in this order:

1. a system message saying that the messages after it are the research the assistant did for the
   question, and that the last messages say what to do with it — and nothing else;
2. the research transcript exactly as the report writer receives it: every message of the turn,
   tool results and their images included, with the status announcements removed;
3. a system message with the grounded review's instructions;
4. a system message with the review request: the configured report structure with each section's
   description, the protected sections, the aligned research question, the approved preparation
   plan, and the draft, last.

**Why this order.** Each message's position has its own reason:

- **The neutral first message.** It is a fixed text with no date, data source or rule, so it is the
  same in every round and every turn. The grounded review does not open with the research agent's
  system prompt; why is given below.
- **The instructions after the transcript.** They come right before the draft they are applied to,
  so the rules the model applies stand next to the text it judges rather than ahead of a transcript
  that can run to tens of thousands of tokens. That is the motive; the benefit to the model is not
  measured, but this is the layout whose recall and precision were measured offline, and the same
  instructions in the first message were not. Their position does not affect the cache: they are
  fixed for the whole turn.
- **The request with the draft, last.** The draft is the only part that changes between rounds, so
  everything before it can be read from the cache.
- **System messages, never user messages, after the transcript,** for the cache (below). The plain
  system role is used: a trailing `developer` message measured no different.

**How the layout keeps a cache hit likely.** The internal cache ablations of the report loop
measured how the provider caches on the DIAL route:

- It caches a prompt only at a point where an earlier request's prompt ended, and a later request
  reuses the longest such earlier prompt that is a prefix of its own.
- A trailing system message is not an end: the cache entry of a request that ends with system
  messages lies at the end of the message before them. A trailing user message is an end, and a
  later request whose last message differs cannot match past it; with a changed closing user
  message no try read anything from the cache.
- A trailing `developer` message behaved like a trailing system message, within the noise of the
  measurement.
- Calls that share a prefix must also share the model, the reasoning effort, the tool list and the
  output schema; `tool_choice` may differ.

The first round therefore leaves an entry at the end of the transcript, and each later round of the
turn can read up to it, as long as:

- both trailing messages are system messages, never user messages;
- the transcript is passed exactly as the writer receives it, and is the same in every round:
  research is over when the report loop starts, and neither the report node nor report review
  writes to it, so drafts and review items never enter it;
- every round uses the same model and reasoning effort, with no tools and no output schema.

Even then a round reads the cache only when DIAL sends it to the upstream that holds the entry: in
the measurement an unpinned trailing system message hit in about half of the tries. Nothing SHALL
depend on the cache being used; the `cache_read` count in the grounded review's log record shows
whether it was.

**Why the grounded review does not reuse the research agent's cached prefix.** The last call of the
research agent leaves a cache entry at the end of its prompt: its system prompt, its tools and the
transcript up to its last tool result. A call that opened with the same system prompt and tools and
then the transcript could read that entry in its first round as well, and the internal ablations
measured calls laid out that way doing so. The grounded review is not laid out that way, because
of these premises. If one of them stops holding, the decision SHALL be reconsidered:

1. **The reasoning effort differs.** The research agent runs at `none`, the grounded review at
   `medium`, and a different effort was measured to lose the cache. At `none` the grounded review
   found well under half of the severe violations, at about a third precision, so it cannot drop to
   the research agent's effort. Reconsider when the research agent runs at the grounded review's
   effort.
2. **The tools differ, but that alone does not block the reuse.** The research agent binds the
   research tools with `tool_choice` forcing a call; the grounded review binds none. To share the
   prefix it would bind the same tools and forbid calling them programmatically through
   `tool_choice`: `none` forbids every call, and a selection of allowed tools forbids the rest. The
   API enforces that choice, so the model is not trusted to refrain, and the tool list stays the
   same, which is what the cache needs: `tool_choice` was measured to differ between calls that
   share a prefix without losing the cache, and the end-to-end cache runs bound the research tools
   with `tool_choice` `none`. Its cost is the tool definitions in every review request, which the
   cache serves on a hit.
3. **A hit is not certain anyway.** Even an exact shared prefix is read only when DIAL routes the
   call to the upstream that holds the entry: about half of the unpinned tries hit, and pinned calls
   still missed occasionally. Reconsider when routing makes a hit close to certain.
4. **The research agent's instructions would come first.** Its system prompt tells the model that
   it is the research agent, that every step is a tool call and that it never writes prose. A
   review opening with it would have to override those instructions with later ones in the same
   request. How that affects the review is not measured.
5. **The measured quality is the neutral layout's.** The grounded review's recall and precision
   were measured with the neutral first message only.

The grounded review's instructions SHALL carry, in this order:

- that it is the report check of a deep-research assistant, today's date, and that it judges the
  draft against the rules below and nothing else;
- that it works claim by claim: every sentence and table cell that states a figure, a forecast or
  an estimate, a comparison, a cause or a characterisation of what a source found is compared with
  the source passage it relays, and every claim its source does not support as written is reported
  — such as a figure no source gives or one for another scope than the source's, a comparison or a
  finding that reverses or outweighs the source, a forecast, an estimate or a source's own view
  written as an observed fact, and a conclusion, a cause or an explanation no source states — and
  that it then checks the rest of the rules against the whole draft before answering;
- a sentence, before every rule block, saying that each rule below says what the report must do
  or what counts as a violation, that the transcript before the instructions is the findings, and
  that the draft is judged against them and every passage that breaks a rule is reported; and that
  when a rule asks the report to give a value or its context, such as both a dataset value and a
  publication value, and the findings hold it but the draft leaves it out, the grounded review
  reports it and asks for it to be added, unless a rule keeps that content out of the report;
- the generic policies' blocks, in the policy order (see **source-selection**): the
  source-selection block, with the source-selection terms and every source-selection rule's
  **report-writer** part; the faithful-relay block, with the faithful-relay terms and every
  faithful-relay rule's **report-writer** part; and the **grounded** parts of the other policies'
  rules, such as "Names, not codes" (see **language-and-style**) and "Accurate and consistent
  terms" (see **terminology**). The source-selection and faithful-relay rules are given in their
  writer parts, as what the report must do, because their blind parts assume a reviewer who cannot
  see the sources;
- the writer's "No calculations" section, as a section of its own (see Rule 3);
- the grounded parts of the channel's client rules, in a `<client_rules>` block, when a client rule
  sets one;
- the writer parts of the channel's client rules, in a `<client_writer_rules>` block under its own
  heading, when a client rule sets one, introduced as context and not as checks: the grounded
  review does not report a passage under them unless a client check names it, uses them to know
  which content the report must leave out and which terms it must use, and never asks for content
  they keep out of the report. This is how the grounded review can ask for a missing value without
  asking for content a client rule excludes; the client rules' blind parts, which judge exclusions,
  stay with the blind review;
- the turn's data-sources string in a `<data_sources>` block, which counts as a source;
- that the transcript before the instructions is the findings, to be used for every check that
  compares the report with its sources, and that a claim the findings hold only in a search tool's
  summarising answer is not supported by a source;
- what is not its job: whether the research was thorough; whether the draft answers every part of
  the question and the plan, which the blind review judges and which the channel's own rules may
  narrow; whether a claim carries a citation or where a citation stands, which the blind review
  judges; which of two terms with the same meaning the report uses for a concept, which the
  channel's own rules may set; the report's sections, headings, Markdown and citation format,
  which the blind review judges; the length, hyperlinks, and whether a cited identifier exists,
  which the app checks itself; it never asks for more research, more sources, a different
  analysis, a rewrite or wording it would prefer;
- that it answers with a numbered list, one item per violation, naming the rule it breaks, the
  passage quoted exactly, what the source says instead and what to change, where a violation the
  draft repeats in several places is one item that quotes every place; or with exactly
  `No violations.` when the draft breaks none; and that it calls no tool. The answer format SHALL
  state the layout the answer is read by, below: each item starts on a new line with its number, a
  full stop and a space, with nothing before the number, and every further line of an item is
  indented. It SHALL give a short example of two items.

**Why both reviews check the source-selection and faithful-relay rules.** The blind review judges
these rules by their blind parts, and the grounded review by their writer parts. The duplication is
deliberate, and SHALL stay until an eval shows that the blind review finds nothing the grounded
review misses:

- the two checks of the faithful-relay rules were evaluated together, so dropping either one risks
  a regression;
- the blind parts carry sentences whose only job is to stop a review from flagging a correct draft,
  such as "a table's year column states the described period of every value in it", which the
  grounded review does not receive;
- a failed review call does not fail the turn, so the blind review still checks a draft when the
  grounded call fails.

The grounded review lacking those guarding sentences is a known risk for the source-selection
rules, whose writer parts it newly receives: it may flag a correct draft that the blind review would
pass. The eval of this change SHALL check the grounded review's source-selection items for such
mistakes. The code that renders the grounded review's instructions SHALL state the duplication and
this risk in a comment.

The grounded review SHALL NOT receive the client rules' research parts, any rule's blind part, the
blind review's numbered checks or the glossary rule. No tool SHALL be bound and no
output schema SHALL be set. It SHALL use the default chat model at reasoning effort `medium`.

Its answer SHALL be read as a numbered list: each numbered item is one violation, and the lines
under an item belong to it. A line SHALL open a new item only when it starts, unindented, with the
next number in sequence, so an indented sub-list or a line that starts with a year stays inside the
item above it. An answer that is `No violations.`, ignoring case, surrounding whitespace, Markdown
wrapping such as backticks, asterisks or quotes, and trailing punctuation, SHALL add no item. A
non-empty answer with no numbered line SHALL be one item, so a violation is never dropped silently.
An empty answer SHALL count as a failed grounded review, not as an approval.

#### Scenario: The grounded review's messages and roles

- **WHEN** report review judges a draft
- **THEN** the grounded review SHALL receive a system message, then the writer's transcript,
  then two more system messages: the instructions, then the request ending in the draft

#### Scenario: The grounded review sees the transcript the writer saw

- **WHEN** research-agent fetched a page in image mode and announced steps with `update_status`
- **THEN** the grounded review's transcript SHALL carry the page's image and SHALL NOT carry the
  status calls or their acknowledgements, exactly as the report writer's transcript does

#### Scenario: The grounded review carries the writer parts, the grounded parts and the terms

- **WHEN** the grounded review's instructions are rendered on a channel with a glossary and client
  rules, one of which sets a grounded part
- **THEN** they SHALL carry the source-selection and faithful-relay terms, the source-selection and
  faithful-relay rules' report-writer parts, every generic rule's grounded part, and that client
  rule's grounded part in a `<client_rules>` block, every client rule's writer part in a
  `<client_writer_rules>` block introduced as context, and SHALL carry no rule's blind part, no
  client rule's research part, no glossary rule and none of the blind review's numbered checks

#### Scenario: A term with the same meaning set by a channel rule is not a violation

- **WHEN** a channel's own rule makes the writer use another term than a source's for one concept,
  with the same meaning, and the draft does so
- **THEN** the grounded review's instructions SHALL have said that which of two terms with the same
  meaning the report uses is not its to judge

#### Scenario: A missing value is asked for

- **WHEN** the findings hold a publication value and a dataset value for one fact, and the draft
  gives only the dataset value
- **THEN** the grounded review SHALL report the missing publication value and ask for it to be added

#### Scenario: An excluded value is not asked for

- **WHEN** a client rule's writer part keeps some values out of the report, and the draft leaves
  such a value out although the findings hold it
- **THEN** the grounded review's instructions SHALL carry that writer part as context and SHALL say
  never to ask for content it keeps out of the report

#### Scenario: Without client writer rules there is no context section

- **WHEN** the channel configures no client rule with a writer part
- **THEN** the grounded review's instructions SHALL carry no `<client_writer_rules>` block and no
  sentence that refers to one

#### Scenario: The answer format is stated with an example

- **WHEN** the grounded review's instructions are rendered
- **THEN** their answer section SHALL say that each item starts on a new line with its number and a
  full stop, with further lines indented, and SHALL carry an example of two numbered items

#### Scenario: An empty answer is a failed grounded review

- **WHEN** the grounded review's call returns no text
- **THEN** the grounded review SHALL add no item, a warning SHALL record the failure, and the stage
  SHALL record that the grounded review failed rather than that the draft satisfies every check

#### Scenario: A wrapped approval is an approval

- **WHEN** the grounded review answers `` `No violations.` `` or `**No violations.**`
- **THEN** it SHALL add no item

#### Scenario: A clean draft

- **WHEN** the grounded review answers `No violations.`
- **THEN** it SHALL add no item to the review's violations

#### Scenario: An answer that opens with "No violations" but lists one keeps it

- **WHEN** the grounded review answers "No violations of the other rules." followed by one numbered
  item
- **THEN** that item SHALL join the review's violations

#### Scenario: A figure no source gives is found

- **WHEN** a draft states a 44% share, citing a page that does not give it, and only a search
  answer in the transcript says 44%
- **THEN** the grounded review SHALL report the sentence as a violation
