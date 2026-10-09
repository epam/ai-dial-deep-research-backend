## MODIFIED Requirements

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

## RENAMED Requirements

- FROM: `### Requirement: Rule 5 — the methodology that changes how a value is read is retrieved`
- TO: `### Requirement: Rule 5 — the qualifying context that changes how a value is read is
  retrieved`
