# source-selection Specification

## Purpose

How each research step finds, keeps and presents the values that several sources and editions give
for the same fact: the quality-rule bundle each step's prompt is built from, the source-selection
terms and rules, and how a channel's own rules reach the steps.

## Requirements

### Requirement: A quality rule is one bundle of step instructions

A quality rule SHALL be one named bundle of up to five instructions, one for each research step:
the research agent, research review, the report writer, the blind review and the grounded review.
The blind review and the grounded review are the two calls that judge each draft (see
**faithful-relay**, "The grounded review checks the draft against the sources"). A rule SHALL set
at most one of its two review parts, because a check is judged by the one review that can decide
it: the blind review for a check that the draft alone decides, the grounded review for a check that
needs the research findings. A generic rule that sets both SHALL fail when the application starts.
The application's generic rules and a channel's client rules (see **application-config-schema**)
SHALL have the same shape.

Each step's system prompt SHALL carry that step's part of every rule, each under its rule's name,
in the order the rules are defined. A rule with no part for a step SHALL add nothing to that
step's prompt, not even its name.

The generic rules SHALL be grouped into policies: source selection, faithful relay (see
**faithful-relay**), terminology (see **terminology**), language and style (see
**language-and-style**), and removal (see **prohibited-content**). Each policy SHALL be rendered as
a block of its own, with a heading and an opening sentence for each step, in that order, and the
client rules SHALL follow the last one. A policy with no part for a step SHALL add no block to that
step's prompt. The two reviews' blocks SHALL present their parts as checks. The statement of the
channel's kinds of source SHALL open the source-selection block, whose parts it governs.

A policy MAY carry **terms**: the definitions its rules use. The terms SHALL NOT be a rule. They
SHALL be rendered at the top of the policy's block, under their own name, in every step whose
prompt carries the block, and they alone SHALL NOT make a block appear. A policy MAY give one step
longer terms than another, as source selection gives the two research steps one more term.

A policy MAY carry rules that apply only on a channel that configures a glossary. They SHALL be
rendered only on such a channel.

**Two policies are judged by both reviews.** The source-selection and faithful-relay rules set no
grounded part. The grounded review SHALL judge the draft against their report-writer parts, rendered
in its prompt as its part of those two policies, and neither policy's rules SHALL set a grounded
part. Every other policy's rules reach the grounded review only through their grounded parts. The
reasons both reviews check these two policies are given in **faithful-relay**, "The grounded review
checks the draft against the sources".

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

- **WHEN** a client rule defines a research-agent part and a report-writer part only
- **THEN** the research agent's and the report writer's system prompts SHALL each carry their
  part under the rule's name, and the research review, blind review and grounded review prompts
  SHALL carry neither the rule's name nor any of its text

#### Scenario: One edit changes the rule for every step

- **WHEN** the generic rule for dates is changed
- **THEN** the change SHALL be made in one definition, from which every step's prompt that carries
  the rule is rendered

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
- **THEN** it SHALL carry, of the source-selection, faithful-relay, terminology, language-and-style
  and removal blocks, those that have a part for that step, in that order, then the client rules,
  each block under its own heading, and only the source-selection block SHALL open with the
  statement of the channel's kinds of source

#### Scenario: A rule that sets both review parts is rejected

- **WHEN** a quality rule sets both a blind-review part and a grounded-review part
- **THEN** validation SHALL reject it, naming the rule

#### Scenario: The terms make no block on their own

- **WHEN** a policy carries terms and none of its rules has a part for some step
- **THEN** that step's prompt SHALL carry neither the policy's heading nor its terms

#### Scenario: The grounded review receives the source-selection writer parts

- **WHEN** the grounded review's instructions are rendered
- **THEN** they SHALL carry a source-selection block with the source-selection terms and every
  source-selection rule's report-writer part, and no source-selection rule's blind part

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

### Requirement: Client rules follow the generic rules in a tagged block

A channel's client rules SHALL reach each step whose part they set, after the generic rules, in a
`<client_rules>` block. Inside the block each part SHALL appear under its rule's name. The text
around the block SHALL say that these rules come from the channel's configuration, that they add
to the rules above them, and that where a client rule is more specific than a generic rule the
client rule is followed, with one exception: the rule that nobody calculates (see
**research-execution**, "Research looks for a stated figure rather than planning to compute one",
and **report-composition**, "Reports contain no calculations") has the highest priority of all the
rules, and no client rule overrides it. The text SHALL state that exception at every step whose
prompt carries the block.

When no client rule has a part for a step, that step's prompt SHALL carry neither the block nor
the text around it.

