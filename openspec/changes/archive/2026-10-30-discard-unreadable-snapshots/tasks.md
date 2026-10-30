# Tasks

Decision numbers (D1–D7) refer to this change's `design.md`.

## 1. The reader discards instead of raising

- [x] 1.1 Add `UNREADABLE = "unreadable"` and `VERSION_UNSUPPORTED = "version_unsupported"` to
  `DiscardReason`, and make `DiscardedSnapshot.plan_id` `str | None`, with `facts` leaving the
  `plan_id` fact out when it is `None` (`app/research/snapshot.py`, D2, D4). Verify in
  `tests/test_research_resume.py` that the facts of a discard without a plan id carry
  `current_plan_id` and `reason` and no `plan_id`.
- [x] 1.2 Change `read_snapshot` so that each of its four raise sites returns a `DiscardedSnapshot`
  (D1). A record that is not a dict builds `DiscardedSnapshot(plan_id=None, reason=UNREADABLE,
  resume_at=None)` directly, without calling `_discarded`. A `plan_id` that is not a string
  discards as `unreadable` with no plan id. A non-boolean `resumable` on a matching plan discards as
  `unreadable`. A matching resumable snapshot with another `version` discards as
  `version_unsupported`. A body that fails to read discards as `unreadable`. Keep the order of the
  checks: plan id, resumable mark, version, body.
- [x] 1.3 Log one WARNING in `read_snapshot` for each discard of 1.2 (D3). A header failure names
  the field (`record`, `plan_id` or `resumable`) and the JSON type found. A version discard names
  the version found when it is an `int`. A body failure names the part (`validation`,
  `research_agent_messages` or `data_queries`) and the exception's class, plus
  `validation_error_summary(exc)` for a pydantic `ValidationError`, with no `exc_info`. Split the
  body read into three `try` blocks to know the part: validation together with the `resume_at`
  check, then `messages_from_dict`, then `decode_data_queries`.
- [x] 1.4 Update the docstrings that say a record can be refused: the module docstring and
  `read_snapshot` in `snapshot.py`, `ResumableSnapshot.resume_at` (`snapshot.py:233`), and the
  "its resume would be refused" sentence on `ResearchReview` and `ReportReview`
  (`app/research/prompts.py`) and on `ReportReviewRound` (`app/research/state.py`), which now say
  the record would be discarded.
- [x] 1.5 Convert the reader tests in `tests/test_research_resume.py`:
  `test_a_snapshot_whose_plan_id_cannot_be_read_is_unreadable` (keep its three records, the string
  `"not a snapshot"` among them),
  `test_a_resumable_mark_that_is_not_a_boolean_is_unreadable`,
  `test_a_matching_snapshot_of_another_version_is_refused`, and the parametrized
  `SnapshotUnreadableError` test near line 313, so each asserts a `DiscardedSnapshot` with its
  reason. Add a case for a non-boolean resumable mark on another plan, which discards as
  `plan_changed`. Assert the WARNING of 1.3 for one header case, the version case and one
  `ValidationError` case, and that the `ValidationError` WARNING carries no input value.

## 2. The turn coordinator and the error resolver

- [x] 2.1 In `app/completion.py`, remove `_SNAPSHOT_REFUSALS`, the `SNAPSHOT_REFUSED` member of
  `_FailureRecordReason` and its branch in `_persist_failure`, and the refusal sentence of
  `_find_resumable_snapshot`'s docstring (D5). Check that `_find_resumable_snapshot` shows the
  discard stage and logs the INFO record for the new reasons with no further change, and that it
  passes the facts of a discard without a plan id through unchanged.
- [x] 2.2 In `app/error_resolution.py`, delete `SnapshotVersionUnsupportedError` and
  `SnapshotUnreadableError`, and reduce the comment on `_CLIENT_ERROR_STATUS_CODES` to the
  handed-off refusal as the reason for 409 (D5). Keep `SnapshotImageUnavailableError`.
- [x] 2.3 Remove the tests of the deleted errors: the two refusal-resolution tests in
  `tests/test_error_resolution.py` (near lines 200 and 209) and
  `test_a_snapshot_of_another_version_is_delivered_as_409` in `tests/test_error_delivery.py`,
  whose 409 delivery `test_research_already_handed_off_delivered_as_409` already covers.
- [x] 2.4 Replace `test_a_refused_snapshot_is_refused_again_on_the_next_request` in
  `tests/test_research_resume.py` with turn-level tests through the HTTP client: an
  unknown-version snapshot and an unreadable snapshot each make the turn run research fresh with
  no protocol error and show the "[DEBUG] existing snapshot discarded" stage with the reason; the
  next request reads the record the fresh run saved; and when the fresh run fails before its graph
  starts, the following request discards the same snapshot again and runs research fresh rather
  than failing.

## 3. Docs

- [x] 3.1 Update `docs/architecture.md` (D7): drop "or on a refused snapshot" from the failed-turn
  flowchart's edge to the failure record, add "or cannot be read" to
  the discard branch of the resume sequence diagram, and replace the bullet "A matching snapshot
  that cannot be read is refused" with one saying such a snapshot is discarded and research runs
  fresh in the same turn.

## 4. Checks

- [x] 4.1 Grep `src/`, `tests/`, `docs/` and `openspec/specs/` for `SnapshotUnreadableError`,
  `SnapshotVersionUnsupportedError`, `snapshot_refused`, `_SNAPSHOT_REFUSALS`, "different version
  of Deep Research" and "prevents resuming", and confirm nothing outside this change's deltas and
  the archived change still names them.
- [x] 4.2 Run `make format`, `make lint` and `make test`, and fix what they report.
