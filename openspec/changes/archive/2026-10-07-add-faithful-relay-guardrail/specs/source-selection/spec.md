## MODIFIED Requirements

### Requirement: A quality rule is one bundle of step instructions

A quality rule SHALL be one named bundle of up to four instructions, one for each research step:
the research agent, research review, the report writer and report review. The application's
generic rules and a channel's client rules (see **application-config-schema**) SHALL have the same
shape.

Each step's system prompt SHALL carry that step's part of every rule, each under its rule's name,
in the order the rules are defined. A rule with no part for a step SHALL add nothing to that
step's prompt, not even its name.

The generic rules SHALL be grouped into policies: source selection, then faithful relay (see
**faithful-relay**). Each policy SHALL be rendered as a block of its own, with a heading and an
opening sentence for each step, in that order, and the client rules SHALL follow the last one. A
policy with no part for a step SHALL add no block to that step's prompt. Report review's blocks
SHALL present their parts as checks. The statement of the channel's kinds of source SHALL open the
source-selection block, whose parts it governs.

The parts of one rule SHALL fit together: a step SHALL NOT be asked to check or to present what
the earlier steps were not asked to produce, and no step SHALL be asked for what it cannot do.
Three constraints follow from what the steps can do:

- **A part about one kind of source applies only where the channel has it.** A channel may
  configure datasets only, or documents only. Each step's generic block SHALL state which kinds of
  source the channel has, taken from its configured servers: a document server gives it
  publications, and a dataset server gives it datasets. When the channel lacks one kind, the
  statement SHALL say that the parts about that kind do not apply. A part that concerns datasets,
  or publications, SHALL apply only where the channel has that kind, and no part SHALL require a
  retrieval from a kind of source the channel does not have. The model is told the kinds rather
  than left to infer them from the data-sources text, whose descriptions an admin writes.

- **The research agent's part only ever asks for retrievals.** The research agent can only call
  tools; it writes no notes, summaries or comparisons. A part SHALL NOT ask it to record, note,
  summarise, compare or calculate anything. Where a rule needs a fact to be on record, the part
  asks the agent to make sure a tool result in the findings carries it.
