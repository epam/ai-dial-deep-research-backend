## Why

The report writer may change a figure in two ways today: it may bring values to one notation, such
as a fraction written as a percentage or a scale word changed, and it may round a value with more
digits than a reader can use. Each change is a place where the model can get a number wrong, such as
a percentage that is off by a factor of a hundred or a rounding done on the wrong digit. The data
query tool of StatGPT now applies the conversion and the rounding itself, from each dataset's
configuration: `fractionToPercent` converts the series stored as fractions of one to percentages and
sets their unit, and `decimalPlaces` rounds the values the model reads (statgpt-backend PRs #799 and
#804). The data layer owns the presentation of the values, so Deep Research has no reason left to
change a figure, and every reason not to.

## What Changes

- The faithful-relay rule "Each figure with its source's value, unit and period" no longer allows any
  change to a figure. The report gives every figure with the digits, decimals, unit, currency, scale
  word and period that its source gives it. The two allowed changes, "One notation" and "Usable
  precision", are removed.
- The report gives no unit that its source does not state for the value, and says so when the
  source states none. A unit, a currency or a scale word that the series name states counts as
  stated, and "percent" may be written as "%". An approximation such as "about 2%" is a rounding.
- A comparison may still judge two values at the precision of the less precise one, because a
  source may round a value for presentation; both values are written as their sources give them.
- No request changes this: not the research question, the approved plan or a section's description
  that asks to round figures, to give a number of decimals, or to convert a unit or a notation.
  Client rules keep their precedence, so a channel's configuration must carry no client rule that
  asks for a conversion or a rounding.
- The blind review no longer reports "a figure with more digits than a reader can use". It still
  reports a figure without its unit, currency or scale word, and the fix it asks for is the unit,
  currency or scale word that the source states, never one the draft makes up.
- The definition of a calculation (`CALCULATION_DEFINITION`) no longer lists a change of notation and
  rounding among the allowed things; it sends them to rule 4. A conversion that needs a rate, such
  as into another currency, stays a calculation. A comparison that produces no new number stays
  allowed.
- The faithful-relay term "Calculation" drops the sentence that exempts a fraction written as a
  percentage.
- The preparation agent plans no calculation, no conversion and no rounding. One prompt section,
  "Unsupported operations", after Stage 3, holds every rule on them, and the other parts of the
  prompt refer to it. It states once that Deep Research never does these operations, also when the
  user insists:
  - An instruction to calculate stays out of the restated query and the plan. The figure stays,
    and the plan looks first for a source that states it.
  - An instruction to round stays out of the query and the plan.
  - An instruction to convert becomes the figure in the target unit, in the query and in every plan
    step that looks for the figure: "Mexico's exports, converted to euros" becomes "Mexico's exports
    in euros". Research already accepts a value in another unit when no source gives the requested
    unit.
  - For each of these explicit instructions, the agent gives the note: one sentence that names only
    the requested operations and says what the report gives instead.
  - A figure that a source can state as its own indicator, such as a multi-year average or a share
    of GDP, is a request for a figure. It needs no note. A plain request gets no note.
- The note appears once in a reply, directly before the labelled block when the reply presents it.
  When the user insists, the agent gives the note again and changes neither the query nor the plan.
  The `update_plan` tool's response tells the agent not to write again a sentence that it already
  wrote in the turn.
- The query check treats a figure that needs a calculation, and a figure in a unit or a currency
  that the user names, as a clear subject. It does not ask how to calculate or convert a figure, or
  which figure or unit to report instead.
- The agent calls `approve_plan` only when the message clearly approves the plan and asks for no
  change to the query or the plan.
- The `update_plan` tool labels the query ("Research query:") and the plan ("Plan:") in the block
  that the agent presents verbatim, so every reply that presents a plan labels the query.
- Every detail that the user stated stays in the query and in every plan step, except an
  instruction to calculate or round. The plan does not mention the precision of figures.
- A plan step names a data source by its name, not a series, an indicator or a value from its
  description, and writes the requested figure in the words of the query. The data-source
  descriptions serve only to choose the sources.
- A period named by an event or an era gets its years in parentheses wherever the query or the plan
  names it: both years for a closed period, the start year for a period that has not ended. An open
  end that names no event, such as "until now", stays as the user wrote it.
- The query check asks for the time period when the query names no period and no event or era.
  Words such as "outlook" or "overview" name no period.
- The `update_query` tool's description refers to the section "Unsupported operations" for a
  request to calculate, round or convert a figure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `faithful-relay`: Rule 4 "Each figure with its source's value, unit and period" allows no change to
  a figure; the term "Calculation" and the writer's list of rules that outrank the request follow.
- `report-composition`: the requirement "Reports contain no calculations" no longer lists a change of
  notation and rounding as allowed.
- `clarification-and-plan-alignment`: the plan asks for no conversion or rounding, and a conversion
  becomes the figure in the target unit; the preparation agent tells the user which requested
  operations Deep Research does not perform; the calculation rule leaves an explicit instruction to
  calculate out of the query; the requirement that the plan keeps every detail makes an exception
  for an instruction to calculate or round; a plan step names a data source, not its series; a
  period named by an event or an era is written with its years; the query check asks for a missing
  time period and asks no question about a calculated or converted figure; `update_plan` returns a
  labelled block; the agent calls `approve_plan` only for a clear approval.

## Impact

- `src/dial_deep_research/app/research/faithful_relay.py`: the term "Calculation" in
  `FAITHFUL_RELAY_TERMS`, and the writer and blind-review parts of the rule "Each figure with its
  source's value, unit and period".
- `src/dial_deep_research/app/research/prompts.py`: `CALCULATION_DEFINITION`, the faithful-relay item
  of "These rules outrank the request" in the report writer's prompt, and the blind review's "No
  calculation by research or the report" check where it names the allowed things.
- `src/dial_deep_research/app/preparation/prompts.py`: in `PREP_AGENT_SYSTEM`, the section
  "Unsupported operations", the Stage 1 rules on formatting requests and on named periods, the
  Stage 2 rules on details and on plan steps, the Stage 3 rule on when to call `approve_plan`, and
  the note on the data-source descriptions; the time-period rules of `QUERY_REVIEW_SYSTEM` and its
  sentences on calculated and converted figures; the labelled block in `PLAN_RECORDED`.
- `src/dial_deep_research/app/preparation/tools.py`: the `update_query` tool's description.
- `tests/test_faithful_relay.py`, `tests/test_no_calculations_prompts.py`: the assertions on the
  removed wording. `tests/test_preparation_tools.py`: the labelled block.
- `openspec/specs/faithful-relay/spec.md`, `openspec/specs/report-composition/spec.md`,
  `openspec/specs/clarification-and-plan-alignment/spec.md`: through the delta specs of this change.
- Every channel: a dataset whose configuration sets no `decimalPlaces` or `fractionToPercent` shows
  its values in the report as the data query tool returns them, with all their digits and in the
  dataset's own notation. The fix for such a dataset is its configuration in StatGPT, not Deep
  Research.
- Outside this repository: a channel's client rules that ask to convert or round values must be
  removed from its application properties, and the output-quality policies must follow this rule.
  The eval needs to cover this behaviour.
- No API, configuration schema or dependency change.
