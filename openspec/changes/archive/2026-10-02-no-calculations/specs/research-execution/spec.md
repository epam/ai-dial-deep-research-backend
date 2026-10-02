## ADDED Requirements

### Requirement: Research looks for a stated figure rather than planning to compute one

Nobody in Deep Research calculates, not even the report writer (see **report-composition**,
"Reports contain no calculations"). A calculation is arithmetic or modelling that produces a number
no source gives: a growth rate derived from two levels, a difference or a gap in percentage points,
a ratio, a multiple, a share, a sum, an average, an elasticity or a regression estimate.

This rule has the highest priority of all the rules: no client rule, section description,
research question or plan overrides it, and each step's prompt SHALL say so.

- **Research agent.** Its prompt SHALL say that nobody calculates, not even the report writer.
  When the question or the plan asks for a figure that only a calculation would give, the research
  agent SHALL look for a source that states the figure itself, and SHALL retrieve the figures it
  would be computed from.
- **Research review.** It SHALL never ask for a calculation. A figure that only a calculation would
  give SHALL count as covered once the findings show a reasonable attempt to find a source that
  states it (the term the source-selection rules define), and hold the figures it would be computed
  from.

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

## MODIFIED Requirements

### Requirement: Reviewer independently judges coverage and produces the next plan

The research-review node SHALL be an independent structured LLM call that reads the
original query, all prior iteration plans, and the accumulated research-agent messages
(reasoning and tool results), and SHALL decide whether the findings cover every plan
item. It SHALL emit the plan for the next iteration as an ordered list of steps; an
**empty** list SHALL mean research is complete. Research-review SHALL be prompted to
include only genuinely uncovered work judged against the existing findings, and
SHALL NOT expand scope to manufacture new iterations. What counts as uncovered work is the plan's
items and the gaps that the research-review parts of the quality rules define (see
**source-selection**): a gap such a rule defines, such as a fact with no check for a later edition,
is part of fulfilling the plan and SHALL NOT be treated as new scope. Every text that tells the
model when research is complete SHALL say so: the prompt's task sentence, its list of gaps, its
sentence on returning an empty next plan, its scope paragraph and its "prefer to finish" guidance,
and the output schema's own description and its two field descriptions, which the model receives
with the output schema.
"Prefer to finish" SHALL apply only once both the plan and those rules are substantively covered.
Every next step SHALL be a retrieval the research agent can carry out with its tools; the prompt
SHALL say that a summary, a comparison or a note is the report writer's and is never a next step,
and that nobody calculates, not even the report writer, so a calculation is never a next step
either (see **Research looks for a stated figure rather than planning to compute one**).
Research-review's structured
output SHALL place its reasoning before its next-plan list. When the next plan is
non-empty, the node SHALL record it (appending to the plan list) and inject it into
the message stream as a `HumanMessage` that becomes the next research-agent iteration's
instruction.

#### Scenario: Uncovered plan item drives another iteration

- **WHEN** research-review finds that a plan item is not yet supported by the findings
- **THEN** it SHALL return a non-empty next plan covering that item, the node SHALL inject it as the next research-agent instruction, and the graph SHALL route back to research-agent

#### Scenario: Full coverage completes research

- **WHEN** research-review finds every plan item supported by the findings, and none of the gaps
  the quality rules define is open
- **THEN** it SHALL return an empty next plan and the graph SHALL route to the report node

#### Scenario: A source-selection gap is not new scope

- **WHEN** every plan item has evidence, but a forecast the plan asks about was found in one
  publication and the findings show no check for a later edition
- **THEN** research-review SHALL return a next plan asking for that check, even though the plan
  does not name it
