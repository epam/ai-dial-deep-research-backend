## Why

A dataset series can run past today with forecasts: the World Economic Outlook, for example, gives
forecasts several years ahead. When the user asks for the latest, most recent or current value of
an indicator, the preparation agent plans to retrieve the latest observation of the series, so
research answers with the furthest forecast instead of the latest actual value.

## What Changes

- When the query asks for the latest, most recent or current value of an indicator, the plan item
  asks for its latest actual value, not the last observation of the series, which can be a
  forecast. The plan names no year for it: which period is the latest actual one depends on the
  series, which may end years before today or run past it.
- The query check treats the latest or current value of an indicator as settled, the same way it
  treats the latest publication: it needs no time period and is not sent back to the user as a
  question.
- A query for a forecast, or for a stated period ("in 2023", "last year"), is planned as before.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `clarification-and-plan-alignment`: the plan asks for the latest actual value when the query
  asks for the latest, most recent or current value of an indicator, and the clarity check does
  not ask for a period for such a value.

## Impact

- Code: the prompts `PREP_AGENT_SYSTEM` and `QUERY_REVIEW_SYSTEM` in
  `src/dial_deep_research/app/preparation/prompts.py`. No configuration, schema or API changes.
- Behaviour: a plan for the latest value of an indicator asks for its latest actual value, and a
  query for the current value of an indicator no longer gets a question about the time period.
- Not changed: the research phase's prompts. Research reads "latest actual value" from the plan.
- Eval: the preparation eval needs to cover this behaviour.
