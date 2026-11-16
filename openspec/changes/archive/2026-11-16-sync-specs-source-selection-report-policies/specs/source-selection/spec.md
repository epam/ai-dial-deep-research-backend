## RENAMED Requirements

- FROM: `### Requirement: Rule 1 — missing evidence is accepted after a reasonable attempt`
- TO: `### Requirement: Rule 10 — missing evidence is stated only for what the user asked for`

- FROM: `### Requirement: Rule 2 — the latest value leads`
- TO: `### Requirement: Rule 3 — the latest value is searched for in each kind of source`

- FROM: `### Requirement: Rule 3 — previous values are added where they give context`
- TO: `### Requirement: Rule 5 — other periods and earlier values are given only when asked for`

- FROM: `### Requirement: Rule 4 — a dataset holding the indicator is queried and is always cited`
- TO: `### Requirement: Rule 4 — the datasets are searched through their structures`

- FROM: `### Requirement: Rule 5 — the qualifying context that changes how a value is read is retrieved`
- TO: `### Requirement: Rule 7 — the qualifying context of each value is retrieved`

- FROM: `### Requirement: Rule 6 — every relevant value is kept, and a difference is explained`
- TO: `### Requirement: Rule 2 — every current value is given with its own citation`

- FROM: `### Requirement: Rule 7 — every value carries its dates`
- TO: `### Requirement: Rule 8 — every value carries its described period`

- FROM: `### Requirement: Rule 8 — near matches are labelled when no exact match exists`
- TO: `### Requirement: Rule 9 — only the nearest matches are given when no exact match exists`

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

- **WHEN** the generic rule "Stated date and described period" is changed
- **THEN** the change SHALL be made in one definition, from which every step's prompt that carries
  the rule is rendered

#### Scenario: Research review asks for a retrieval, not a summary

- **WHEN** research review finds that a retrieved page refers to a methodology section for a
  value, and the findings show no read of that section
- **THEN** its next step SHALL ask to read that section, and SHALL NOT ask the research agent to
  compare or summarise values

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
  date confirmed on the page itself", since the rule "Stated date and described period" takes it
  from the document metadata. The checklist SHALL gain an item for the generic rules, and the
  exception that lets a plan item count as done without evidence only a failed tool could give
  SHALL name the checklist items it applies to rather than pointing at "the last check"; it SHALL
  apply to the new item too.
- **Research review.** Its task sentence, its list of gaps, its sentence saying that research is
  complete when every plan item is covered, its scope paragraph, the description of its output
  schema and the descriptions of its two output fields SHALL each include the gaps the rules
  define, so that none of them tells the model that plan coverage alone completes research. Its
  existing gap for a planned comparison SHALL ask for the comparison's data, since the research
  agent retrieves data and never compares; and its gap for a figure, date or entity seen only in a
  search summary SHALL exempt a stated date taken from document metadata. The stage that shows
  research review's verdict to the user SHALL say the same: research is complete when the plan and
  the rules are covered.
