## 1. The stage

- [x] 1.1 In `utils/dial_stages.py`, add `format_budget_exhausted_title` and
      `format_budget_exhausted_body` to `DialStageResearchReviewFormatter`, beside the report
      formatter's unreviewed-delivery pair. The title is
      `[RESEARCH REVIEW RESULT] review budget is exhausted - proceeding to report ⚠️` and carries no
      elapsed time, no call having been made; the body gives the iteration with the cap and states
      that the findings go to the report without a coverage review.
- [x] 1.2 Add `ResearchRunner._emit_research_budget_exhausted_stage`, rendering the two through the
      formatter, next to `_emit_unreviewed_delivery_stage`.

## 2. Reporting the skip where it is decided

- [x] 2.1 Give `route_after_research_agent` an emitter parameter beside `max_research_iterations`,
      and call it on the branch that returns `report`, skipping the emission when the cap is one.
- [x] 2.2 Add the cap to that branch's INFO record, so it reads
      `Research iteration budget exhausted: research_iteration=N max_research_iterations=M`.
- [x] 2.3 Thread the emitter through `build_research_graph` beside the two result-stage emitters,
      wired from the runner method of 1.2.

## 3. The failed revision

- [x] 3.1 In `utils/dial_stages.py`, add a formatter for the report step's own outcome, prefixed
      `[REPORT REVISION FAILED]`, with a title naming the draft that was not written and the one delivered
      instead, marked ❌, and a body carrying those two numbers, the failure kind, and the note that
      violations the last review recorded may remain. No draft text.
- [x] 3.2 Add the outcome model and its emitter type in `app/research/nodes.py`, and emit it from the
      report node's `except` branch, which is where the exception kind is known.
- [x] 3.3 Thread the emitter through `build_research_graph` and add the runner method that renders it.

## 3b. The unreviewed delivery moves to its router

- [x] 3b.1 Add the outcome model for a delivery the version budget left unreviewed, and move the
      decision, the draft measurement and the INFO record from `ResearchRunner` into
      `route_after_report`, which gains the report structure and the ceiling.
- [x] 3b.2 Leave the runner only the rendering, and wire the emitter through
      `build_research_graph`.
- [x] 3b.3 Move the three runner tests that asserted the decision onto the router, keeping one
      runner test for the rendering.

## 4. Tests

- [x] 4.1 Assert both titles and bodies, including the cap in the exhausted-budget body, the absence
      of any elapsed time in either title, and that the failed-revision body carries no draft text.
- [x] 4.2 Assert the router emits exactly once when the cap is reached, and not at all while
      iterations remain.
- [x] 4.3 Assert a cap of one emits nothing — neither this stage nor a findings stage.
- [x] 4.4 Assert the exhausted-budget stage is created before the report and report-review stages of
      the same run, by driving a whole graph run with the cap reached.
- [x] 4.5 Assert the INFO record carries both numbers and that no research-iteration-reviewed record
      fires for the unreviewed iteration.
- [x] 4.6 Assert a revision whose call fails emits exactly one stage naming both draft numbers and the
      failure kind, that the previous draft is still delivered, and that the run's stage channel
      carries no draft text.

## 5. Docs and closeout

- [x] 5.1 Update `docs/architecture.md`: the research-review stage bullet in the loop invariants, and
      the two flowchart edges that describe these hand-offs — the one leaving the iteration gate and
      the one leaving the report node on a failed revision — neither of which says the hand-off is
      announced.
- [x] 5.2 Run `make format` and `make lint`, then the full test suite.
- [x] 5.3 Drive a real query end to end with `scripts/send_conversation.py` against a running server
      configured with a low `max_research_iterations`, and confirm in the DIAL UI that the stage
      appears once, before the report's stages.