The generic rules SHALL name no client, no client dataset, no client publication and no client
domain. What a client's sources contain SHALL be said only in that channel's client rules: whether
its datasets document their methodology or keep earlier releases, where its publications document
methodology, which metadata key carries a publication's date, and which tool lists its documents.

#### Scenario: A client rule for one step

- **WHEN** a channel configures one client rule, "Dataset methodology", with only a research-agent
  part
- **THEN** the research agent's system prompt SHALL carry a `<client_rules>` block with that part
  under "Dataset methodology", after the generic rules, and no other step's prompt SHALL carry a
  `<client_rules>` block

#### Scenario: A channel without client rules

- **WHEN** a channel configures no client rules
- **THEN** no step's prompt SHALL carry a `<client_rules>` block or the text that introduces one,
  and every step's prompt SHALL still carry its part of the generic rules

#### Scenario: A client rule asks for a calculation

- **WHEN** a channel's client rule asks the writer to give the year-on-year change of each series
- **THEN** the text around the `<client_rules>` block SHALL say that no client rule overrides the
  rule that nobody calculates, and the report SHALL NOT compute the changes

### Requirement: The source-selection terms are given to every step

Every step's prompt, the grounded review's included, SHALL carry the same definitions of the terms
the source-selection rules use, at the top of the source-selection block, before the rules, and
SHALL present them as definitions rather than as a rule or a check to
follow. The last term, "Reasonable attempt", concerns searching and when a failed tool may be
called again, which only the research agent and research review deal with, so only those two steps
SHALL carry it. Its
reference to a failed tool SHALL resolve in both prompts: the research agent's rules on failed tool
calls and research review's rule that a tool-failure result is not planned again both say when a
tool may not be called again.

- **Fact**: what the question asks for, as a figure or a finding stated in words, with its
  indicator, scope, geography, period and scenario.
- **Value**: a figure or a finding that a source gives for a fact.
- **Exact match**: a value that agrees with the fact on all of these.
- **Near match**: a value that differs from the fact in one of them, such as a narrower geography
  or a narrower scope.
- **Stated date**: when the source stated the value. For a publication it is the publication date
  in the document's metadata; an edition name, such as a volume or issue number, is not a stated
  date. For a dataset value it is the dataset's last update.
- **Described period**: the period the value is about. A forecast for 2027 made in 2025 has the
  stated date 2025 and the described period 2027.
- **Previous value**: the value for the previous period (year, quarter or month), or the value
  from the previous edition.
- **Methodology**: the details a source gives on how a figure or an analysis was obtained, such as
  its geography, time range, sectors and other splits, sample size, adjustments and definitions.
- **Qualifying context**: what a source states that changes how a value is read. This is its
  methodology, and also its assumptions, scenario conditions, limitations and caveats, such as
  "preliminary estimate", "the baseline assumes unchanged policies" or "excludes financial
  services".
- **Supersede**: a newer value may supersede an older one for the same fact only when the two
  were obtained with a methodology that is obviously identical, or very likely so. Editions of one
  publication series usually share a methodology, but the series alone decides nothing. When the
  methodology differs or is unclear, such as a changed sample, model or coverage, neither value
  supersedes the other, and the report gives both. A dataset value is never superseded, because a
  dataset is an independent source. A dataset value never supersedes a publication's value
  either.
- **Obviously outdated**: a value that meets all four conditions: a newer retrieved value for the
  same fact supersedes it; it is neither the latest nor the previous edition; the question does not
  ask how the value evolved; and it does not contribute meaningfully to answering the question. It
  is never judged from the model's own knowledge.
- **Reasonable attempt**: at least two searches for the evidence that differ in wording or in
  scope, such as a metadata filter, neither of which found it. Evidence that only a failed tool
  could give counts as missing once that tool has failed for it and may not be called again for
  it.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent and research review SHALL each carry all twelve
  definitions above, and the system prompts of the report writer, the blind review and the
  grounded review SHALL each carry the first eleven, without "Reasonable attempt"

### Requirement: Rule 1 — missing evidence is accepted after a reasonable attempt

Any evidence the other rules ask for, including a methodology or a date, may not exist.

The rule's parts SHALL tell each step the following.

- **Research agent:** makes a reasonable attempt to find it, then moves on without it.
- **Research review:** keeps the gap open until the findings show a reasonable attempt, then
  treats the evidence as missing rather than as a gap.
- **Report writer:** states what is missing and what therefore cannot be concluded, as it does for
  evidence that could not be retrieved.
