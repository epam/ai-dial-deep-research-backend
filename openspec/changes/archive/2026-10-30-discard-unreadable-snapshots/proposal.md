## Why

When research starts and the latest snapshot in the history cannot be read, the turn is refused
with an error that tells the user to start a new conversation. The refused turn saves only its
failure record, so the same snapshot stays the latest one, and every later request to continue is
refused the same way. A snapshot whose plan id cannot be read is never dropped by a changed plan
either, so only a new conversation gets past it.

The refusal protects nothing. A new conversation also runs the research from the beginning, and it
costs the user the conversation as well. Only a developer can fix an unreadable snapshot, and a
WARNING tells the developer as well as a refused turn does. So an unreadable snapshot should be
discarded like a snapshot of another plan, and research should run from the beginning in the same
turn. This reverses decision D13 of the archived change `resume-research-after-failure`, which kept
the refusal on the grounds that losing progress silently is worse than a clear message.

## What Changes

- **A snapshot that cannot be read is discarded, not refused.** This covers a record that is not a
  JSON object, a plan id that is not a string, a snapshot of the current plan whose resumable mark
  is not a boolean, and a matching resumable snapshot whose body fails validation or whose research-agent messages or
  data-query records cannot be decoded. Research then starts from the beginning in the same turn.
- **A matching resumable snapshot of an unknown format version is discarded too**, with a reason of
  its own, instead of being refused with HTTP 409.
- **Two new discard reasons**, `unreadable` and `version_unsupported`, appear in the existing
  "[DEBUG] existing snapshot discarded" stage and the INFO "snapshot discarded" record. A snapshot
  whose plan id cannot be read is shown without a plan id.
- **One WARNING per discarded unreadable snapshot** names the cause: the exception's class, and for
  a pydantic `ValidationError` its error count, `loc` paths and error types only.
- **BREAKING (error contract):** the two refusal messages, "saved by a different version of Deep
  Research and cannot be resumed" (409) and "an error on our side prevents resuming this research"
  (500), are removed. No turn fails because of a snapshot's contents any more. The retryable error
  for a snapshot image that cannot be downloaded right now stays.
- **The failure-record reason `snapshot_refused` is removed**, because no turn is refused for a
  snapshot any more.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `research-resume`: the requirement "A matching snapshot that cannot be read fails the turn" is
  replaced by one that discards such a snapshot. The resume gate ("Research resumes only when the
  latest research record is a resumable snapshot of the current plan") and the stage requirement
  ("The turn shows whether it reused a snapshot") gain the two new discard reasons. "A research
  failure saves a snapshot of the research progress" drops its clause about a refused snapshot.
- `dial-agent-with-mcp`: "Failures delivered as DIAL protocol errors" loses the two snapshot
  refusals and their scenarios, and gains a sentence and a scenario saying that what a snapshot
  contains never fails a turn.
- `logging-policy`: "Research snapshot events are part of the INFO skeleton" gains the two discard
  reasons, "A failure record without a snapshot is one INFO record" loses `snapshot_refused`, and a
  new requirement makes an unreadable snapshot one WARNING.

## Impact

Code:

- `src/dial_deep_research/app/research/snapshot.py`: `read_snapshot` returns a `DiscardedSnapshot`
  in every case where it raises today. `DiscardReason` gains `UNREADABLE` and
  `VERSION_UNSUPPORTED`. `DiscardedSnapshot.plan_id` becomes optional. The module docstring, the
  docstring of `read_snapshot` and the docstring of `ResumableSnapshot.resume_at` stop saying a
  record can be refused.
- `src/dial_deep_research/app/completion.py`: `_SNAPSHOT_REFUSALS`, the
  `_FailureRecordReason.SNAPSHOT_REFUSED` branch of `_persist_failure`, and the refusal sentence of
  `_find_resumable_snapshot`'s docstring are removed. The discard facts handle a missing plan id.
- `src/dial_deep_research/app/error_resolution.py`: `SnapshotVersionUnsupportedError` and
  `SnapshotUnreadableError` are removed, and the comment on `_CLIENT_ERROR_STATUS_CODES` no longer
  names a snapshot version as a reason for 409.
- `src/dial_deep_research/app/research/prompts.py` and `src/dial_deep_research/app/research/state.py`:
  the docstrings of `ResearchReview`, `ReportReview` and `ReportReviewRound` say that an older record
  without an added field "would fail validation, and its resume would be refused". They now say it
  would be discarded.

Tests:

- `tests/test_research_resume.py`: the refusal tests (the `pytest.raises(SnapshotUnreadableError)`
  and `SnapshotVersionUnsupportedError` cases and
  `test_a_refused_snapshot_is_refused_again_on_the_next_request`) become discard tests. The reader
  test keeps its record that is not a JSON object (`"not a snapshot"`).
- `tests/test_error_resolution.py`: the two refusal-resolution tests are removed.
- `tests/test_error_delivery.py`: `test_a_snapshot_of_another_version_is_delivered_as_409` uses
  `SnapshotVersionUnsupportedError` as its 409 example. It goes, since
  `test_research_already_handed_off_delivered_as_409` already covers delivery of a 409.

Docs:

- `docs/architecture.md`: the failed-turn flowchart drops "or on a refused snapshot" from the edge
  to the failure record, the resume sequence diagram adds the unreadable case to the discard
  branch, and the bullet "A matching snapshot that cannot be read is refused" is replaced.

Other systems: none. StatGPT shows the `display_message` of any failed Deep Research turn as it
is and matches no error text (`statgpt/app/chains/deep_research/deep_research_tool.py` in
epam/statgpt-backend), so removing the two texts changes nothing for it.
