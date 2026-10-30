## Why

When the user asks for "the last N years", the preparation agent resolves the span to the N
completed years before the current one, so a request for the last 2 years in 2026 is recorded and
planned as 2024–2025 and the research skips 2026, the year the user cares about most. The same
reading is built into the agent's own default: the example for "the last 10 years" reads
2016–2025, a span that ends before today.

## What Changes

- A span of N years counted back from today ends with the current year, which counts as one of
  the N although it is not over: in 2026, "the last 2 years" is 2025–2026 and "the last 10 years"
  is 2017–2026. The preparation agent's prompt says so where it tells the agent to resolve a
  mechanical time normalization itself, and its example for the default span is counted the same
  way. The current year is the one the user most wants to see; the other reading that keeps it,
  the last N completed years plus the current one, would turn "the last 2 years" into three
  calendar years.
- The agent writes the resolved years into the query it records ("over the last 10 years
  (2017–2026)"), so the research phase, whose prompts carry no rule on relative spans, never
  reads the span itself.
- The query check's prompt carries the same rule next to its line on relative spans, so the check
  does not send the span back as a question when the agent has resolved it this way.
- Spans given in months or days ("the last 6 months", "the last 90 days") are unchanged: they run
  to today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `clarification-and-plan-alignment`: a span of years counted back from today ends with the
  current year, for a span the user states and for the default span the agent applies when the
  user declines to choose; both the preparation agent's prompt and the query check's prompt state
  the rule.

## Impact

- Code: the prompts `PREP_AGENT_SYSTEM` and `QUERY_REVIEW_SYSTEM` in
  `src/dial_deep_research/app/preparation/prompts.py`, which take the years of their examples from
  today's date, and the two places that render them (`agent.py` and `tools.py`). No configuration,
  schema or API changes.
- Behaviour: a query that gives "the last N years" is recorded, and planned, with the current year
  as its last year.
- Eval: the preparation eval needs to cover this reading.