- **Report review:** a check that asks for some evidence, such as a stated date or the reason for a
  difference, is satisfied by a statement that the sources do not give it.

#### Scenario: A missing previous edition stops being a gap

- **WHEN** the findings show two differently worded searches for the previous edition of a
  forecast, neither of which found it
- **THEN** research review SHALL NOT plan a further search for it, and the report SHALL say that
  no earlier edition was found

#### Scenario: A stated date the sources do not give

- **WHEN** a draft gives a forecast and says that its source gives no publication date
- **THEN** report review SHALL NOT report the missing stated date as a violation

### Requirement: Rule 2 — the latest value leads

The rule's parts SHALL tell each step the following.

- **Research agent:** looks for the latest value of every fact in each kind of source the channel
  has: the latest dataset release and the latest publication edition. Where the channel has both,
  a dataset value does not make the search of the publications unnecessary. A
  dataset's entry in the data sources was fetched at the start of the turn and is its latest
  release, so a dataset value needs no check for a later release. A search's first results are not
  necessarily a publication's latest edition, so the agent checks for a later one, for example
  with a search scoped to recent publication dates or with the document listing. This matters most
  for forecasts, for estimates of past events that are recalculated as information arrives, such
  as the turnout of a past election, estimated before the final count, and for figures revised
  later. A later value can
  come from another publication type or series than the one first found, so the check is scoped
  by publication date, not by the first result's type or series. A listing shows titles and dates,
  not values, so a later document whose title or topic could cover the fact is searched or read.
  When the latest edition does not give the value, the agent checks the edition before it, and so
  on: the latest value is the one from the most recent edition that states it.
- **Research review:** where the channel has publications, a fact the question asks about with no
  search of the publications for its latest value is a gap, even when a dataset gives its value. A
  value taken from a publication, with no check for a later edition, is also a gap. A dataset value needs no check for a later
  release. A check covers only what it searched: one confined to the type or series of the value
  found leaves a gap, and so does a later listed document whose title or topic could cover the
  fact and that was never searched or read. When the latest edition read does not give the value,
  the earlier editions never searched or read are a gap until one gives it.
- **Report writer:** the most recent exact match leads.

#### Scenario: A later edition exists

- **WHEN** the research finds a forecast in one edition of a periodic publication and a later
  edition of the same publication gives a new forecast for the same fact
- **THEN** the report SHALL lead with the later edition's value

#### Scenario: A dataset value is not rechecked

- **WHEN** the findings hold a data query's value and the data sources show the dataset's last
  update
- **THEN** research review SHALL NOT plan a check for a later release of that dataset

#### Scenario: A listing is not a check for a later value

- **WHEN** the findings take a forecast from an annual report, and the only check for a later
  value is a document listing filtered to that report's publication type, or a listing whose later
  documents were judged by their titles and never searched or read
- **THEN** research review SHALL report a gap asking for a search scoped to publication dates after
  the report's, across publication types

#### Scenario: A dataset value does not close the fact

- **WHEN** the plan names only datasets, a data query gives the value of a fact the question asks
  about, and the findings show no search of the publications for that fact
- **THEN** research review SHALL report a gap asking for a search of the publications for the
  fact's latest value

#### Scenario: A channel without publications

- **WHEN** a channel's data sources include datasets and no publications, and a data query gives
  the value of a fact the question asks about
- **THEN** research review SHALL NOT report a missing search of the publications as a gap

### Requirement: Rule 3 — previous values are added where they give context

The report gives what the user asked for. A previous value is added only where it gives context
and makes sense. It does for a forecast, whose previous edition shows how the view moved. A value
for the previous period does not for a one-off event, which has no previous period; a previous
edition of an estimate of such an event, recalculated as information arrived, is an earlier value
for the same fact and falls under rules 2 and 6.

The rule's parts SHALL tell each step the following.

- **Research agent:** retrieves every value the question asks for, including every edition when
  the question asks how the value evolved, and the previous value where it gives context. For a
  forecast taken from a publication, it reads the previous edition, found in the document listing,
  for its forecast of the same fact. A later edition's quote of the previous value does not replace
  that read, because the quote does not carry the previous value's stated date.
- **Research review:** a value the question asks for that is not in the findings is a gap. For a
  forecast taken from a publication, the previous edition's forecast for the same fact is a gap
  until the findings show that edition read, and a later edition's quote of it does not close the
  gap. A dataset forecast's previous release is a gap only where a client rule says the datasets
  keep earlier releases, because whether they do depends on the channel's data. No other previous value
  is a gap. The part states the
  forecast's gap as a requirement and says "not in the findings" rather than "missing", which rule
  1 uses for evidence not found after a reasonable attempt.
