## Why

The INFO request skeleton logs duration and token usage for every LLM call, but there is no
single policy stating what every such record must carry or how its duration is measured — each
call site grew its own log line ad hoc. Two gaps follow from that: three of the six LLM-call
events carry no message count at all, and two nodes measure "duration" over the whole node
(prompt assembly, the call, and post-processing) rather than the call itself, which also happens
to be the same number shown to the user as a DIAL stage's duration. A message count is cheap to
add and, together with a duration that measures only the call, makes context growth across
research-agent iterations and review calls directly readable from the logs — without adding any
payload content.

## What Changes

- Add a general logging policy for LLM calls: every direct LLM call (an agent's model call or a
  raw chain invocation in a node or tool) logs its message count and, when available, its token
  usage; its duration is wall-clock time around the call alone — timed from immediately before
  the model is invoked to immediately after it returns or raises.
- Add a message count to the three INFO events that already had one (model call completed,
  research iteration reviewed, report reviewed) — done — and to the three that did not: report
  generated, query clarity checked, plan approval checked.
- Narrow "duration" in the research-review and report-review nodes' log records to the LLM call
  itself. Both nodes already report a broader, whole-node duration to the user through a DIAL
  stage (`ResearchReviewOutcome.duration_seconds`, `ReportReviewOutcome.duration_seconds`); that
  stays as it is — the log record now gets its own, separate, tighter measurement instead of
  reusing the stage's.
- Narrow "duration" in the report node's log record the same way (it has no stage duration to
  preserve, so its existing timer moves in place).
- Cover failed calls: a failed report-review call and a failed report-revision call still made an
  LLM call, so their records now carry that call's duration and message count too (token usage
  stays unavailable, as it always was on failure). research-review and the two preparation tools
  have no failure path that logs anything (they fail loud, and no record fires), so they need no
  equivalent change.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `logging-policy`: a new general requirement states what every LLM-call log record carries and
  how its duration is measured; the model-call-completed, research-iteration-reviewed, and
  report-reviewed events already gained a message-count field, and report-generated,
  query-clarity-checked, and plan-approval-checked events gain one too.

## Impact

- `src/dial_deep_research/utils/agent_logging.py` — done: `ModelCallLoggingMiddleware` logs a
  message count; its duration already timed only the call.
- `src/dial_deep_research/app/research/nodes.py`:
  - `make_research_review_node` — done: message count added. Still needed: a duration measured
    around only the `llm.ainvoke` call, kept separate from the whole-node duration that feeds
    `ResearchReviewOutcome.duration_seconds`.
  - `make_report_review_node` — done: message count added. Still needed: the same duration split
    against `ReportReviewOutcome.duration_seconds`, and the failed-call path logging that call's
    duration and message count.
  - `make_report_node` — needed: a message count on "Report generated", its duration narrowed to
    the call itself (no stage duration to preserve here), and the failed-revision WARNING logging
    that call's duration and message count.
- `src/dial_deep_research/app/preparation/tools.py` — needed: a message count on `update_query`'s
  "Query clarity checked" and `approve_plan`'s "Plan approval checked" log lines.
- `openspec/specs/logging-policy/spec.md` — a new general requirement for LLM-call logging, plus
  the INFO request skeleton requirement's field lists updated for the three newly-covered events
  and the failed-revision record.