- **Report writer.** Its list of rules that outrank the request SHALL include three source-selection
  prohibitions, each with the name of its rule. A request never makes the report average or merge
  differing values ("Every current value, with its own source"). A request never makes the report
  leave out a value's described period ("Stated date and described period"). A request never makes
  the report present a near match as an exact match ("Nearest matches when no exact match
  exists"). A request may still narrow what the report covers. Where the report declines a request
  to average or merge differing values, it SHALL give each value separately with its source and say
  in one sentence that the values are given separately because the sources differ, as the one
  exception to the rule that the report does not say it declined part of a request. A request
  declined under the other two prohibitions is declined without comment.
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
- **THEN** the report SHALL give each forecast separately with its source and its own citation,
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
domain. What a client's sources contain, and a rule that holds only for them, SHALL be said only in
that channel's client rules. Examples are whether its datasets document their methodology or keep
earlier releases, where its publications document methodology, which metadata key carries a
publication's date, which tool lists its documents, and the order in which the report gives a
dataset value and a publication value.

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
SHALL present them as definitions rather than as a rule or a check to follow. The last term,
"Reasonable attempt", concerns searching, which only the research agent and research review deal
with, so only those two steps SHALL carry it. The term SHALL NOT say how a failed tool call is
handled. The research agent's prompt and research review's prompt each say that in their own
text.

The terms SHALL define the following, in this order:

- **Approved plan**: the research plan that the user approved before research started. A plan that
  research review writes is not the approved plan.
- **Requested fact**: one figure, or one finding in words, that the user asks for in the query or
  in the approved plan. Other statements in a source are not requested facts. A requested fact has
  the parts below, and the list is not complete:
  - **Indicator**: what is measured. A growth rate, a share or an index is a different indicator.
  - **Unit**: the currency, or the measure of the same quantity. A scale word, such as million, is
    notation, not a different unit.
  - **Scope**: the group that the value is about, such as one age group. When the query and the
    approved plan name no group, the scope is all groups, and a value for one group is a near
    match.
  - **Geography**: a country, a region or a group of countries.
  - **Period**: the described period. Its length is its frequency. Only a word such as "monthly",
    "quarterly" or "annual" names a frequency, and a time span such as "in 2024" names none. When
    no frequency is named, a value at any frequency within the time span matches, and the most
    appropriate frequency among those the sources give is chosen. When a frequency is named, a
    value at another frequency is a near match. The preparation phase settles the period before
    research starts. It asks the user, and when the user leaves the choice to it, it applies the
    last 10 years for past values and the next 3 years for forecasts.
  - **Scenario**: the case that the source names for a hypothetical value, such as "baseline". A
    hypothetical value is a forecast, a projection, or a value for an event that did not occur. A
    preliminary estimate for a period that had ended when the source stated it is not a
    hypothetical value: it is a value for the same requested fact as the final value. An observed
    value has no scenario. The assumptions of a value are
    qualifying context, not its scenario. A forecast that its source does not label has the
    baseline scenario. For a period that has ended, the observed value is the exact match and a
    forecast is a near match, which the report gives only when no observed value exists. When the
    user asks for a forecast, the forecast is the exact match, and an observed value is at most a
    near match.

  The query or the approved plan can name another part, such as who states a forecast. An
  institution's forecast and the consensus forecast are then two requested facts. When no one is
  named, the values of different sources are values for the same requested fact. Where the query
  or the approved plan says to look for a value is not a part. It tells research where to look
  first.
- **Exact match**: a value with the same indicator, unit, scope, geography, period and scenario as
  the requested fact, and with the definition or basis that the query or the approved plan names.
  A unit, a scenario, a definition or a basis that they do not name matches any value. A part that
  the source does not state also matches. Exception: when they ask for no forecast, a forecast for
  a period that has ended is a near match. Exception for the unit: when no source of one kind gives
  the requested fact in the named unit, a value of that kind that differs only in its unit is an
  exact match.
- **Near match**: a value with the same indicator as the requested fact and one or more other
  parts that differ, or with a definition or basis other than the one named. A part that the source
  does not state does not alone make a near match, and the report says which part the source does
  not state.
- **Value for another indicator**: a value with a different indicator. It is neither an exact match
  nor a near match, and it is not a value for the requested fact.
- **Matching series**: a dataset series whose dimensions match a requested fact, as the term "Exact
  match" says, and that has a value for the requested period. Its value for a period that has
  ended can be a forecast, and the term "Scenario" decides whether that value is an exact match or
  a near match, and when the report gives it. Each requested period is its own
  requested fact, so a series can be a matching series for some periods and a near-match series for
  others. For an indicator that a query about an effect, a cause or a relation names, a matching
  series has the geography and the period that the query or the approved plan names.
- **Near-match series**: a dataset series of the same indicator as a requested fact that is not a
  matching series, because a dimension differs or it has no value for the requested period. A
  series of another indicator is not a near-match series.
- **Value**: a figure, or a finding in words, that a source gives.
- **Kind of source**: publications or datasets.
- **Values for the same requested fact**: two values that match the same requested fact and agree
  with each other on all their parts, including a definition or basis that the query or the
  approved plan names.
- **Stated date**: the date when the source gave the value. For a publication, it is the
  publication date in the document metadata, and an edition name, such as an issue number, is not
  a stated date. For a dataset value, it is the date of the dataset's last update.
- **Described period**: the period that the value is about. A GDP forecast for 2027 that a source
  gave in 2025 has the stated date 2025 and the described period 2027.
- **Earlier value**: a value for the same requested fact that a current value supersedes. A value
  that a publication quotes as its own earlier value is an earlier value too.
- **Value for another period**: a value with the same indicator, scope, geography and scenario as
  the requested fact but for a different period. It is not a value for the requested fact.
- **Asks how a value was revised**: the query or the approved plan asks how the value for one
  period changed from one stated date to another. A query about a trend over several periods does
  not ask this. It asks for one requested fact for each period.
- **Methodology**: the information that a source gives about how it got a figure or an analysis,
  such as definitions, basis, coverage, sample, adjustments and calculation method.
- **Qualifying context**: what a source states about how it got a value and under which conditions
  the value holds. It covers what the value covers and excludes, its definition and basis, its
  status and caveats, the assumptions of a forecast or a scenario, and what a scenario stands for.
  Why a value changed, what drives it and what it means for something else are supporting context.
  Qualifying context can be on the page of the value, or in a methodology section, a box, a
  footnote, a note under a table or chart, or an appendix. A methodology that the query or the
  approved plan asks for is a requested fact, not qualifying context.
- **Measured differently**: two values whose sources state a different definition, basis or
  calculation method. A different definition or basis does not make a different indicator.
- **Supersede**: a newer value supersedes an older value for the same requested fact, and the
  report does not give the superseded value unless the query or the approved plan asks how the
  value was revised. Of two publication values, the one with the later stated date supersedes the
  other, with no age threshold. A dataset value and a publication value never supersede each
  other, and neither do two dataset values. For a requested fact that is a figure, a finding in
  words never supersedes an older figure, and a newer figure supersedes an older finding in words.
  Two values with the same stated date never supersede each other. A superseded value can
  supersede a value that is older than it. Supersession applies in the same way between two near
  matches that agree on all their parts, and to supporting context about the same subject.
- **Current value**: a value that no other retrieved value supersedes.
- **Supporting context**: content from the sources that does not answer a requested fact but helps
  the reader read the answer. It stands next to the answer and never replaces it. Research does not
  search for it. The writer can say in one clause how each item bears on the answer, and that
  clause states only what a source states, or a comparison. When an exact match exists, a near
  match can stay only as supporting context. A superseded value, a value of a near-match series, an
  earlier value or a value for another period that nobody asked for, content about a different
  topic, an account of the search, and a cause of a difference that no source states are never
  supporting context.
- **Account of the search**: a statement about how research searched, such as which sources it
  checked, or that one publication does not give a requested fact that another publication gives.
  A statement that the rule "When to say that evidence is missing" or the rule "Nearest matches when
  no exact match exists" requires is not an account of the search. Neither is the statement in the
  Overview that names the question and the kinds of source that research covered.
- **Reasonable attempt**: two or more searches for the evidence that differ in wording or in
  filters, such as a metadata filter, and that find no evidence. For context that a retrieved page
  refers to, a reasonable attempt is to read the page that it refers to.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent and research review SHALL each carry all
  twenty-three definitions above, and the system prompts of the report writer, the blind review and
  the grounded review SHALL each carry the first twenty-two, without "Reasonable attempt"

#### Scenario: A failed tool is left to research review's own prompt

- **WHEN** research review's system prompt is rendered
- **THEN** the term "Reasonable attempt" SHALL carry no clause about a failed tool, and research
  review's own prompt SHALL say that the research agent has already retried a failed tool as far
  as it is allowed, so the tool call is not planned again

### Requirement: Rule 10 — missing evidence is stated only for what the user asked for

The rule SHALL be named "When to say that evidence is missing", and its parts SHALL tell each step
the following.

- **Research agent:** makes a reasonable attempt to find each item of evidence that a rule asks
  for, qualifying context and dates included. When the attempt finds nothing, it continues without
  that item.
- **Research review:** a gap for an item of evidence stays open until the findings show a
  reasonable attempt to find that item. After that attempt the item is missing, and a missing item
  is not a gap.
- **Report writer:**
  - says that evidence is missing when no retrieved source gives an item that the user asked for
    in the query or in the approved plan, and names that item;
  - when the query or the approved plan asks for a figure that needs the missing item, such as a
    change over time, says that the report cannot give that figure;
  - does not say that other evidence is missing, and does not say that a stated date is missing;
  - when the datasets give a value for a requested fact and the publications give none, says that
    the publications give no value for it, but only when the findings show two or more searches in
    the publications that found no value;
  - never names the datasets as sources that do not give a requested fact, a figure or a finding
    in words. A statement about all the sources together is allowed. A statement of what a dataset
    gives for each part that differs from a requested fact, with the dataset cited, is the
    exception, and rule 9 decides when to give it;
  - when one source gives a requested fact, does not say that another source of the same kind does
    not give it.
- **Report review:** when the draft says that the sources do not give an item, that statement
  satisfies every check that asks for the item. A statement that names the datasets as sources that
  do not give a requested fact is a violation, and a statement about all the sources together is
  not. A statement of what a dataset gives for each part that differs, with the dataset cited, is
  the exception.

#### Scenario: Missing qualifying context stops being a gap

- **WHEN** the findings show two differently worded searches for the assumptions of a forecast,
  neither of which found them
- **THEN** research review SHALL NOT plan a further search for them

#### Scenario: The publications give no value

- **WHEN** a data query of IMF:WEO gives the 2025 value of a requested fact, and the findings show
  two searches in the publications that found no value for it
- **THEN** the report SHALL say that the publications give no value for 2025

#### Scenario: A draft names the datasets as lacking a value

- **WHEN** a draft says "the datasets do not give the 2025 value"
- **THEN** report review SHALL report a violation, and SHALL NOT report one for "No source gives
  the 2025 value"

#### Scenario: A statement that an item is missing satisfies the check

- **WHEN** a draft says that the sources do not state which definition a value uses
- **THEN** report review SHALL NOT report the missing definition as a violation

### Requirement: Rule 3 — the latest value is searched for in each kind of source

The rule SHALL be named "The latest value in each kind of source", and its parts SHALL tell each
step the following.

- **Research agent:** for each requested fact, searches each kind of source the channel has for
  the value with the latest stated date. For a requested fact that is a finding in words, it
  searches only the publications, because a dataset series never gives a finding in words. For a
  query about an effect, a cause or a relation, it searches the publications for that effect, cause
  or relation, and the datasets for the series of each indicator that the query names. For a
  requested fact that is a figure, it searches each kind of source for the latest figure and for
  the latest value, which can be a finding in words. A finding in words that is newer than the
  latest figure does not end the search for the latest figure. A dataset's entry in the data
  sources is its latest release, so a dataset value needs no check for a later release. When the
  query or the approved plan names a source, the agent starts with it and then searches the other
  sources, unless the user explicitly limits research to the named sources.
- **Research review:** where the channel has publications, a requested fact without a search of
  the publications for its latest value is a gap, also when a dataset gives a value. For a
  requested fact that is a figure, a missing search for the latest figure is a gap, also when
  research found a newer finding in words. A dataset value needs no check for a later release. A
  source that the query or the approved plan names does not close these gaps, unless the user
  explicitly limits research to the named sources.
- **Report writer:** gives the current exact matches for each requested fact. For a requested fact
  that is a figure, when a finding in words is newer than the latest figure, it gives both the
  latest figure and the newer finding in words.

#### Scenario: A later edition supersedes an earlier one

- **WHEN** an edition of a periodic publication of 15 May 2025 and an edition of 20 November 2025
  each give a 2026 GDP growth forecast for the same requested fact
- **THEN** the report SHALL give the forecast of 20 November 2025, and SHALL NOT give the forecast
  of 15 May 2025 unless the query asks how the forecast was revised

#### Scenario: A newer finding in words does not replace the latest figure

- **WHEN** one edition of a publication gives a 2026 GDP growth forecast of 3.2%, and a later
  edition says only that the forecast was revised up
- **THEN** the report SHALL give both the 3.2% and the later edition's statement

#### Scenario: A dataset value is not rechecked

- **WHEN** the findings hold a data query's value and the data sources show the dataset's last
  update
- **THEN** research review SHALL NOT plan a check for a later release of that dataset

#### Scenario: A dataset value does not close the requested fact

- **WHEN** the plan names only datasets, a data query gives the value of a requested fact, and the
  findings show no search of the publications for that fact
- **THEN** research review SHALL report a gap asking for a search of the publications for the
  fact's latest value

#### Scenario: A channel without publications

- **WHEN** a channel's data sources include datasets and no publications, and a data query gives
  the value of a requested fact
- **THEN** research review SHALL NOT report a missing search of the publications as a gap

#### Scenario: The user limits research to a named source

- **WHEN** the query says "use only the World Economic Outlook"
- **THEN** research review SHALL NOT report a missing search of the other sources as a gap

### Requirement: Rule 5 — other periods and earlier values are given only when asked for

The rule SHALL be named "Other periods and earlier values only when asked", and its parts SHALL
tell each step the following.

- **Research agent:** gets each value that the query or the approved plan asks for. When the query
  or the approved plan asks how a value was revised, it gets each earlier value in the date range
  that it gives. It does not get an earlier value, or a value for another period, that the query or
  the approved plan does not ask for. This limit does not apply to a near match that rule 9
  requires or allows.
- **Research review:** a value that the query or the approved plan asks for, and that is not in the
  findings, is a gap until research makes a reasonable attempt. An earlier value, or a value for
  another period, that the query or the approved plan does not ask for is never a gap.
- **Report writer:** gives each value that the query or the approved plan asks for. For a question
  about the current forecast, it gives the current forecasts and no earlier forecast. For a
  question about how a forecast was revised, it gives each earlier value with its stated date. It
  does not give an earlier value, or a value for another period, that nobody asked for, except a
  near match that rule 9 requires or allows.

#### Scenario: The current forecast

- **WHEN** the question asks for the current 2026 forecast of an indicator, and an earlier edition
  of the publication gave another value
- **THEN** the report SHALL give the current forecasts and SHALL NOT give the earlier edition's
  value

#### Scenario: How a forecast was revised

- **WHEN** the question asks how the 2026 GDP growth forecast was revised during 2025, and the
  research found four editions that give it
- **THEN** the report SHALL give the value of every edition, each with its stated date and its
  citation

#### Scenario: A trend is not a revision

- **WHEN** the question asks how the euro-area unemployment rate changed from 2020 to 2025
- **THEN** each year SHALL be a requested fact of its own, and research review SHALL NOT report an
  earlier edition's value for any of those years as a gap

#### Scenario: A one-off event

- **WHEN** the question asks for the losses of one past event
- **THEN** research review SHALL NOT treat a missing value for a previous period as a gap

### Requirement: Rule 4 — the datasets are searched through their structures

The rule SHALL be named "Searching the datasets". It SHALL apply to each requested fact that is a
figure, and to each indicator that a query about an effect, a cause or a relation names. Its parts
SHALL tell each step the following.

- **Research agent:**
  - finds which dataset series match each requested fact, starting from the dataset structures in
    the data-source descriptions;
  - makes no availability query for a series when the structures show that a code it needs is
    missing, and calls no dataset tool for a requested fact when the data-source descriptions show
    that no dataset can hold its indicator;
  - otherwise checks with an availability query whether the series exists, because a structure
    lists the codes of each dimension and not which combinations of codes have a series;
  - never uses a data query to find a series, because a broad data query returns the data points
    of every series it finds;
  - queries the matching series for the requested period, and when several matching series differ
    only in parts that the query and the approved plan do not name, queries only the most
    appropriate ones;
  - queries the dataset also when a publication gives a value, and also when the query or the
    approved plan names another source, unless the user explicitly limits research to the sources
    that they name;
  - when no dataset has a matching series, checks with availability queries what each dataset that
    has the indicator gives for each part that differs, and never queries the data of a near-match
    series.
- **Research review:** unless the user explicitly limits research to other sources, each of these
  is a gap:
  - a requested figure in a dataset that can hold its indicator, where the structures do not show
    that a needed code is missing and research made no availability query for its series;
  - a requested fact with a matching series, where research queried no matching series for the
    requested period;
  - a requested fact with no matching series, where research did not check with availability
    queries what a dataset that has the indicator gives for each part that differs.

  The same applies to each indicator of a query about an effect, a cause or a relation. Research
  review never asks for a data query of a near-match series.

The rule sets no report-writer part. How the report gives a dataset value beside a publication
value is specified in rule 2, and how it gives what a near-match series offers in rule 9.

#### Scenario: A code the structure shows is missing

- **WHEN** a dataset structure lists every code of its geography dimension, and the requested
  country is not among them
- **THEN** the research agent's prompt SHALL tell it to make no availability query for that
  country's series in that dataset

#### Scenario: A named publication does not replace the dataset query

- **WHEN** the query asks for the 2026 GDP growth forecast "according to the World Economic
  Outlook", IMF:WEO has a matching series, and research made no data query of it
- **THEN** research review SHALL report a gap asking for a query of that series

#### Scenario: No matching series

- **WHEN** the requested fact is the unemployment rate for all ages, and a dataset gives that rate
  only for each age group
- **THEN** research SHALL check with availability queries what the dataset gives, and research
  review SHALL NOT ask for a data query of an age-group series

### Requirement: Rule 7 — the qualifying context of each value is retrieved

Where a client documents methodology differs by client, so a channel's client rules say it. The
rule SHALL be named "Finding the qualifying context of each value", and its parts SHALL tell each
step the following.

- **Research agent:** for each value that the report can use, the values of supporting context
  included, gets its qualifying context from the sources. Without it, the agent cannot know whether
  two values are for the same requested fact, or whether they are measured differently. When a
  retrieved page refers to qualifying context, such as a methodology section or an appendix, the
  agent reads that context.
- **Research review:** qualifying context that a retrieved page refers to, and that research did
  not read, is a gap. Qualifying context that no source gives is not a gap.

The rule sets no report-writer part. Giving the qualifying context next to its value is specified
in **faithful-relay**, the rule "Qualifying context next to its value", and giving the qualifying
context of two values that are measured differently in rule 2.

#### Scenario: A referred-to appendix is not read

- **WHEN** a retrieved page gives a forecast and refers to an appendix for its assumptions, and the
  findings show no read of that appendix
- **THEN** research review SHALL report a gap asking to read the appendix

#### Scenario: Qualifying context that no source gives

- **WHEN** no retrieved page states or refers to the assumptions of a forecast
- **THEN** research review SHALL NOT report the missing assumptions as a gap

### Requirement: Rule 2 — every current value is given with its own citation

The rule SHALL be named "Every current value, with its own source", and its parts SHALL tell each
step the following.

- **Research agent:** searches each kind of source as rules 3 and 4 say. After that it does not
  search for more sources that give the same requested fact. It does not search for the cause of a
  difference between values, unless the query or the approved plan asks for it.
- **Research review:** a difference between values is not a gap. A missing cause of a difference is
  not a gap, unless the query or the approved plan asks for the cause. Research review never plans
  a search for more sources that can disagree, because such a search has no end.
- **Report writer:**
  - gives all current values for a requested fact, from different sources and disagreeing ones
    included;
  - cites each value and does not name its source in the text, because the citation identifies the
    source. When one sentence or phrase gives values from two or more sources, it names the source
    of each value. The title of a table of one source names that source;
  - when two values are measured differently, gives the qualifying context of each value next to
    it;
  - gives in one table the values of one source only, unless the query or the approved plan
    explicitly asks to present the answer as a table. In such a table it makes clear which source
    gives each value, preferably by a passage right before or right after the table that cites
    each source, and otherwise by a citation in each cell;
  - gives a cause for a difference only when a source says that this cause explains the difference
    between these values. It does not write that the sources do not explain the difference, unless
    the query or the approved plan asks for the cause;
  - never averages or merges values, and never gives a range that includes them;
  - under this policy, omits a value only in four cases: the value is superseded and the query or
    the approved plan does not ask how it was revised; the value is a near match, an exact match
    exists, and the value is not supporting context; the value is not for a requested fact and is
    neither a near match that rule 9 requires or allows nor supporting context; or the query or the
    approved plan asks to omit it. Other policies can also remove content;
  - gives each value it keeps with its own citation, also when two values are the same figure, and
    never puts two or more citations on one figure. A value in a table that a passage next to the
    table attributes to its source, and a value in a table of one source that cites that source in
    its title, are the exceptions.
- **Report review:** for each pair of values that the draft gives for the same requested fact, each
  value has its own citation, with the same two table exceptions. The draft does not average the
  two values, and does not give a range that includes them. One figure with two or more citations
  is a violation. Report review does not ask for a cause of the difference, unless the query or the
  approved plan asks for it. A figure computed from values for different requested facts, such as
  the difference between two growth rates, merges no values and is outside this check; report
  review's "No calculation by research or the report" check covers it (see
  **report-composition**, "Reports contain no calculations").

