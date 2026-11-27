## MODIFIED Requirements

### Requirement: Reports contain no calculations

The report SHALL give every figure as a source states it, and SHALL compute nothing. A calculation
is arithmetic or modelling that produces a number no source gives: a growth rate derived from two
levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as large", a
share, a sum, an average, an elasticity or a regression estimate. A comparison that produces no new
number, such as which value is larger, a rank, or the direction of a change, is not a calculation
and stays allowed. A change of unit, scale or notation that needs no rate, such as a fraction
written as a percentage, and a rounding are not calculations, but they are not allowed either: the
definition SHALL say that the faithful-relay rule "Each figure with its source's value, unit and
period" forbids them (see **faithful-relay**, "Rule 4 — figures keep their source's value, unit and
period"). The definition SHALL NOT list them as allowed. A conversion that needs a rate, such as
into another currency, SHALL stay a calculation. The
writer's rule section and report review's check SHALL be built from this definition in one wording
(`CALCULATION_DEFINITION`), so the two cannot drift apart.

- **Report writer.** Its prompt SHALL carry this rule as a section of its own, headed "No
  calculation by research or the report". Flagging a computed number as the report's own inference
  SHALL NOT make it allowed. Where the question or the plan asks for a figure that only a
  calculation gives and no source states it, the report SHALL give the figures it is computed
  from, each with its citation, and SHALL say that the sources do not give the computed figure.
  Where the question names only a measure, such as an index, and no source states how to compute
  it, the report SHALL say that the sources give neither the figure nor how to compute it, and
  SHALL give none of the figures that it could be computed from.
- **Precedence.** This rule SHALL have the highest priority of all the rules: neither the research
  question, the plan, a section's description nor a client-specific rule SHALL override it, and both
  the writer and report review SHALL be told so in those words. The writer's list of rules that
  outrank the research question and the plan SHALL include this rule. Saying that the sources do not
  give a figure is a statement about the evidence, and SHALL NOT be read as the commentary on a
  declined instruction that **Protected sections and their rules survive any user instruction**
  forbids.
- **Report review.** The blind review's prompt SHALL carry a "No calculation by research or the
  report" check among its numbered checks: a number the draft presents as computed from other
  figures is a violation, even when the draft flags it as its own inference or a section's
  description or a client-specific rule asked for it. A comparison that produces no new number is
  not a violation. A number that carries its own citation, and that the draft does not present as
  computed, is not report review's to judge, because report review cannot see the sources. A
  figure computed from values for different requested facts, such as the difference between two
  growth rates, falls within this check. The blind part of the source-selection rule "Every current
  value, with its own source" SHALL say that its own check does not cover such a figure. The
  grounded review SHALL receive the writer's section in the same wording, so it also finds a
  computed number the draft presents as stated (see **faithful-relay**, "Rule 3 — the grounded
  review judges the "No calculation by research or the report" rule").

#### Scenario: The question asks for an elasticity no source states

- **WHEN** the question asks for the elasticity of import growth to GDP growth, and the findings
  hold both growth series but no source that states the elasticity
- **THEN** the report SHALL present both series with their citations, SHALL say that the sources do
  not give the elasticity, and SHALL NOT give an elasticity or a regression estimate of its own

#### Scenario: The question names an index that no source defines

- **WHEN** the question asks for a trade-openness index for Germany, no source states the index or
  how to compute it, and the findings hold the exports, the imports and the GDP of Germany
- **THEN** the report SHALL say that the sources give neither the index nor how to compute it, and
  SHALL NOT give the exports, the imports or the GDP as the figures the index is computed from

#### Scenario: A gap in percentage points between two cited values

- **WHEN** a draft states that one cited growth rate is 1.2 percentage points above another cited
  growth rate, and no source gives that gap
- **THEN** report review SHALL report a "No calculation by research or the report" violation

#### Scenario: A comparison is not a calculation

- **WHEN** a draft states that one cited growth rate is higher than another, without giving a new
  number
- **THEN** report review SHALL NOT report a "No calculation by research or the report" violation

#### Scenario: The definition allows no rounding and no conversion

- **WHEN** the writer's "No calculation by research or the report" section and the blind review's
  check of the same name are rendered
- **THEN** neither SHALL list a rounding or a change of unit, scale or notation as allowed, both
  SHALL say that the rule "Each figure with its source's value, unit and period" forbids them, and
  both SHALL say that a conversion that needs a rate, such as into another currency, is a
  calculation

#### Scenario: A client rule asks for a computed figure

- **WHEN** a channel's client rule asks the writer to give the year-on-year change of each series,
  and no source states those changes
- **THEN** the report SHALL give the cited values for each year, SHALL NOT compute the changes, and
  report review SHALL report a "No calculation by research or the report" violation for a draft
  that computed them

#### Scenario: A computed figure flagged as inference

- **WHEN** a draft gives the average of three cited yearly values and labels it as its own
  estimate
- **THEN** report review SHALL report a "No calculation by research or the report" violation
