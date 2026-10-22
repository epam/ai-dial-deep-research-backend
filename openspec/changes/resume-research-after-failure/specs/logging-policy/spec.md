## ADDED Requirements

### Requirement: Research snapshot events are part of the INFO skeleton

The INFO request skeleton SHALL carry four events of **research-resume**, each a stable message
prefix plus `key=value` fields. Snapshot saved and failure recorded (next requirement) are owned by
the failed turn's persistence. Snapshot reused and snapshot discarded are owned by the snapshot
lookup when research starts. Their fields SHALL be ids, names, counts and sizes only, per the
content allowlist.

#### Scenario: A saved snapshot is recorded before the turn's error

- **WHEN** a research run fails and its snapshot is persisted
- **THEN** one INFO "snapshot saved" record SHALL carry the plan id, whether the snapshot is
  resumable, the resume point, the iteration count, the number of transcript messages, the latest
  draft number, the number of data-query records, and the sizes in bytes of the snapshot and of the
  whole state
- **AND** for a snapshot that is not resumable it SHALL also carry the failure class,
  `input_rejected` or `step_budget_exhausted`, and nothing about the failure's content
- **AND** it SHALL precede the turn's single ERROR record and its failed "request completed" record

#### Scenario: A reused snapshot is recorded with the facts of its stage

- **WHEN** research resumes from a snapshot
- **THEN** one INFO "snapshot reused" record SHALL carry the same facts as the "[DEBUG] reusing
  snapshot" stage: the plan id, the resume point, the iteration count, the number of transcript
  messages, the latest draft number, and the completed agent turns or the report-review round where
  the resume point has one

#### Scenario: A discarded snapshot is recorded with its reason

- **WHEN** research starts and the latest snapshot will not be resumed
- **THEN** one INFO "snapshot discarded" record SHALL carry the snapshot's plan id, the current plan
  id, and the reason, `plan_changed` or `not_resumable`, and the resume point the snapshot names
  when that reads as a known resume point

#### Scenario: No snapshot record carries research content

- **WHEN** any of the four records is written
- **THEN** it SHALL NOT carry message text, the query, a plan step, draft text, a query id, a URL or
  any part of a tool result, at any level

### Requirement: A failure record without a snapshot is one INFO record

When a failed turn persists its failure record without a snapshot (**research-resume**), the app
SHALL write one INFO "failure recorded" record that names the reason no snapshot was saved:
`preparation_failed` for any failure before research started, `snapshot_refused`,
`no_graph_state` or `snapshot_failed`. It SHALL carry
nothing about the failure's content, and SHALL precede the turn's single ERROR record, so the logs
say why a failed turn left no snapshot.

#### Scenario: A failure in preparation is recorded

- **WHEN** the approval check fails with a quota error
- **THEN** the logs SHALL hold one INFO "failure recorded" record with reason `preparation_failed`
  and no "snapshot saved" record, followed by exactly one ERROR record, for the quota error

### Requirement: A snapshot or failure record that could not be saved is one WARNING

When building or saving a snapshot raises, or saving the failure record raises, the app SHALL log
one WARNING that names the exception's class. It SHALL NOT log this at ERROR: the turn's single
ERROR record belongs to the original failure, which the turn still raises.

#### Scenario: The snapshot fails while a quota error is handled

- **WHEN** research-agent fails with a quota error and building the snapshot then raises
- **THEN** the logs SHALL hold one WARNING naming the snapshot failure's exception class, one INFO
  "failure recorded" record with reason `snapshot_failed` and no "snapshot saved" record, followed
  by exactly one ERROR record, for the quota error

### Requirement: A failure after the report is written is one WARNING

When a step fails after the report loop settled a draft (**research-resume**), the app SHALL log
one WARNING that names the step and the exception's class, and SHALL log no ERROR record for it,
because the turn completes. A files bucket that cannot be resolved is one failure, logged once, not
once per image. The citation step's own failure records keep their existing form.

#### Scenario: The final save cannot resolve the files bucket

- **WHEN** research delivered its report and resolving the DIAL files bucket at the final save
  raises
- **THEN** the logs SHALL hold one WARNING naming the save and the exception's class, no ERROR
  record, and the turn's "request completed" record SHALL carry `outcome=completed`

### Requirement: A retried snapshot image download is one WARNING per failed attempt

When a snapshot image download fails and another attempt will follow, the app SHALL log one
WARNING. The record names the attempt number, the exception's class and the file URL stripped of
its query string and fragment. A download whose last attempt fails is not logged here: it fails the
turn, which logs its one ERROR.

#### Scenario: A download that succeeds on its second attempt

- **WHEN** a snapshot image's first download fails and its second succeeds
- **THEN** the logs SHALL hold one WARNING for the first attempt and no ERROR
