## Context

The archived change `resume-research-after-failure` (in this branch, under
`openspec/changes/archive/2026-10-30-resume-research-after-failure/`) introduced the research
snapshot. When research starts, `DeepResearchCompletion._find_resumable_snapshot`
(`app/completion.py`) takes the latest research record in the history with `find_latest_snapshot`
and hands it to `read_snapshot` (`app/research/snapshot.py`). `read_snapshot` reads the record in
the order its decision D13 fixed:

1. `plan_id`: not a string raises `SnapshotUnreadableError`; a different id returns a
   `DiscardedSnapshot` with `DiscardReason.PLAN_CHANGED`.
2. `resumable`: not a boolean raises `SnapshotUnreadableError`; `false` returns a
   `DiscardedSnapshot` with `DiscardReason.NOT_RESUMABLE`.
3. `version`: not `SNAPSHOT_VERSION` raises `SnapshotVersionUnsupportedError`.
4. The body: `ResearchSnapshot.model_validate`, a check that `resume_at` is set,
   `messages_from_dict` and `decode_data_queries`. Any exception is re-raised as
   `SnapshotUnreadableError` chained to the original.

Both errors are `AppConditionError` subclasses in `app/error_resolution.py`: the version error is
outgoing 409, the other outgoing 500, both non-retryable, and both texts tell the user to start a
new conversation. `_persist_failure` recognizes them through `_SNAPSHOT_REFUSALS` and saves the
failure record with the reason `snapshot_refused`. A discard, by contrast, makes
`_find_resumable_snapshot` show the "[DEBUG] existing snapshot discarded" stage, log the INFO
"snapshot discarded" record from `DiscardedSnapshot.facts`, and return `None`, after which research
runs fresh in the same turn. A snapshot whose image answers 404 already takes that path
(`discard_for_missing_image`), for the same reason this change gives: a refusal would repeat on
every request. See proposal.md, "Why", for the motivation.

## Goals / Non-Goals

**Goals:**

- `read_snapshot` never raises for what a record contains. Every outcome is a `ResumableSnapshot`
  or a `DiscardedSnapshot`.
- A developer can tell from the logs why a snapshot was discarded and which part failed, within the
  content allowlist of the logging policy.

**Non-Goals:**

- The image download keeps its retryable `SnapshotImageUnavailableError`. A download that fails
  for a reason other than 404 may pass on the next request, so failing the turn keeps the progress.
- No change to the snapshot format or to `SNAPSHOT_VERSION`.
- No change to which record counts as the latest (`find_latest_snapshot`), and no attempt to fall
  back to an older readable snapshot behind an unreadable one. The archived design's rule that the
  latest record hides older ones stays.
- No user-facing note about the discard beyond the existing debug stage. The preparation agent's
  failed-turn note is not touched.

## Decisions

### D1. `read_snapshot` returns a discard where it raises today

Each of the four raise sites becomes a return of `DiscardedSnapshot`. A record that is not a dict,
a `plan_id` that is not a string, a `resumable` that is not a boolean, and a body that fails to
read get `DiscardReason.UNREADABLE`. A matching resumable snapshot with another `version` gets
`DiscardReason.VERSION_UNSUPPORTED`. A record that is not a dict builds
`DiscardedSnapshot(plan_id=None, reason=UNREADABLE, resume_at=None)` directly: `_discarded` calls
`raw.get`, which a string or a list does not have, and an `AttributeError` escaping the reader would
fail every later turn the same way the refusal did. The order of the checks stays as D13 of the
archived change fixed it, so a snapshot of another plan or one marked not resumable is still discarded for that
reason, whatever its version or body. `_find_resumable_snapshot` needs no new branch: it already
shows the stage and logs the record for any `DiscardedSnapshot`.

Alternatives:

- *Keep raising in `read_snapshot` and catch the two errors in `_find_resumable_snapshot`* —
  rejected. The reader already owns the decision between resume and discard; splitting the discard
  across two functions keeps two exception classes alive only to be caught one frame up.
- *Treat a `plan_id` that cannot be read as a changed plan* — rejected. The stage and the log would
  name `plan_changed` for a corrupt record, which sends whoever debugs it down the wrong path.

### D2. Two new reasons, not one

`version_unsupported` and `unreadable` stay apart. A version discard is an expected operational
event after a rollback, or during a rolling deploy once the version is bumped. An `unreadable`
discard of a known version is a bug in the code that wrote the record or the code that read it.
Counting them apart in the logs shows which one is happening. Both are logged at WARNING even so
(D3): a version discard is expected, but it still means a deploy or a rollback cost a user's
resume, which whoever ran it needs to see.

Alternatives:

- *One reason, `unreadable`, for both* — rejected for the reason above. The cost of the second
  value is one enum member.

### D3. `read_snapshot` logs the WARNING where the failure is caught

The WARNING the logging-policy delta requires is written inside `read_snapshot`, at the point where
it catches the failure, because only there is the exception at hand. One helper,
`_discard_unreadable`, writes it for every case and returns the discard, so the record has one
format: the reason first, then `key=value` facts that name the cause.

- A header failure is an `isinstance` check with no exception, so its WARNING names the field
  (`record`, `plan_id` or `resumable`) and the JSON type found.
- A version discard names the version found when it is an `int`, and otherwise only its JSON type,
  under the key `version_type`, so a type name is never read as a version.
- A body failure names the part that failed (`validation`, `research_agent_messages` or
  `data_queries`) and the exception's class. For a pydantic `ValidationError` it adds
  `validation_error_summary(exc)` (`utils/pydantic_errors.py`), which history parsing already uses
  for persisted state, so the record carries the error count, the `loc` paths and the error types
  and never the rendered text. For any other exception it adds the stack trace, which the content
  allowlist permits, so a developer can tell an unknown message type from a missing key.

