## 1. Model-call logging middleware

- [x] 1.1 In `ModelCallLoggingMiddleware.awrap_model_call` (`src/dial_deep_research/utils/agent_logging.py`), compute the message count from `request` (system message, if any, plus `request.messages`) and add `messages=%d` to the "Model call completed" log line.

## 2. Research-review node

- [x] 2.1 In `make_research_review_node` (`src/dial_deep_research/app/research/nodes.py`), keep the assembled system+human message list in a variable before the `llm.ainvoke` call, and add `messages=%d` (its length) to the "Research iteration reviewed" log line.

## 3. Report-review node

- [x] 3.1 In `make_report_review_node` (`src/dial_deep_research/app/research/nodes.py`), keep the assembled system+human message list in a variable before the `llm.ainvoke` call — available whether the call succeeds or raises — and add `messages=%d` (its length) to the "Report reviewed" log line.

## 4. Verification (first pass — model-call middleware, research-review, report-review message counts)

- [x] 4.1 Run `make format` and `make lint`.
- [x] 4.2 Update or add tests covering the three new log fields (existing tests for these log lines, if any, plus any logging-policy test suite).
- [x] 4.3 Run `make test` (or `poetry run pytest`) and confirm it passes.

## 5. Duration split: research-review and report-review

- [x] 5.1 In `make_research_review_node`, add a separate timer around only `llm.ainvoke(review_messages)` and use it (not the whole-node `duration`) in the "Research iteration reviewed" log line. Leave the whole-node `duration` feeding `ResearchReviewOutcome.duration_seconds` unchanged.
- [x] 5.2 In `make_report_review_node`, add a separate timer around only `llm.ainvoke(review_messages)`, computed on both the success and the exception path (the call may raise), and use it in the "Report reviewed" log line. Leave the whole-node `duration` feeding `ReportReviewOutcome.duration_seconds` unchanged.

## 6. Report node

- [x] 6.1 Add a message count (`len(report_messages)`) to the "Report generated" INFO log line.
- [x] 6.2 Narrow the existing `duration` timer to start immediately before `llm.ainvoke(report_messages)` instead of at the top of the node (no stage duration depends on the current broader measurement, so this can move in place).
- [x] 6.3 Add duration and message count to the "Report revision failed" WARNING log line, using the same narrowed timer (token usage stays absent, as it already is).

## 7. Preparation tools

- [x] 7.1 Add a message count to `_update_query`'s "Query clarity checked" log line.
- [x] 7.2 Add a message count to `_approve_plan`'s "Plan approval checked" log line.
- [x] 7.3 Confirm each tool's existing `start = time.monotonic()` already sits immediately before `llm.ainvoke(...)` (with only cheap, non-blocking object construction in between) — adjust only if it does not.

## 8. Verification (second pass — duration split, report node, preparation tools)

- [x] 8.1 Run `make format` and `make lint`.
- [x] 8.2 Extend or add tests: report node's message count and narrowed duration on both the success and the failed-revision path; the two preparation tools' message counts; a test asserting the research-review/report-review log duration differs from (and is not derived from) the stage's `duration_seconds` when there is measurable non-call work in the node.
- [x] 8.3 Run `make test` and confirm it passes.

## 9. End-to-end smoke test

- [x] 9.1 Start the DR server from this worktree and send one short research turn (a query about the latest short insight-type publication, chosen only to keep token usage low) via `scripts/send_conversation.py`, using a conversation artifact file outside the repo (e.g. under `$TMPDIR`) so no query content is ever written into a repo-tracked path.
- [x] 9.2 Confirm the new message-count (and, where changed, duration) fields appear in the logs for each LLM call site touched by this change.