#### Scenario: A dataset value and a newer publication value

- **WHEN** IMF:WEO, last updated in October 2025, gives a 2026 GDP growth forecast of 3.4%, and a
  publication of 20 November 2025 gives 3.2% for the same requested fact
- **THEN** the report SHALL give both values, each with its own citation, SHALL NOT drop either as
  superseded, and SHALL NOT say why they differ unless a source says what explains the difference

#### Scenario: A dataset and a publication give the same figure

- **WHEN** a data query and a publication give the same value for the same requested fact
- **THEN** the report SHALL give the value from each source with its own citation, and SHALL NOT
  put two citations on one figure

#### Scenario: Differing values merged into a range

- **WHEN** a draft states "growth is forecast at 3.2% to 3.4% in 2026" and cites one source for
  each end of the range
- **THEN** report review SHALL report a violation asking for each value on its own with its own
  citation, and SHALL NOT ask for the reason for the difference

#### Scenario: One figure with two citations

- **WHEN** a draft gives "growth of 3.2% in 2026" with two citations on the one figure
- **THEN** report review SHALL report a violation

#### Scenario: A difference between two indicators is not a merged value

- **WHEN** a draft gives a column of differences between export growth and GDP growth, each
  computed from two cited values of different indicators
- **THEN** report review SHALL NOT report the column under this rule as a range or an average of
  differing values, and SHALL report it under its "No calculation by research or the report" check
  as figures computed from other figures

