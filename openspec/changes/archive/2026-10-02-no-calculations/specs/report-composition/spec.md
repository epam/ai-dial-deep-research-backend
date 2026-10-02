## ADDED Requirements

### Requirement: Reports contain no calculations

The report SHALL give every figure as a source states it, and SHALL compute nothing. A calculation
is arithmetic or modelling that produces a number no source gives: a growth rate derived from two
levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as large", a
share, a sum, an average, an elasticity or a regression estimate. Three things are not
calculations and stay allowed: a comparison that produces no new number, such as which value is
larger, a rank, or the direction of a change; writing a value in another notation, such as a
fraction as a percentage; and rounding a value given with more digits than a reader can use, such
as 0.0473918265 written as 4.74%. The writer and report review SHALL be given this definition in
one wording, so the two cannot drift apart.

- **Report writer.** Its prompt SHALL carry this rule as a section of its own. Flagging a computed
  number as the report's own inference SHALL NOT make it allowed, although an uncited sentence may
  otherwise be kept when it is flagged that way. Where the question or the plan asks for a figure
  that no source states and only a calculation would give, the report SHALL present the figures it
  would be computed from, each with its citation, and SHALL say that the sources do not give the
  computed figure.
- **Precedence.** This rule SHALL have the highest priority of all the rules: neither the research
  question, the plan, a section's description nor a client-specific rule SHALL override it, and both
  the writer and report review SHALL be told so in those words. The writer's list of rules that
  outrank the research question and the plan SHALL include this rule. Saying that the sources do not
  give a figure is a statement about the evidence, and SHALL NOT be read as the commentary on a
  declined instruction that **Protected sections and their rules survive any user instruction**
  forbids.
- **Report review.** Its prompt SHALL carry a "No calculations" check among its numbered checks: a
  number the draft presents as computed from other figures is a violation, even when the draft flags
  it as its own inference or a section's description or a client-specific rule asked for it. The
  three allowed things above are not violations. A number that carries its own citation, and that
  the draft does not present as computed, is not report review's to judge, because report review
  cannot see the sources. A figure computed from values of different facts, which the
  source-selection check on disagreements leaves out, falls within this check, and that
  source-selection part SHALL say so.

#### Scenario: The question asks for an elasticity no source states

- **WHEN** the question asks for the elasticity of import growth to GDP growth, and the findings
  hold both growth series but no source that states the elasticity
- **THEN** the report SHALL present both series with their citations, SHALL say that the sources do
  not give the elasticity, and SHALL NOT give an elasticity or a regression estimate of its own

#### Scenario: A gap in percentage points between two cited values

- **WHEN** a draft states that one cited growth rate is 1.2 percentage points above another cited
  growth rate, and no source gives that gap
- **THEN** report review SHALL report a "No calculations" violation

#### Scenario: A comparison is not a calculation

- **WHEN** a draft states that one cited growth rate is higher than another, without giving a new
  number
- **THEN** report review SHALL NOT report a "No calculations" violation

#### Scenario: Rounding is not a calculation

- **WHEN** a data query returned 0.0473918265 and the draft gives it as 4.74% with the query's
  citation
- **THEN** report review SHALL NOT report a "No calculations" violation

#### Scenario: A client rule asks for a computed figure

- **WHEN** a channel's client rule asks the writer to give the year-on-year change of each series,
  and no source states those changes
- **THEN** the report SHALL give the cited values for each year, SHALL NOT compute the changes, and
  report review SHALL report a "No calculations" violation for a draft that computed them

#### Scenario: A computed figure flagged as inference

- **WHEN** a draft gives the average of three cited yearly values and labels it as its own
  estimate
- **THEN** report review SHALL report a "No calculations" violation
