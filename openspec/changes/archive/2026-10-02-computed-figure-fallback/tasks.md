## 1. Prompts

- [x] 1.1 In `QUERY_REVIEW_SYSTEM`, treat a request for a computed figure as a clear subject and never ask about it, neither how to compute it nor what to report instead
- [x] 1.2 In `PREP_AGENT_SYSTEM`, make the inputs conditional on no source stating the figure, plan it without asking the user, and update the example plan item
- [x] 1.3 In `PREP_AGENT_SYSTEM`, hold the rule when the user insists on a calculation: explain the limit plainly, keep no calculation step, and offer the inputs
- [x] 1.4 In `RESEARCH_AGENT_SYSTEM_PROMPT` and `RESEARCH_REVIEW_SYSTEM_PROMPT`, retrieve the inputs only when no source states the figure, and count a stated figure as covering the item

## 2. Tests and verification

- [x] 2.1 Update the prompt tests for the query check and the pushback rule
- [x] 2.2 Run lint and the test suite
- [x] 2.3 Replay a query asking for an elasticity, twice, and a turn insisting on a calculation, against a local server, and check that no clarification is asked and no plan item calculates
- [x] 2.4 Update rule 3 of the "Faithful relay of the sources" policy in the internal documentation repository