#### Scenario: Research review does not start an open-ended search

- **WHEN** the findings hold one value for a requested fact and no other source was found
- **THEN** research review SHALL NOT plan a search for further sources that might disagree

#### Scenario: Values of two sources are not combined in one table

- **WHEN** a dataset and a publication each give the 2025 unemployment rate, and the query does not
  ask for a table
- **THEN** the report SHALL NOT put the two values in one table

### Requirement: Rule 8 — every value carries its described period

The rule SHALL be named "Stated date and described period", and its parts SHALL tell each step the
following.

- **Research agent:** gets the stated date and the described period of each value that the report
  can use, the values of supporting context included, from the tool results. It gets the stated
  date of a publication from the document metadata that a tool gives, and never from the page text,
  because the page text can carry an old template date.
- **Research review:** a value that the report can use, without its stated date, is a gap until
  research gets the date. A value that the report can use, without its described period, is a gap
  until research makes a reasonable attempt.
- **Report writer:**
  - gives the described period of each value;
  - does not write the stated date in the text, because the citation of each source shows it,
    unless the answer needs it, such as when the query or the approved plan asks how a value was
    revised. The title of a table of one source may give the stated date of that source;
  - when it writes a stated date in the text, takes it only from the metadata of the source: the
    publication date of a publication in the findings, or the last update of a dataset in the
    findings or the data sources. It never takes a date from the page text or a page image, and
    never infers one.
