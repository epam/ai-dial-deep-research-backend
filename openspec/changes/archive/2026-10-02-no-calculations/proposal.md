## Why

The preparation agent writes plan items such as "calculate the elasticity of one growth rate to
another using a regression-based estimate", and the report then contains sums, differences,
percentages and regression estimates that no source states. A computed figure carries a citation to
the figures it was computed from, so the reader cannot tell it from a figure the source gives, and
an arithmetic or modelling error in it goes unnoticed. Deep Research relays what the sources state;
it does not compute.

## What Changes

- The preparation agent's plan never asks to calculate, compute, derive, estimate or model a
  figure. When the query asks for such a figure, the plan item asks to look for a source that
  states it, and to retrieve the figures it would be computed from. The query check never asks the user how a
  figure should be computed, such as a method, a formula or a regression specification.
- The research agent is told that nobody calculates, not even the report writer. When the question
  or the plan asks for a computed figure, it looks for a source that states the figure itself, and
  retrieves the figures it would be computed from.
- Research review never asks for a calculation, and no longer tells the model that a calculation
  is the report writer's. A figure that only a calculation would give counts as covered once the
  findings show a reasonable attempt to find a source that states it, and hold the figures it would
  be computed from.
- The report writer gets a "No calculations" rule: it gives every figure as a source states it,
  computes nothing, and, where a computed figure was asked for, presents the cited figures it would
  be computed from and says that the sources do not give it. Flagging a computed figure as the
  report's own inference does not make it allowed.
- "No calculations" has the highest priority of all the rules: no client rule, section
  description, research question or plan overrides it. The text that introduces a channel's client
  rules says so as the one exception to following the more specific client rule.
- Report review gets a "No calculations" check: a number the draft presents as computed from other
  figures is a violation.
- Three things are not calculations and stay allowed at every step: a comparison that produces no
  new number, writing a value in another notation, such as a fraction as a percentage, and rounding
  a value given with more digits than a reader can use.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `clarification-and-plan-alignment`: the plan the preparation agent drafts never asks for a
  calculation, and the query check never asks how a figure should be computed.
- `research-execution`: the research agent looks for stated figures instead of planning to compute
  them, and research review never asks for a calculation and defines when a computed figure counts
  as covered.
- `source-selection`: the statement that a calculation is the report writer's is removed from the
  research-review item, which now says nobody calculates, and the client-rules block names the rule
  that nobody calculates as the one rule no client rule overrides.
- `report-composition`: the report writer's "No calculations" rule, its place among the rules that
  outrank the request, and report review's matching check.

## Impact

- Code: the prompts in `src/dial_deep_research/app/preparation/prompts.py` (`PREP_AGENT_SYSTEM`,
  `QUERY_REVIEW_SYSTEM`) and `src/dial_deep_research/app/research/prompts.py`
  (`RESEARCH_AGENT_SYSTEM_PROMPT`, `RESEARCH_REVIEW_SYSTEM_PROMPT`, `REPORT_SYSTEM_PROMPT`,
  `REPORT_REVIEW_SYSTEM_PROMPT`, and the glossary check, renumbered from 7 to 8), and the
  report-review part of the source-selection rule on disagreements in
  `src/dial_deep_research/app/research/source_selection.py`. No configuration, schema or API
  changes.
- Behaviour: a report answering a question that asks for a computed figure carries the source
  figures and a statement that the sources do not give the computed one, instead of the computed
  figure.
- Merge: the planned faithful-relay change edits the same research-review sentence and the same
  "These rules outrank the request" paragraph, and carries its own "No calculations" rule. Whichever lands second needs a manual merge.
- Docs: the quality policy "Faithful relay of the sources", rule 3, in the internal documentation
  repository, gains the preparation agent's part.
