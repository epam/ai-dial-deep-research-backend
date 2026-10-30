## MODIFIED Requirements

### Requirement: Research snapshot events are part of the INFO skeleton

The INFO request skeleton SHALL carry four events of **research-resume**, each a stable message
prefix plus `key=value` fields. Snapshot saved and failure recorded (next requirement) are owned by
the failed turn's persistence. Snapshot reused and snapshot discarded are owned by the snapshot
lookup when research starts. Their fields SHALL be ids, names, counts and sizes only, per the
content allowlist.

#### Scenario: A saved snapshot is recorded before the turn's error

- **WHEN** a research run fails and its snapshot is persisted
- **THEN** one INFO "snapshot saved" record SHALL carry the plan id, whether the snapshot is
  resumable, the resume point, the iteration count, the number of research-agent messages, the
  latest draft number, the number of data-query records, and the sizes in bytes of the snapshot and
  of the whole state
- **AND** for a snapshot that is not resumable it SHALL also carry the reason it names,
  `repeating_failure` or `image_upload_failed`, and for `repeating_failure` the failure class,
  `input_rejected` or `step_budget_exhausted`, and nothing about the failure's content
- **AND** it SHALL precede the turn's single ERROR record and its failed "request completed" record

#### Scenario: A reused snapshot is recorded with the facts of its stage

- **WHEN** research resumes from a snapshot
- **THEN** one INFO "snapshot reused" record SHALL carry the same facts as the "[DEBUG] reusing
  snapshot" stage: the plan id, the resume point, the iteration count, the number of research-agent
  messages, the latest draft number, and the restored model calls of the interrupted iteration or
  the report-review round where the resume point has one

#### Scenario: A discarded snapshot is recorded with its reason

- **WHEN** research starts and the latest snapshot will not be resumed
- **THEN** one INFO "snapshot discarded" record SHALL carry the snapshot's plan id when it reads as
  a string, the current plan id, and the reason, `plan_changed`, `not_resumable`, `image_missing`,
  `version_unsupported` or `unreadable`, for `not_resumable` the reason the record names when that
  reads as a known reason, and the resume point the snapshot names when that reads as a known
  resume point

#### Scenario: No snapshot record carries research content

- **WHEN** any of the four records is written
- **THEN** it SHALL NOT carry message text, the query, a plan step, draft text, a query id, a URL or
  any part of a tool result, at any level

### Requirement: A failure record without a snapshot is one INFO record

When a failed turn persists its failure record without a snapshot (**research-resume**), the app
SHALL write one INFO "failure recorded" record that names the reason no snapshot was saved:
`preparation_failed` for any failure before the research runner was created, `no_graph_state` or
`snapshot_failed`. It SHALL carry
nothing about the failure's content, and SHALL precede the turn's single ERROR record, so the logs
say why a failed turn left no snapshot.

#### Scenario: A snapshot image that cannot be downloaded is recorded as no_graph_state

- **WHEN** research starts, a matching resumable snapshot is found, and one of its images still
  fails with HTTP 503 after its last attempt
- **THEN** the logs SHALL hold one INFO "failure recorded" record with reason `no_graph_state`, not
  `preparation_failed`, followed by exactly one ERROR record

#### Scenario: A failure in preparation is recorded

- **WHEN** the approval check fails with a quota error
- **THEN** the logs SHALL hold one INFO "failure recorded" record with reason `preparation_failed`
  and no "snapshot saved" record, followed by exactly one ERROR record, for the quota error


## ADDED Requirements

### Requirement: A snapshot that cannot be read is one WARNING

When research starts and the latest snapshot is discarded because its format version is not one
this code reads or because it cannot be read (**research-resume**), the app SHALL log one WARNING
besides the INFO "snapshot discarded" record. The WARNING names the discard reason and the cause:

- for `version_unsupported`, the format version found when it is an integer, and otherwise only
  the JSON type found, under a key of its own;
- for `unreadable` in the header, the field that could not be read (the record itself, the plan id
  or the resumable mark) and the JSON type found;
- for `unreadable` in the body, the part that failed (the record's validation, the research-agent
  messages or the data-query records) and the exception's class. For a pydantic `ValidationError`
  it carries only the error count, the `loc` paths and the error types, per the content allowlist,
  never the rendered text or a traceback. For any other exception it carries the stack trace.

A WARNING, not an INFO, because each case means a user's saved progress was thrown away: an
unreadable snapshot is a bug in the code that wrote it or read it, and a version discard means a
rollback or a deploy cost a resume, which whoever ran it needs to see. It is not an ERROR: the turn
goes on and runs research.

#### Scenario: A snapshot that fails validation

- **WHEN** research starts and the matching resumable snapshot fails validation
- **THEN** the logs SHALL hold one WARNING naming the reason `unreadable`, the part that failed,
  the exception's class, the error count, the `loc` paths and the error types, one INFO "snapshot
  discarded" record with the reason `unreadable`, and no ERROR record for it

#### Scenario: A snapshot of another version

- **WHEN** research starts and the matching resumable snapshot carries a format version this code
  does not read
- **THEN** the logs SHALL hold one WARNING naming the reason `version_unsupported` and the version
  found, one INFO "snapshot discarded" record with the reason `version_unsupported`, and no ERROR
  record for it