- **Report review:** a value without its described period is a violation. Report review never asks
  for the stated date of a value, because its citation shows it, and a stated date in the title of
  a table of one source is not a violation. A year column or a row label in a table gives the
  described period of each value in it, so report review does not ask to mark such values as
  historical or actual.

#### Scenario: A forecast cited without a stated date in the text

- **WHEN** a draft says "GDP is forecast to grow by 3.2% in 2026" with a citation and no stated date
- **THEN** report review SHALL NOT report a violation

#### Scenario: A value without its described period

- **WHEN** a draft says "growth is forecast at 3.2%" with a citation and no period
- **THEN** report review SHALL report a violation asking for the described period

#### Scenario: A written stated date comes from the metadata

- **WHEN** the query asks how a forecast was revised, and a publication's page text carries a date
  that differs from its publication date of 20 November 2025 in the document metadata
- **THEN** the report SHALL take that publication's stated date from the publication date in the
  metadata, although the page text is also in the findings

### Requirement: Rule 9 — only the nearest matches are given when no exact match exists

The rule SHALL be named "Nearest matches when no exact match exists", and its parts SHALL tell each
step the following.

- **Research agent:** when it finds no exact match for a requested fact, it searches the same
  sources for the nearest matches. For each part that can differ, the nearest match is:
  - for a period, the nearest periods before and after it;
  - for a geography, the smallest region or group of countries that contains it, then a wider
    region, then the world, stopping at the first geography that gives a value;
  - for a group of countries that no source aggregates, a few key member countries;
  - for a scope, the smallest scope that contains it;
  - for a frequency that the query or the approved plan names, the other frequencies that the
    sources give;
  - for a scenario, or for a definition or basis, the other values that the sources give.

  It searches the nearest periods in the same geography before it searches a wider geography, and
  it searches for no other near matches. For a near-match series of a dataset, the list does not
  apply: the agent checks with availability queries what the dataset gives for each part that
  differs, and never queries the data of a near-match series.