- **Research review asks only for steps the research agent can take.** Research review's prompt
  SHALL say that every next step it writes is a retrieval — which source to search, list, query or
  read, and for what — and never a summary, a comparison or a note, which the report writer does
  from the findings, nor a calculation, which nobody does (see **research-execution**, "Research
  looks for a stated figure rather than planning to compute one").

#### Scenario: A rule's part reaches only its step

- **WHEN** a rule defines a research-agent part and a report-writer part only
- **THEN** the research agent's and the report writer's system prompts SHALL each carry their
  part under the rule's name, and the research review and report review prompts SHALL carry
  neither the rule's name nor any of its text

#### Scenario: One edit changes the rule for every step

- **WHEN** the generic rule for dates is changed
- **THEN** the change SHALL be made in one definition, from which all four steps' prompts are
  rendered

#### Scenario: Research review asks for a retrieval, not a summary

- **WHEN** research review finds that two editions of a forecast were read but their difference
  was not explained
- **THEN** its next step SHALL ask for the pages or the methodology that could explain the
  difference, and SHALL NOT ask the research agent to compare or summarise the two values

#### Scenario: A channel with documents only

- **WHEN** a channel configures a document server and no dataset server
- **THEN** no step's part SHALL require a dataset query, and research review SHALL NOT report a
  missing dataset query or a missing dataset release as a gap

#### Scenario: Each step is told the channel's kinds of source

- **WHEN** a channel configures a dataset server and no document server
- **THEN** each step's generic block SHALL say that the channel has datasets and no publications,
  and that the parts about publications do not apply

#### Scenario: The policies render in order, each under its own heading

- **WHEN** any step's system prompt is rendered
- **THEN** it SHALL carry the source-selection block, then the faithful-relay block, then the client
  rules, each block under its own heading, and only the source-selection block SHALL open with the
  statement of the channel's kinds of source

#### Scenario: A policy with no part for a step adds no block

- **WHEN** a policy has no rule with a part for some step
- **THEN** that step's prompt SHALL carry neither the policy's heading nor its opening sentence

### Requirement: The rules and the existing prompt text do not contradict each other

Where the text a step's prompt already carries would contradict a generic rule, that text SHALL be
amended in the same change, so a model never has to choose between two instructions:

- **Research agent.** Its pre-finish checklist SHALL exempt a publication's stated date from "every
  date confirmed on the page itself", since rule 7 takes it from the document metadata. The
  checklist SHALL gain an item for the generic rules, and the exception that lets a plan item count
  as done without evidence only a failed tool could give SHALL name the checklist items it applies
  to rather than pointing at "the last check"; it SHALL apply to the new item too.
- **Research review.** Its task sentence, its list of gaps, its sentence saying that research is
  complete when every plan item is covered, its scope paragraph, the description of its output
  schema and the descriptions of its two output fields SHALL each include the gaps the rules
  define, so that none of them tells the model that plan coverage alone completes research. Its
  existing gap for a planned comparison SHALL ask for the comparison's data, since the research
  agent retrieves data and never compares; and its gap for a figure, date or entity seen only in a
  search summary SHALL exempt a stated date taken from document metadata. The stage that shows
  research review's verdict to the user SHALL say the same: research is complete when the plan and
  the rules are covered.
- **Report writer.** Its list of rules that outrank the request SHALL include the source-selection
  prohibitions: a request never makes the report average or merge differing values, leave out a
  value's described period or the stated date of a forecast or an estimate, or present a near match
  as an exact match. A request may still narrow what the report covers. Where the report declines a
  request to average or merge differing values, it SHALL give each value separately with its source
  and say in one sentence that the values are given separately because the sources differ, as the
  one exception to the rule that the report does not explain a declined request. A request declined
  under the other two prohibitions is declined without comment.
- **Report review.** Its instruction to check "exactly these" SHALL name the checks of every rule
  section below it, the client-specific checks included, and all of them SHALL come before its
  "Not your job" section, whose "the checks above" then covers them.
- **Every step.** A sentence that names the rules a step follows, such as research review's task
  sentence, its gap bullet and its output schema's descriptions, or the research agent's checklist
  item, SHALL name the rule sections as a whole rather than the source-selection rules alone, since
  faithful relay defines gaps and checks too.

#### Scenario: A request to average two forecasts

- **WHEN** the question asks for "the average of the published growth forecasts" and the research
  found two differing forecasts
- **THEN** the report SHALL give each forecast with its source, its citation and its stated date,
  SHALL NOT give their average, and SHALL say that the values are given separately because the
  sources differ

#### Scenario: Research review does not finish on plan coverage alone

- **WHEN** every plan item has evidence and a rule's gap is open
- **THEN** no sentence of research review's prompt or of its output schema SHALL say that research
  is complete, and research review SHALL return a next step for the gap

#### Scenario: Research review's rule sentences cover faithful relay

- **WHEN** research review's prompt and output schema are rendered
- **THEN** none of their sentences that name the rules defining gaps SHALL name the
  source-selection rules alone

### Requirement: Rule 6 — every relevant value is kept, and a difference is explained

The rule's parts SHALL tell each step the following.

- **Research agent:** looks for other sources that give a value for the same fact, and for what
  explains any difference between them.
- **Research review:** the rule's only gap is a difference already found in the findings whose
  explanation was not looked for. Research review never plans a search for further sources that
  might disagree, because such a search has no natural end. This limit applies to rule 6 alone:
  the gaps the other rules define, including the checks rules 2 and 4 require, still stand.
- **Report writer:** gives every differing value, naming its source in the text and citing it,
  and says why the values differ or that the sources do not explain it. "The forecast was updated
  between the two dates" is a valid reason, and so is a methodology change between two editions,
  which leaves neither value superseded. Values are never averaged or merged, and a value is left
  out only when it is obviously outdated or irrelevant. Omitting a relevant value costs more than
  including one.
- **Report review:** judges only what the draft shows. A range or an average spanning two sources'
  values for the same fact is a violation, and so are two values for the same fact that the draft
  presents as differing unless each carries its own citation and a reason, or the statement that the
  sources do not explain the difference. A figure computed from values of different facts, such as
  the difference between two indicators' growth rates, merges no values for one fact and is outside
  this check; report review's "No calculations" check covers it (see **report-composition**,
  "Reports contain no calculations"). Whether a figure carrying two citations hides a disagreement
  is not report review's to judge, because it cannot see the sources.

#### Scenario: Two editions with a methodology change

- **WHEN** two editions of one publication give different values for the same fact and the later
  one changed its sample
- **THEN** the report SHALL give both values, each with its citation and stated date, and SHALL
  say that the methodology changed between the editions

#### Scenario: Differing values merged into a range

- **WHEN** a draft states "growth is forecast at 3.2% to 3.4% in 2026" and cites one source for
  each end of the range
- **THEN** report review SHALL report a violation asking for each value on its own, with its
  citation and the reason for the difference, or the statement that the sources do not explain it

#### Scenario: A difference between two indicators is not a merged value

- **WHEN** a draft gives a column of differences between export growth and GDP growth, each
  computed from two cited values of different indicators
- **THEN** report review SHALL NOT report the column under this rule as a range or an average of
  differing values, and SHALL report it under report review's "No calculations" check as figures
  computed from other figures

#### Scenario: Research review does not start an open-ended search

- **WHEN** the findings hold one value for a fact and no other source was found
- **THEN** research review SHALL NOT plan a search for further sources that might disagree