- **Report writer:** gives every value the question asks for, and a previous value where it gives
  context. For a question about the current forecast, the latest forecast is required and the
  previous edition is added context; for a question about how a forecast evolved, every edition is
  required.

#### Scenario: How a forecast evolved

- **WHEN** the question asks how a forecast evolved and the research found four editions that give
  it
- **THEN** the report SHALL give the value of every edition, each with its stated date and
  citation

#### Scenario: The current forecast

- **WHEN** the question asks for the current forecast of an indicator and the previous edition
  gave another value
- **THEN** the report SHALL lead with the latest forecast and SHALL give the previous edition's
  value as context

#### Scenario: A previous forecast known only from a later edition's quote

- **WHEN** the question asks for the current forecast of an indicator, and the latest edition says
  the forecast is "down from 1.5%" while the findings hold no read of the previous edition
- **THEN** research review SHALL report a gap asking for the previous edition, so that the previous
  forecast's stated date can be given

#### Scenario: A one-off event

- **WHEN** the question asks for the losses of one past event
- **THEN** research review SHALL NOT treat a missing value for a previous period as a gap

#### Scenario: A dataset forecast has no previous release to find

- **WHEN** a data query gives a forecast and no client rule says the dataset keeps earlier releases
- **THEN** research review SHALL NOT plan a search for the dataset's previous release

### Requirement: Rule 4 — a dataset holding the indicator is queried and is always cited

The rule's parts SHALL tell each step the following.

- **Research agent:** when a dataset holds the indicator, queries it, even when a publication
  gives a value.
- **Research review:** an indicator of a fact the question asks about, held by a dataset that was
  never queried for it, is a gap.
- **Report writer:** cites the data query that returned the dataset value, even when a newer
  publication gives a different value, because a dataset is an independent source. A dataset value
  never replaces a publication's value either: the report gives both, each with its citation and
  its stated date, unless the publication's value is obviously outdated or irrelevant. When a
  publication gives the same figure, the dataset is primary, and a publication that only repeats it
  may be left out.

#### Scenario: A publication and a dataset give the same figure

- **WHEN** a publication and a data query give the same value for the same fact
- **THEN** the report SHALL cite the data query for it and MAY leave the publication out

#### Scenario: A newer publication gives another value

- **WHEN** a dataset last updated in April gives a 2026 growth forecast of 3.4% and a publication
  from June gives 3.2% for the same fact
- **THEN** the report SHALL give both values, each with its source named, its citation and its
  stated date, and SHALL NOT drop the dataset value as superseded

#### Scenario: A newer dataset value does not replace a publication's value

- **WHEN** a publication from January gives a 2026 growth forecast of 3.2% and a dataset last
  updated in April gives 3.4% for the same fact
- **THEN** the report SHALL give both values, each with its citation and its stated date, and SHALL
  NOT drop the publication's value as superseded by the dataset's

### Requirement: Rule 5 — the qualifying context that changes how a value is read is retrieved