- **Research review:** a requested fact without an exact match is a gap until research has searched
  its nearest periods in the same geography and the next wider geography. Research review asks only
  for the nearest matches, which are few, so this search has an end. For the datasets, availability queries that show what a
  dataset gives for each part that differs close this gap. Research review never asks for a data
  query of a near-match series.
- **Report writer:**
  - when the findings hold no exact match for a requested fact, says that the sources give no exact
    match, and then gives only its nearest matches: the nearest periods, the smallest geography
    that gives a value, a few key members of a group that no source aggregates, the smallest scope
    that contains the requested scope, the values for other frequencies when a frequency is named,
    and the values for other scenarios, definitions or bases;
  - treats a near match that differs in fewer parts as nearer, and a near match for a different
    period as nearer than one for a wider geography;
  - gives the other near matches in the findings only when none of these nearest matches exists;
  - says how each near match differs from the requested fact;
  - gives no value of a near-match series of a dataset, and instead says what the dataset gives for
    each part that differs, with the dataset cited;
  - when an exact match exists for a requested fact, gives no near match for it, also when the near
    match agrees with the exact match, unless the near match is supporting context (rule 6).
- **Report review:**
  - a near match without a statement of how it differs from the requested fact is a violation;
  - a near match that the draft gives as an answer next to an exact match for the same requested
    fact is a violation, and a near match in Additional context is supporting context, not a
    violation;
  - a value that the draft gives for a requested fact from a dataset series that the draft says
    differs from that fact is a violation. A value of the same series for another requested period
    that the series covers is not a violation, and neither is a named series that the draft
    describes and cites without giving a value from it. A series that differs only in its unit,
    with the unit stated, and a forecast for a period that has ended, labelled as a forecast, are
    not violations either.

