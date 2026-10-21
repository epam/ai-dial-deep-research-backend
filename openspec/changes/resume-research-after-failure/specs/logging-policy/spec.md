## ADDED Requirements

### Requirement: Research snapshot events are part of the INFO skeleton

The INFO request skeleton SHALL carry four events of **research-resume**, each a stable message
prefix plus `key=value` fields. Snapshot saved and snapshot skipped (next requirement) are owned by
the failed turn's persistence. Snapshot reused and snapshot discarded are owned by the snapshot
lookup when research starts. Their fields SHALL be ids, names, counts and sizes only, per the
content allowlist.

#### Scenario: A saved snapshot is recorded before the turn's error

- **WHEN** a research run fails and its snapshot is persisted
- **THEN** one INFO "snapshot saved" record SHALL carry the plan id, the resume point, the iteration
  count, the number of transcript messages, the latest draft number, the number of data-query
  records, and the sizes in bytes of the snapshot and of the whole state
- **AND** it SHALL precede the turn's single ERROR record and its failed "request completed" record

#### Scenario: A reused snapshot is recorded with the facts of its stage

- **WHEN** research resumes from a snapshot
- **THEN** one INFO "snapshot reused" record SHALL carry the same facts as the "[DEBUG] reusing
  snapshot" stage: the plan id, the resume point, the iteration count, the number of transcript
  messages, the latest draft number, and the completed agent turns or the report-review round where
  the resume point has one

#### Scenario: A discarded snapshot is recorded with both ids

- **WHEN** research starts and the latest snapshot's plan id differs from the current one
- **THEN** one INFO "snapshot discarded" record SHALL carry the snapshot's plan id, the current plan
  id and the resume point the snapshot names

#### Scenario: No snapshot record carries research content

- **WHEN** any of the four records is written
- **THEN** it SHALL NOT carry message text, the query, a plan step, draft text, a query id, a URL or
  any part of a tool result, at any level

### Requirement: A failure a resume would repeat is recorded as a skipped snapshot

When a research run fails with a failure a resume would repeat (**research-resume**), the app SHALL
write one INFO "snapshot skipped" record that names the failure class, `input_rejected` or
`step_budget_exhausted`, says that the plan id was cleared, and carries nothing about the failure's
content. It SHALL precede the turn's single ERROR record, so the logs say why a failed research
turn left no snapshot.

#### Scenario: A context-length rejection is recorded as skipped

- **WHEN** research-agent's model call is rejected with `context_length_exceeded`
- **THEN** the logs SHALL hold one INFO "snapshot skipped" record with class `input_rejected` and
  no "snapshot saved" record, followed by exactly one ERROR record, for the rejection

### Requirement: A snapshot that could not be built is one WARNING

When building or saving a snapshot raises, the app SHALL log one WARNING that names the exception's
class. It SHALL NOT log this at ERROR: the turn's single ERROR record belongs to the original
failure, which the turn still raises.

#### Scenario: The snapshot fails while a quota error is handled

- **WHEN** research-agent fails with a quota error and building the snapshot then raises
- **THEN** the logs SHALL hold one WARNING naming the snapshot failure's exception class and no
  "snapshot saved" record, followed by exactly one ERROR record, for the quota error

### Requirement: A retried snapshot image download is one WARNING per failed attempt

When a snapshot image download fails and another attempt will follow, the app SHALL log one
WARNING. The record names the attempt number, the exception's class and the file URL stripped of
its query string and fragment. A download whose last attempt fails is not logged here: it fails the
turn, which logs its one ERROR.

#### Scenario: A download that succeeds on its second attempt

- **WHEN** a snapshot image's first download fails and its second succeeds
- **THEN** the logs SHALL hold one WARNING for the first attempt and no ERROR
