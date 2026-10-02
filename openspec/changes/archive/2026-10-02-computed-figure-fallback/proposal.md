## Why

Live runs of the "No calculations" rule showed three gaps. The query check treated a request for a
computed figure as unresearchable and asked the user what to report instead, adding a clarification
round. When the user insisted on a calculation, the preparation agent added a "Calculate the
elasticity" step to the plan, which the report then refused to carry out. And the plan, the
research agent and research review asked for a computed figure's inputs even when a source states
the figure itself.

## What Changes

- For a figure that only a calculation would give, the plan item, the research agent and research
  review look for a source that states the figure first, and retrieve the figures it would be
  computed from only when no source states it. Research review counts a stated figure as covering
  the item.
- The preparation agent plans such an item straight away, without asking the user first.
- The query check treats a request for a computed figure as a clear subject and never asks about
  it: neither how the figure should be computed nor what to report instead.
- When the user insists on a calculation, the preparation agent says plainly that research does not
  compute figures and that, where no source states the figure, the report gives the cited figures
  the calculation needs. The plan keeps no calculation step.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `clarification-and-plan-alignment`: the plan item for a computed figure asks for its inputs only
  when no source states it, is planned without asking the user, survives the user's insistence, and
  the query check never asks about such a request.
- `research-execution`: the research agent retrieves a computed figure's inputs only when no source
  states it, and research review counts a stated figure as covering the item.

## Impact

- Code: `PREP_AGENT_SYSTEM` and `QUERY_REVIEW_SYSTEM` in
  `src/dial_deep_research/app/preparation/prompts.py`, and `RESEARCH_AGENT_SYSTEM_PROMPT` and
  `RESEARCH_REVIEW_SYSTEM_PROMPT` in `src/dial_deep_research/app/research/prompts.py`. The report
  writer and report review are unchanged.
- Docs: rule 3 of the quality policy "Faithful relay of the sources", in the internal documentation
  repository.