#### Scenario: Nearer periods before a wider geography

- **WHEN** the question asks for a country's figure for 2025, no source gives it, and the findings
  show no search for that country's figures for 2024 or 2026
- **THEN** research review SHALL report a gap asking for those periods in the same country, and
  the research agent SHALL search them before the region that contains the country

#### Scenario: Only a narrower geography is available

- **WHEN** the question asks for a figure for a region, the findings hold no nearest match for it,
  and the research found the figure only for one country of that region
- **THEN** the report SHALL say that the sources give no exact match, MAY give the country figure,
  and SHALL say that it covers only that country

#### Scenario: A near-match series is described, not quoted

- **WHEN** the requested fact is the unemployment rate for all ages, and a dataset gives the rate
  only for each age group
- **THEN** the report SHALL say that the dataset gives the rate for each age group but not for all
  ages, SHALL cite the dataset, and SHALL NOT give a value of an age-group series

#### Scenario: A near match beside an exact match

- **WHEN** a draft gives the euro-area unemployment rate for 2025 as the answer, and next to it, as
  a second answer, the rate for Germany
- **THEN** report review SHALL report a violation, and SHALL NOT report one when the rate for
  Germany appears in Additional context

### Requirement: Source selection is verified by evals

The effect of these rules on research and reports depends on model behavior, which unit tests
cannot establish. Unit tests SHALL establish what each step's prompt carries. The behavior SHALL
be checked by running questions on a local stack, including at least one question that asks how a
forecast was revised, and by the Deep Research eval's test cases. Their ground truth follows these
rules.

