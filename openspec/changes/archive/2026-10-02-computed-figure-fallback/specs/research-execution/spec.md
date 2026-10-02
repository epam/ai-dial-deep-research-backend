## MODIFIED Requirements

### Requirement: Research looks for a stated figure rather than planning to compute one

Nobody in Deep Research calculates, not even the report writer (see **report-composition**,
"Reports contain no calculations"). A calculation is arithmetic or modelling that produces a number
no source gives: a growth rate derived from two levels, a difference or a gap in percentage points,
a ratio, a multiple, a share, a sum, an average, an elasticity or a regression estimate.

This rule has the highest priority of all the rules: no client rule, section description,
research question or plan overrides it, and each step's prompt SHALL say so.

- **Research agent.** Its prompt SHALL say that nobody calculates, not even the report writer.
  When the question or the plan asks for a figure that only a calculation would give, the research
  agent SHALL look for a source that states the figure itself and, only when no source states it,
  SHALL retrieve the figures it would be computed from.
- **Research review.** It SHALL never ask for a calculation. A figure that only a calculation would
  give SHALL count as covered by a source that states it. When no source states it, the figure SHALL
  count as covered once the findings show a reasonable attempt to find one (the term the
  source-selection rules define), and hold the figures it would be computed from.

#### Scenario: The question asks for an elasticity no source states

- **WHEN** the plan asks for the elasticity of import growth to GDP growth, the findings show two
  differently worded searches that found no source stating it, and they hold both growth series for
  the same years
- **THEN** research review SHALL treat that plan item as covered, and SHALL NOT return a next step
  asking to compute the elasticity

#### Scenario: Inputs missing

- **WHEN** the plan asks for a share of a total, no source states the share, and the findings hold
  the part but not the total
- **THEN** research review SHALL return a next step asking to retrieve the total, and SHALL NOT ask
  for the share to be computed

#### Scenario: A source states the figure

- **WHEN** the plan asks for the elasticity of import growth to GDP growth and a publication read in
  full states it
- **THEN** research review SHALL treat that plan item as covered without the two growth series, and
  SHALL NOT return a next step asking to retrieve them for a calculation
