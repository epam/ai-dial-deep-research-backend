## Why

Two things can happen mid-run that change what the user gets, and neither is visible to them today.
When the research iteration cap is reached, the findings go to the report with no coverage review and
no stage says so. When the model call writing a revision fails, the previous draft is delivered
instead, while the last stage the user saw asked for a revision that never arrives. Both leave only a
server-side log record.

The stage channel is where a run explains itself, and the report loop already treats it that way: a
draft the version budget left unreviewed gets a stage of its own, so "the review approved this" and
"nothing reviewed this" stay distinguishable. The same standard should hold for every hand-off the
user can be misled by. The logs stay as they are — the content allowlist governs them, and none of
this puts new content into a log record.

## What Changes

- **A stage announces a coverage review the iteration cap skipped.** When the just-finished iteration
  is the last one the cap permits, the app emits one closed stage titled
  `[RESEARCH REVIEW RESULT] review budget is exhausted - proceeding to report ⚠️`, carrying the
  iteration number with the cap and stating that the findings go to the report unreviewed. Rendered
  from the state alone, with no model call.
- **A cap of one emits nothing.** With one permitted iteration a coverage review could never be acted
  on, so review is off by configuration rather than exhausted — the rule the report loop applies to a
  version budget of one.
- **A stage announces a revision whose call failed.** When the report call writing a revision fails
  and the previous draft is delivered in its place, the app emits one stage naming the draft that was
  not written, the draft delivered instead, and the failure kind, marked with the error cross. No
  draft text appears in it: a draft the loop did not settle on stays out of the response.
- **The INFO record for the exhausted iteration budget carries the cap**, alongside the iteration
  number, matching its report-side counterpart which carries the version budget.
- **Both skipped-step hand-offs are reported by the router that decides them.** The unreviewed
  delivery moves out of the runner, where it was reconstructed from the final state after the graph
  had finished, into `route_after_report` beside its research counterpart. Nothing the user sees
  changes: the stage renders the same and lands in the same place, since nothing else emits after
  that decision. Its INFO record travels with it rather than being split from the stage it belongs
  to.

## Capabilities

### New Capabilities

None. All three behaviors belong to existing specs.

### Modified Capabilities

- `research-execution`: the requirement "Every research review's findings are visible as a DIAL stage"
  states that an iteration the cap left unreviewed emits no stage. It now emits one, so that sentence
  is replaced by what the stage carries, by where it is emitted, and by the rule for a cap of one.
- `report-composition`: the requirement "Every report review is visible as a DIAL stage and summarized
  in the logs" covers a review that ran, a review that failed, and a delivery the budget left
  unreviewed. It gains the remaining case — a revision whose own call failed.
- `logging-policy`: the INFO request skeleton's research-iteration-budget-exhausted event carries the
  iteration count; it gains the configured cap. The report-delivered-without-review event is owned
  by the research runner; it becomes the report router's, following the code that emits it.

## Impact

Source:

- `src/dial_deep_research/utils/dial_stages.py` — the title and body for the skipped review, and the
  title and body for the failed revision.
- `src/dial_deep_research/app/research/nodes.py` — `route_after_research_agent` reports the skipped
  review through a callback beside the INFO record it already emits, and that record gains the cap;
  `route_after_report` gains the same shape for the unreviewed delivery, measuring the draft where
  it decides; the report node reports its own failed revision through a callback, where the
  exception kind is known.
- `src/dial_deep_research/app/research/graph.py` — the three callbacks threaded in beside the two
  result-stage emitters, and the report structure and ceiling passed to the report router.
- `src/dial_deep_research/app/research/runner.py` — the methods that render them; the unreviewed
  delivery's decision, measurement and log record leave the runner for the router.

Tests: `tests/test_dial_stages.py` for the titles and bodies, `tests/test_research_review_stage.py`
for the skipped review and the silence at a cap of one, `tests/test_report_loop.py` for the failed
revision, `tests/test_research_routing.py` for what each router reports, and a whole-graph test that
each stage lands in the order the work happened.

Docs: `docs/architecture.md` — the stage list in the loop invariants, and the two flowchart edges
that today describe these hand-offs without saying they are announced.

No changes required, though they look adjacent:

- The logs for the failed revision — the WARNING already names the failed and delivered draft numbers
  and the exception kind.
- `src/dial_deep_research/app_properties.py` — no new or changed property.