To know the part, the body read is split into three `try` blocks (validation and the `resume_at`
check, then the messages, then the data queries) rather than the one block it is today. The INFO
"snapshot discarded" record that follows stays where it is, in `_find_resumable_snapshot`.

Alternatives:

- *Carry the cause on `DiscardedSnapshot` and log it in `_find_resumable_snapshot`* — rejected.
  `DiscardedSnapshot.facts` feeds the user-visible stage, which carries ids, names and counts only;
  a cause field would sit beside those facts and could leak into the stage by a later edit.
- *Log every failure with its stack trace* — rejected. The logging policy forbids the traceback of
  a `ValidationError` over persisted state, and a traceback is not needed to find the field that
  failed once its `loc` path is logged.
- *Log only the exception's class for every failure* — rejected. A failure in
  `messages_from_dict` or `decode_data_queries` names nothing but its class then, which cannot tell
  one cause from another.

### D4. `DiscardedSnapshot.plan_id` becomes optional

A record whose `plan_id` cannot be read has no id to show. `plan_id` becomes `str | None`, and
`DiscardedSnapshot.facts` leaves the `plan_id` fact out when it is `None`; `current_plan_id` and
`reason` are always present. For a dict record, `_known` already keeps `resume_at` out when it does
not read as a known value; a record that is not a dict sets `resume_at=None` directly (D1).

Alternatives:

- *A placeholder value such as `"unknown"`* — rejected. It reads like an id in the stage and in a
  log search, and a record could in principle carry that string.

### D5. The refusal machinery is removed

`SnapshotVersionUnsupportedError`, `SnapshotUnreadableError`, `_SNAPSHOT_REFUSALS` and
`_FailureRecordReason.SNAPSHOT_REFUSED` lose their last use and are deleted. The comment on
`_CLIENT_ERROR_STATUS_CODES` that names the snapshot version as a reason for 409 is reduced to the
handed-off refusal. `tests/test_error_delivery.py` uses `SnapshotVersionUnsupportedError` only as a
409 example; that test goes, because
`test_research_already_handed_off_delivered_as_409` covers 409 delivery already.

Alternatives:

- *Keep the classes for a later use* — rejected. Nothing raises them after D1, and an unused
  exception with curated user text suggests a contract that no longer exists.

### D6. This reverses D13 of the archived change, which stays as written

D13 recorded "*Discard the snapshot and research from zero* — rejected by the user. Losing progress
silently is worse than a clear message." The user reversed that decision: the clear message only
said to start a new conversation, which loses the same progress and the conversation too. The
archived design is a record of what was decided at the time, so it is not edited; this design is
where the reversal is recorded, and the main specs change through this change's deltas.

Alternatives:

- *Edit the archived `design.md` in place* — rejected. An archive that is rewritten later no longer
  says why the first implementation behaved as it did.

### D7. `docs/architecture.md` is updated in the same change

The project rule (`CLAUDE.md`, "Keep `docs/architecture.md` up to date with the runtime flow")
covers this, because a turn-boundary behavior changes. Three places change: the failed-turn
flowchart loses "or on a refused snapshot" on its edge to the failure record; the resume sequence
diagram's discard branch adds "or cannot be read"; and the bullet
"A matching snapshot that cannot be read is refused" is replaced by one saying such a snapshot is
discarded and research runs fresh.

## Risks / Trade-offs

- **[A bug that makes every snapshot unreadable disables resume without anyone noticing]** → This is
  the risk D13 of the archived change guarded against. Every resume then becomes a fresh run, the
  user sees research start again, and only the WARNING records say why. Mitigation: the WARNING is
  per discard and names the part that failed, so one log search finds it; and the existing
  round-trip tests in `tests/test_research_resume.py` (`test_a_snapshot_round_trips_through_the_reader`
  and the tests that pass a `build_snapshot` result to `read_snapshot`) catch a writer-reader
  mismatch in CI. With the refusal gone, those tests must assert a `ResumableSnapshot`, since a
  mismatch would otherwise pass as a discard.
- **[The user is not told why research restarted]** → The "[DEBUG] existing snapshot discarded"
  stage names the reason, but a client that hides debug stages shows nothing. Accepted: a discard
  for a changed plan or a gone image already behaves this way.
- **[A rollback or a rolling deploy discards a resume that a newer pod could make]** → Only after a
  version bump, which no current change plans. The refusal left the snapshot the latest record, so
  it stayed reachable for a user who ignored the advice to start a new conversation and whose next
  request reached a newer pod. After a discard the fresh run's record hides it for good. Accepted by
  the user: the difference covers only that narrow case.
- **[A fresh run that fails before its graph starts leaves the unreadable record the latest]** → The
  next request discards it again and reruns research, so the conversation is never stuck; the
  research-resume delta has a scenario for it. Each such turn logs the WARNING again.

## Migration Plan

No stored data changes. A snapshot the current code refuses is discarded by the new code on the
next request that starts research. Rolling back to the code of the archived change restores the
refusal for any unreadable snapshot still latest in a conversation; nothing else is affected.

## No changes required

- `src/dial_deep_research/app/history.py`: it never reads the research record.
- `src/dial_deep_research/utils/image_attachments.py`: `download_snapshot_images` keeps raising
  `SnapshotImageUnavailableError`, which stays.
- `find_latest_snapshot` in `snapshot.py`: which record counts as the latest is unchanged.
- The StatGPT backend: it shows a failed Deep Research turn's `display_message` as it is and
  matches no text (`statgpt/app/chains/deep_research/deep_research_tool.py` in
  epam/statgpt-backend).
- `README.md`, `dial_conf/core/applications-template.json` and `docs/generated-app-schema.json`: no
  setting and no application property changes.
