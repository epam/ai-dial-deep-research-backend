## MODIFIED Requirements

### Requirement: The faithful-relay rules are a generic policy of quality rules

The faithful-relay rules SHALL be generic quality rules (see **source-selection**), rendered as a
block of their own in each step's system prompt, under a heading that names faithful relay, after
the source-selection block and before the other generic policies and the client rules. The blind
review's block SHALL present the rules' parts as checks. The grounded review's block SHALL carry
the rules' report-writer parts (see "The grounded review checks the draft against the sources"). The
rules SHALL name no client, dataset, publication or tool. The terms MAY name a search tool and a
retrieval tool as examples, such as `rag_search` and `retrieve_text_chunks`.

The block SHALL open with the definitions of the terms the rules use, under a name distinct from
the source-selection terms, presented as definitions rather than as a rule, and every step, the
grounded review included, SHALL receive them. The terms are the policy's terms, not one of its
rules (see **source-selection**, "A quality rule is one bundle of step instructions"). The
definitions SHALL say that the source-selection terms, such as value, stated date
and described period, apply here too, which is why the faithful-relay block comes after the
source-selection block that defines them.

- **Source**: the result of a research tool call, or the data sources every prompt carries: the
  knowledge base's descriptions, and the list of datasets and their structures. The answer of a
  search tool that summarises pages, such as `rag_search`, is not a source. A model that follows
  none of these rules writes it, and it can state a sum or a characterisation that the pages do
  not state. It only points at where the evidence lives. A page read as text or as an image, and a
  chunk a retrieval tool returns word for word, such as `retrieve_text_chunks`, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say and
  adds nothing to them, such as "both sources expect growth to slow in 2026".
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic that produces a number no source gives: a growth rate derived from
  two levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as
  large", a share, a sum or an average. A comparison is not a calculation. The term SHALL NOT
  exempt a change of unit, scale or notation, or a rounding: the rule "Each figure with its
  source's value, unit and period" forbids both, and a conversion that needs a rate, such as into
  another currency, is a calculation.
- **Inference**: a conclusion no source states: a causal link, a forecast, an extrapolated trend,
  an implication, a recommendation, or a position attributed to an organisation.
- **Forecast**: a value that its source labels as a forecast, a projection or an outlook. A value
  for a period that ends on or after the stated date of its source is also a forecast, unless its
  source labels it as observed. For example, a publication dated 20 November 2025 that says
  exports "reached USD 250 billion in 2025" gives a forecast, because 2025 was not over. The past
  tense does not make the value observed.
- **Statement about the evidence**: a sentence that says what the research covered, as a section's
  description may ask, that the sources do not give some evidence, or that the report does not
  cover a topic. It states no fact from a source, so it needs no citation.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent, research review, the report writer, the blind
  review and the grounded review SHALL each carry the faithful-relay block, opening with the
  definitions above, after the source-selection block

#### Scenario: The blind review reads the rules as checks

- **WHEN** the blind review's system prompt is rendered
- **THEN** its faithful-relay block SHALL introduce the parts below it as checks to judge the draft
  against, and SHALL come before its "Not your job" section

#### Scenario: The forecast term carries a generic example

- **WHEN** the faithful-relay terms are rendered
- **THEN** the forecast term SHALL give as its example a publication dated 20 November 2025 that
  says exports "reached USD 250 billion in 2025", and SHALL define no estimate term

#### Scenario: The calculation term exempts no conversion

- **WHEN** the faithful-relay terms are rendered
- **THEN** the calculation term SHALL NOT say that a fraction written as a percentage, or any other
  change of unit, scale or notation, is allowed

### Requirement: Rule 4 — figures keep their source's value, unit and period

The rule is named "Each figure with its source's value, unit and period". Every figure SHALL keep
its source's value, unit, currency and period, and SHALL say whether it is nominal or real where the
source says so.

The report SHALL write each number as its source writes it: the same digits, the same decimals, the
same unit, currency and scale word. The report SHALL NOT change a figure in any way:

- it SHALL NOT round a figure or add digits to it, and SHALL NOT replace a figure with an
  approximation, such as "about 2%" or "over USD 1 trillion";
- it SHALL NOT convert a figure to another unit, scale or notation, such as a fraction to a
  percentage, millions to billions, a currency symbol to a currency code, or a number with a
  thousands separator to one without;
- it SHALL NOT give a figure a unit that its source does not state for that value.