Where a client documents methodology differs by client, so a channel's client rules say it. The
rule is named "Qualifying context": a value's methodology is one kind of qualifying context, and its
assumptions, scenario conditions, limitations and caveats are the others (see the term in "The
source-selection terms are given to every step").

The rule's parts SHALL tell each step the following.

- **Research agent:** for every value the report may use, retrieves its qualifying context,
  wherever the sources document it, such as methodology pages, boxes, footnotes
  and notes under tables and charts. Without it a superseded forecast cannot be told from a
  disagreement.
- **Research review:** for a value of a fact the question asks about, qualifying context the
  findings show is documented, because a page that was read or a search result points to it, and
  that was
  not read, is a gap.
- **Report writer:** gives a value's qualifying context with the value, where it materially
  affects how the value is read.

#### Scenario: Two values differ in definition

- **WHEN** two sources give different values for a country's unemployment rate, and the
  methodology of one counts only urban areas
- **THEN** the report SHALL state that difference in definition beside the two values

#### Scenario: A forecast's assumption is given with it

- **WHEN** a publication gives a GDP growth forecast and states that its baseline assumes unchanged
  policies
- **THEN** the research agent's prompt SHALL ask for that assumption to be retrieved, and the
  report SHALL give it with the forecast

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

### Requirement: Rule 7 — every value carries its dates

The rule's parts SHALL tell each step the following.

- **Research agent:** makes sure the findings carry the stated date and the described period of
  every value it may use. A dataset value's stated date is the dataset's last update, which the
  data sources or the data-query result give. A publication's stated date is the publication date
  in the document metadata a tool returns — never a date in the page text, which can carry a stale
  template date, and never an edition name. The document listing returns documents with the
  metadata fields the channel makes filterable, but may return one page of results at a time and
  may not look a document up by id. So when the research uses a publication, the agent lists the
  documents once per research, narrowed
  by a publication-date filter where the plan allows rather than by publication type, which would
  hide a later value of another type (rule 2), with a limit that covers every matching document or
  by paging through them, and reads the date of each document it uses from that list. It lists
  again, without the filter or with the next page, only for a document the list does not include.
  One listing entry settles a document's stated date: when the entry carries no date, the date is
  missing (rule 1). A channel whose publication date the listing does not return names another
  source for it in a client rule.
- **Research review:** a value for a fact the question asks about, given in the findings without
  one of its dates, is a gap. A listing entry for a document settles that document's stated date,
  whether it carries a date or not. A publication's stated date is its publication date, so
  research review never asks for a separate forecast vintage, data cut-off or as-of date.
- **Report writer:** every value states its described period. The stated date is stated where it
  makes a difference: for a forecast, for an estimate, and for a value shown beside a value for
  the same fact stated on another date. It is written as a date, never as an edition name alone,
  and a publication's is taken from the document metadata in the findings, never from a date
  printed on its pages.
- **Report review:** a value without its described period, or a forecast or an estimate without
  its stated date, is a violation. This includes a previous forecast the draft gives only as the
  starting point of a revision, such as "revised down from 1.5%". An edition name alone is not a
  stated date. A table's year column or row label states the described period of every value in
  it, so report review does not ask to mark such values as historical or actual.

#### Scenario: A forecast without its stated date

- **WHEN** a draft says "GDP is forecast to grow by 3.2% in 2026" with a citation and no date on
  which the forecast was made
- **THEN** report review SHALL report a violation asking for the forecast's stated date

#### Scenario: An edition name instead of a date

- **WHEN** a draft gives a forecast "from the third issue of 2025" and no date
- **THEN** report review SHALL report a violation asking for the stated date

#### Scenario: A publication date is taken from the metadata

- **WHEN** the research uses a figure from a publication whose page text carries a date different
  from its publication date in the document metadata
- **THEN** the report SHALL give the publication date from the metadata as the stated date, although the page text is also in the findings

#### Scenario: A listing's first page misses a used document

- **WHEN** the document listing returns its first page and a document the research uses is not on
  it
- **THEN** the research agent SHALL list again, without the filter or with the next page, and SHALL
  take the document's stated date from the entry it finds, or treat the date as missing when no
  entry is found

### Requirement: Rule 8 — near matches are labelled when no exact match exists

The rule's parts SHALL tell each step the following.

- **Research agent:** when no exact match exists, looks for the nearest matches by scope,
  geography and period, such as the smallest region or grouping that contains a country or the
  nearest years, in the same sources it searches for the exact match.
- **Research review:** a fact the question asks about with no exact match in the findings, and no
  search for its nearest matches, is a gap. The nearest matches are few, so research review asks
  only for those. The part exists because the evals showed the research agent skipping near
  matches when nothing asked for them, and a search for the nearest matches has a natural end,
  unlike rule 6's search for further sources.
- **Report writer:** presents the near matches found, labels each with how it differs from what was
  asked, and states the limitation.
- **Report review:** a near match presented without how it differs is a violation.

#### Scenario: Research review asks for the nearest region

- **WHEN** the question asks for a figure for a country, the findings show no value for it, and
  no search for the region that contains the country
- **THEN** research review SHALL report a gap asking for that region's value

#### Scenario: Only a narrower geography is available

- **WHEN** the question asks for a figure for a region, and the research found it only for one
  country of that region
- **THEN** the report SHALL present the country figure, say that it covers only that country, and
  state that the regional figure was not found

### Requirement: Source selection is verified by evals

The effect of these rules on research and reports depends on model behavior, which unit tests
cannot establish. Unit tests SHALL establish what each step's prompt carries. The behavior SHALL
be checked by running questions on a local stack, including at least one question about how a
forecast evolved, and by the Deep Research eval's test cases. Their ground truth follows these
rules.

#### Scenario: A question about how a forecast evolved

- **WHEN** a local stack is asked how a periodic forecast evolved
- **THEN** the report SHALL give several editions' values, each with its citation and stated date,
  and the research findings SHALL show a document listing from which the dates were taken