#### Scenario: A question about how a forecast was revised

- **WHEN** a local stack is asked how a periodic forecast was revised over a given date range
- **THEN** the report SHALL give the value of each edition in that range, each with its citation
  and its stated date, and each stated date SHALL come from the source's metadata

## ADDED Requirements

### Requirement: Rule 1 — every requested fact is answered on its own

The rule SHALL be named "Every requested fact, each on its own", and its parts SHALL tell each step
the following.

- **Research agent:** finds and searches for each requested fact that the query and the approved
  plan ask for. Two requested facts are different when they differ in any part. The other rules
  apply to each requested fact separately, so each requested fact has its own latest values, which
  can come from sources with different stated dates.
- **Research review:** a requested fact that research did not search for is a gap. A value for one
  requested fact never supersedes a value for another requested fact, so it does not close the gap
  of another.
- **Report writer:** answers each requested fact that the query and the approved plan ask for. The
  later plans of research review are not requested facts, because they are the retrieval steps
  that research took. The part of a plan item that says where or how to search is not a requested
  fact either: the values that the search found answer the plan item. A value for one requested
  fact never supersedes a value for another. When research found no value for a requested fact,
  the writer follows rule 10.

#### Scenario: Two forecasters give two requested facts

- **WHEN** a query compares the IMF forecast of euro-area GDP growth for 2026 with the consensus
  forecast
- **THEN** the research agent SHALL search for the latest value of each forecast, and the report
  SHALL give both, also when they have different stated dates

#### Scenario: A search instruction in the plan is not a requested fact

- **WHEN** a plan item says "check the datasets for the 2025 unemployment rate of the euro area"
- **THEN** the report SHALL answer the 2025 unemployment rate of the euro area with the values that
  research found, and SHALL NOT treat the instruction to check the datasets as a fact to answer

### Requirement: Rule 6 — supporting context is included, and requested omissions are honoured

The rule SHALL be named "Supporting context and omitted content", and its parts SHALL tell each
step the following.

- **Research agent:** searches for the requested facts, and does no search only for supporting
  context. The stated date, the described period and the qualifying context of a value in the
  findings are exceptions, which rules 7 and 8 require. The dataset series of each indicator that
  a query about an effect, a cause or a relation names are an exception too, which rule 4 requires.
- **Research review:** missing supporting context is never a gap. The stated date, the described
  period and the qualifying context of a value of supporting context are not supporting context,
  and rules 7 and 8 decide whether they are a gap. The dataset series of each indicator that a
  query about an effect, a cause or a relation names are not supporting context, and rule 4 decides
  whether they are a gap.
- **Report writer:** includes supporting context, but includes an item only when it can say in one
  clause how the item bears on the answer, and that clause states only what a source states, or a
  comparison. It omits the content that the term "Supporting context" excludes. When the query or
  the approved plan asks to omit some content, it omits that content, keeps what another rule
  requires next to a value, such as its described period, and does not say that it omitted part of
  the request.
- **Report review:** an account of the search, as the term defines it, is a violation. Content that
  the query or the approved plan asks to omit is a violation, unless another rule requires it next
  to a value.

#### Scenario: An account of the search

- **WHEN** a draft says "research checked the datasets and three publications"
- **THEN** report review SHALL report a violation

#### Scenario: A requested omission

- **WHEN** the query asks to leave out forecasts
- **THEN** the report SHALL give no forecast, SHALL keep the described period of each value it
  gives, and SHALL NOT say that it left out the forecasts

#### Scenario: Missing supporting context is not a gap

- **WHEN** the findings answer every requested fact, and no retrieved page gives the drivers of the
  values
- **THEN** research review SHALL NOT report the missing drivers as a gap