The report SHALL give the unit, the currency and the scale word that the source states for the
value, also when the source states them only in the series name, such as an indicator named "…,
percent change" or "…, US dollar, billions". It gives the unit as the source states it, except
that "percent" MAY be written as "%". A currency is written as the source writes it. When the source
states no unit for a value, the report SHALL say so.

A data query result gives its values already converted and rounded as the data layer configures
them for the dataset. The report relays these values as the result gives them, and does not convert
or round them again.

This SHALL hold also when the research question, the approved plan or a section's description asks
to round figures, to give a number of decimals, or to convert a unit or a notation. Client rules
keep their precedence (see **source-selection**, "Client rules follow the generic rules in a tagged
block"), so a channel's configuration SHALL NOT carry a client rule that asks the report to round or
convert a figure. A conversion that needs a rate, such as into another currency, also remains a
calculation, which **report-composition**, "Reports contain no calculations", forbids.

A comparison is not a change to a figure. Two sources can give the same value at different
precisions, because a source may round a value for presentation, so a comparison MAY judge two
values at the precision of the less precise one. Both values are still written as their sources
give them.

The preparation agent keeps in the restated query a unit that the user asks a figure in, because a
requested unit decides which source research uses. It leaves an instruction to round out of the
query and the plan, writes a figure that the user asks to convert in the target unit, and tells the
user (see **clarification-and-plan-alignment**, "The plan never asks to convert or round a figure"
and "The agent tells the user which requested operations Deep Research does not perform"). This is
a sentence of the preparation prompt, not a part of the rule, because quality rules have no
preparation step.

- **Report writer:** writes every figure as its source gives it, whatever rounding or conversion
  the research question, the plan or a section's description asks for.
- **Report review:** a figure without its unit, its currency or its scale word is a violation. The
  fix the review asks for is the unit, the currency or the scale word that the source states for
  the value, its series name included, or, where the source states none, a statement in the draft
  that the source states no unit. The writer, who sees the source, makes that choice. The review
  never proposes a unit itself. The number of digits of a
  figure is not a violation. Whether a figure matches its source is not the blind review's to
  judge.
- The rule sets no grounded part. The grounded review judges the draft by the writer part against
  the research transcript (see "The grounded review checks the draft against the sources"), so a
  figure that the draft rounded, converted or gave a unit its source does not state is a violation
  there.

#### Scenario: A data query value is relayed as returned

- **WHEN** a data query returns an unemployment rate of `3.512` with the unit `%`, and a publication
  gives the same rate as 3.5%
- **THEN** the report SHALL give the dataset value as 3.512% and the publication value as 3.5%, and
  SHALL NOT round the dataset value to 3.5%

#### Scenario: A value with many digits keeps them

- **WHEN** a data query returns a growth rate of `2.156555` with the unit `%`, because the dataset's
  configuration sets no rounding
- **THEN** the report SHALL give 2.156555%, and report review SHALL NOT report the figure for its
  number of digits

#### Scenario: A value with no stated unit gets none

- **WHEN** a data query returns `0.031` for a series named "Inflation" and states no unit for
  it
- **THEN** the report SHALL give 0.031 under that series name, SHALL NOT write it as 3.1%, 0.031%
  or "0.031 units", and SHALL say that the source states no unit

#### Scenario: A publication's scale word stays

- **WHEN** one publication gives exports of "USD 1.2 trillion" and another gives "USD 950 billion"
- **THEN** the report SHALL give each figure with its own scale word, and SHALL NOT rewrite either
  as the other's scale

#### Scenario: A requested rounding does not change the figure

- **WHEN** the research question asks for figures rounded to whole percentages, and a source gives
  a growth rate of 2.4%
- **THEN** the report SHALL give 2.4%, and report review SHALL NOT report the decimal

#### Scenario: A requested conversion does not change the figure

- **WHEN** the research question asks for the growth rates as percentages, and a data query returns
  `0.031` with no unit
- **THEN** the report SHALL give 0.031, and SHALL NOT give 3.1%

#### Scenario: A unit stated in the series name is given

- **WHEN** a data query returns `2.4` for an indicator named "Gross domestic product, constant
  prices, percent change", and its unit attribute is empty
- **THEN** the report SHALL give the value as 2.4% or 2.4 percent, SHALL NOT change the number, and
  the blind review SHALL NOT report the figure as one without its unit

#### Scenario: A currency stated in the series name is given as written

- **WHEN** a data query returns `2104.7` for an indicator named "Gross domestic product, current
  prices, US dollar, billions"
- **THEN** the report SHALL give 2104.7 with the currency and the scale the name states, and SHALL
  NOT rewrite the number as "USD 2.1 trillion" or with a thousands separator

#### Scenario: An approximation is a rounding

- **WHEN** a data query returns a growth rate of `2.156555` with the unit `%`, and the draft writes
  "growth of about 2%"
- **THEN** the grounded review SHALL report the figure as one that differs from its source

#### Scenario: A comparison judges the values at the coarser precision

- **WHEN** the question asks to compare a dataset value of `3.512%` with a publication value of 3.5%
  for the same fact
- **THEN** the report SHALL write 3.512% and 3.5% as their sources give them, and MAY state that the
  two values are equal at the precision of the publication

#### Scenario: The blind review asks for the source's unit, never one of its own

- **WHEN** a draft gives a figure without a unit
- **THEN** the blind review SHALL report it, and its finding SHALL ask for the unit that the source
  states, its series name included, or, only when the source states none, for a statement that it
  states none, and SHALL NOT propose a unit

### Requirement: The prompt text agrees with the faithful-relay rules

The text the prompts already carry SHALL NOT contradict the faithful-relay rules:

- **Report writer.** Its citations section SHALL NOT allow a sentence flagged as the writer's own
  synthesis or inference: an uncitable sentence stays only where rule 1, "Facts only from the
  sources", allows it, and the section SHALL refer to rule 1 by its name rather than restate its
  exemptions. Its "never include" list SHALL NOT ask it to say when a statement is its own
  inference. Its rules that outrank the request SHALL include, after "No calculation by research or
  the report" of **report-composition**, the rules that exclude content and the source-selection
  prohibitions, two faithful-relay rules, each named in the list: inferring nothing ("No conclusion
  that no source states"), and keeping every figure as its source gives it, with no rounding and no
  conversion ("Each figure with its source's value, unit and period"). A section's description,
  default or configured, SHALL NOT override "No calculation by research or the report" or these two
  rules: where a description asks for implications, recommendations, a computed figure, a rounding
  or a conversion, the rules win and the rest of the description still applies.
- **Report review.** Its section-content check SHALL accept uncited text only where rule 1's check
  accepts it, referring to that check rather than restating it, and SHALL NOT accept text flagged as
  the report's own inference.
- **Research review.** Its prompt SHALL say that the report writer does summaries and comparisons,
  and that a next step never asks for one; that nobody calculates is owned by
  **research-execution**, "Research looks for a stated figure rather than planning to compute one".
  Its gap for a figure, date or entity seen only in a search summary SHALL cover a finding and a
  characterisation too, and SHALL accept a chunk returned word for word as well as a page read.
- **Research agent.** Its tools guidance SHALL say that the search tool answers with summaries a
  model writes, which can change, distort or invent a value, a sum or a characterisation that no
  page states, so a summary is a pointer and not evidence; that the pages it points at are read,
  and every value and finding is taken from what was read; and that the retrieval tool's chunks,
  which quote the documents word for word, are evidence.

#### Scenario: No step is told it may infer

- **WHEN** the prompts of a research turn are rendered
- **THEN** no prompt SHALL carry text allowing the report's own inference or synthesis, and
  research review's prompt SHALL NOT say that the writer does calculations

#### Scenario: A configured section asking for implications

- **WHEN** a channel configures a section "Implications" whose description asks what the findings
  imply for the next year, and no source states an implication
- **THEN** the writer SHALL say in that section that the sources do not state one, and SHALL NOT
  infer one

#### Scenario: The research agent is told why a summary is not evidence

- **WHEN** the research agent's system prompt is rendered
- **THEN** its tools guidance SHALL say that a search summary can change, distort or invent a
  figure, and that every figure is taken from a page that was read

#### Scenario: The outrank list names the faithful-relay rules

- **WHEN** the writer's system prompt is rendered
- **THEN** its list of rules that outrank the request SHALL name "No conclusion that no source
  states" and "Each figure with its source's value, unit and period", and SHALL NOT say that the
  latter allows any change to a figure

#### Scenario: No prompt allows a rounding or a conversion

- **WHEN** the prompts of a research turn are rendered
- **THEN** no prompt SHALL carry text that allows the report to round a figure or to write it in
  another unit, scale or notation, apart from writing "percent" as "%"
