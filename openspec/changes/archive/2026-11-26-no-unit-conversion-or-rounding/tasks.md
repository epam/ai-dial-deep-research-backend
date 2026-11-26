## 1. Report rules

- [x] 1.1 In `faithful_relay.py`, rewrite the writer part of "Each figure with its source's value, unit and period" from the design's prompt text, trimmed to what the rule needs: no rounding or approximation, no unit, scale or notation change, a currency conversion with a rate is a calculation, the unit, currency and scale word the source states (series name included, "percent" as "%"), a sentence when the source states none, the comparison at the coarser precision, and the request override without client rules
- [x] 1.2 In the same rule, rewrite the blind-review part: a missing unit, currency or scale word is a violation, the fix is the source's unit or a "no unit stated" sentence, never a proposed unit, and the number of digits is not judged
- [x] 1.3 In `FAITHFUL_RELAY_TERMS`, replace the exemption sentence of the term "Calculation" with one that sends a change of unit, scale or notation and a rounding to rule 4 and keeps a conversion with a rate as a calculation
- [x] 1.4 In `research/prompts.py`, rewrite the allowed-things sentence of `CALCULATION_DEFINITION` as in the design
- [x] 1.5 In `research/prompts.py`, change the faithful-relay item of "These rules outrank the request" to "keep every figure as its source gives it, with no rounding and no conversion", and add a rounding or a conversion to the paragraph about section descriptions

## 2. Preparation agent

- [x] 2.1 In `PREP_AGENT_SYSTEM`, add the plan rule for conversion and rounding requests after the calculation rules: no plan step, not a detail the plan keeps and not a form, a named unit stays without a notice, the notice for an explicit request
- [x] 2.2 In the same prompt, make the "do not drop a detail" and the form-exception lines refer to that rule where they would otherwise keep a rounding, without restating it
- [x] 2.3 In the same rule, keep a request to round out of the query and the plan, and make the notice name the rounding and the conversion; make "do not drop a detail" name that exception

- [x] 2.4 Replace the reply to an insisted calculation and the round-or-convert notice with one rule for the three unsupported operations, as in the design: an explicit instruction only, what each leaves in the query and the plan, one sentence that names only the requested operations
- [x] 2.5 Make the Stage 1 sentence that keeps the user's formatting requests, and "do not drop a detail", name the exception for these instructions
- [x] 2.6 Return the labelled block from `PLAN_RECORDED`, and make the prompt's presentation lines name the block
- [x] 2.7 Add to the rule on spans that an open end such as "until now" stays as the user wrote it
- [x] 2.8 Add that a named period that has ended, such as a presidency, is written into the query with its years
- [x] 2.9 Write the sentence about an unsupported operation once, after `update_plan` returns; add to `PLAN_RECORDED` that the agent does not write again a sentence that it already wrote in the turn; say in the `update_query` tool's description to leave an instruction to calculate or round out of the query
- [x] 2.10 Write the years of a period named by an event or an era wherever the query or the plan names it: both years for a closed period, the start year for a period that has not ended, no date for an open end that names no event
- [x] 2.11 Say that the plan does not mention the precision of figures
- [x] 2.12 Make a conversion request the figure in the target unit, in the query, in every plan step that looks for the figure and in the `update_query` tool's description, with the note
- [x] 2.13 Give the note only for an explicit instruction to calculate, round or convert; a figure that looks like a calculation, such as a share of GDP or a multi-year average, gets no note
- [x] 2.14 Move the rules for the three operations and the note into one section "Requests to calculate, round or convert": what the note names and says, once after `update_plan` returns, no promise, no question, and `update_plan` again with the same steps when the user insists
- [x] 2.15 Make a plan step name a data source, not a series, an indicator or a value from its description, and write the requested figure in the words of the query; say next to the data sources that their descriptions are examples, used only to choose the sources
- [x] 2.16 Keep every stated detail in the query and in every plan step, except an instruction to calculate or round; a conversion keeps its target unit in every plan step
- [x] 2.17 In `QUERY_REVIEW_SYSTEM`, list the cases in which the query check asks for the time period: no period and no event or era (words such as "outlook" or "overview" name no period), a bare "latest", "recent" or "lately", and an event or era it does not recognize
- [x] 2.18 In Stage 1 of `PREP_AGENT_SYSTEM`, write the restated query as a full question or a full instruction, not as a noun phrase; show the calculation example's query as a full question
- [x] 2.19 Rename the section to "Unsupported operations" and move it after Stage 3; move Stage 2's calculation rule into it; make Stage 1, Stage 2 and the `update_query` tool's description refer to it; state the invariant "also when the user insists" in place of a rule for an insisting user; give the examples in reply order, the note and then the query
- [x] 2.20 In Stage 3, call `approve_plan` only when the message clearly approves the plan and asks for no change to the query or the plan
- [x] 2.21 In `QUERY_REVIEW_SYSTEM`, replace the paragraph on computed figures with three sentences: a figure that needs a calculation and a figure in a unit or currency that the user names are clear subjects; no question on how to calculate or convert; no question on which figure or unit to report instead

## 3. Tests

- [x] 3.1 Update `tests/test_faithful_relay.py`: replace the assertions on "Two changes are allowed" with assertions that the writer part forbids rounding and conversion, gives the series name's unit, and that the blind part does not judge digits
- [x] 3.2 Update `tests/test_no_calculations_prompts.py`: the shared definition no longer allows rounding, sends conversions to rule 4, and keeps a rate conversion as a calculation
- [x] 3.3 Add a test that the preparation prompt carries the conversion and rounding plan rule
- [x] 3.4 Run `make format`, `make lint` and the unit tests from the worktree with `PYTHONPATH=src`
- [x] 3.5 Update the preparation prompt assertions for the three operations, and add a test that `update_plan` returns the labelled block
- [x] 3.6 Update the preparation prompt and query-check assertions for the section "Unsupported operations", the `approve_plan` rule and the query check's three sentences

## 4. Specs

- [x] 4.1 Sync the delta specs into the main specs with the `openspec-sync-specs` skill

## 5. Outside this repository

- [x] 5.1 A channel's configuration carries no client rule that asks to convert or round values
- [x] 5.2 Update the output-quality policies: rule 4, the definition of a calculation, any client rule entry that converts values, the requirement behind rule 4 with the deviation from its original wording, and the data-source limitations note
- [x] 5.3 The eval needs to cover this behaviour

## 6. Validation

- [x] 6.1 Check that final reports give every figure as its source gives it
- [x] 6.2 Check the preparation agent's reply to an explicit rounding request, to a conversion request, to a named unit and to an insisted rounding
- [x] 6.3 Check the preparation agent's behaviour for the three operations and the labelled block, with no regression elsewhere
