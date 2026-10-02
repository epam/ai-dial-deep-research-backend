## MODIFIED Requirements

### Requirement: The plan never asks for a calculation

The plan the preparation agent drafts SHALL NOT ask to calculate, compute, derive, estimate or
model a figure, such as a growth rate from two levels, a difference, a share, a sum, an average, an
elasticity or a regression estimate, because neither research nor the report computes anything (see
**report-composition**, "Reports contain no calculations"). When the query asks for such a figure,
the plan item SHALL ask to look for a source that states the figure itself and, only where none
does, to retrieve the figures it would be computed from. The preparation agent SHALL plan such an
item straight away, without asking the user first, and its prompt SHALL say so, with an example of
such a plan item. A plan item asking research to look for what explains a difference between
sources is not a calculation, and the prompt SHALL say so, since the source-selection rules need
that explanation.

The query itself is unaffected: the preparation agent restates what the user asked for, a request
for a computed figure included, and the plan alone carries how research handles it. The query check
SHALL treat a request for a computed figure as a clear subject, and its prompt SHALL say what
research does with it: look for a source that states the figure and, where none does, retrieve the
figures it would be computed from. The query check SHALL NOT ask about such a request: neither how
the figure should be computed, such as a method, a formula or a regression specification, nor what
to report instead.

The rule SHALL hold when the user insists on a calculation or rejects a plan without one. The
preparation agent SHALL then say plainly that research does not compute figures and that, where no
source states the figure, the report gives the cited figures the calculation needs, and SHALL keep
the plan item that looks for a stated figure. No plan item SHALL calculate or promise a calculated
result.

#### Scenario: The user asks for an elasticity

- **WHEN** the clarified query asks to quantify the elasticity of import growth to GDP growth over
  a period
- **THEN** the recorded plan SHALL ask to look for a stated elasticity and, if no source states
  one, to retrieve the import growth and GDP growth series for that period, and no plan item SHALL ask to calculate, estimate or
  model the elasticity, by regression or otherwise

#### Scenario: The query check does not ask for an estimation method

- **WHEN** the query asks to quantify the elasticity of import growth to GDP growth, and the
  subject, the region and the period are settled
- **THEN** the query check SHALL NOT ask how the elasticity should be estimated, by which formula,
  or with which regression specification, and SHALL NOT ask what to report instead of a calculated
  elasticity

#### Scenario: The user asks for a growth rate

- **WHEN** the query asks for the growth of a value between two years
- **THEN** the plan SHALL ask for a source that states that growth and, if none does, for the
  value in both years, and SHALL NOT ask to compute the growth from the two values

#### Scenario: The user insists on a calculation

- **WHEN** the user rejects a plan that looks for a stated elasticity and answers that they need a
  calculation
- **THEN** the preparation agent SHALL say that research does not compute figures and that the
  report will give the cited figures the calculation needs where no source states it, and no
  recorded plan item SHALL ask to calculate the elasticity or promise a calculated result
