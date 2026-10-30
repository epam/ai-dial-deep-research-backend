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
- **THEN** one INFO "snapshot discarded" record SHALL carry the snapshot's plan id, the current plan
  id, and the reason, `plan_changed`, `not_resumable` or `image_missing`, for `not_resumable` the reason the record
  names when that reads as a known reason, and the resume point the snapshot names when that reads as a known resume point

#### Scenario: No snapshot record carries research content

- **WHEN** any of the four records is written
- **THEN** it SHALL NOT carry message text, the query, a plan step, draft text, a query id, a URL or
  any part of a tool result, at any level

### Requirement: A failure record without a snapshot is one INFO record

When a failed turn persists its failure record without a snapshot (**research-resume**), the app
SHALL write one INFO "failure recorded" record that names the reason no snapshot was saved:
`preparation_failed` for any failure before the research runner was created, `snapshot_refused`,
`no_graph_state` or `snapshot_failed`. It SHALL carry
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

### Requirement: A snapshot or failure record that could not be saved is one WARNING

When building, encoding or saving a snapshot raises, or building, encoding or saving the failure
record raises, the app SHALL log one WARNING that names the exception's class: one WARNING per
state that could not be saved. It SHALL NOT log this at ERROR: the turn's single ERROR record
belongs to the original failure, which the turn still raises.

#### Scenario: The snapshot fails while a quota error is handled

- **WHEN** research-agent fails with a quota error and building the snapshot then raises
- **THEN** the logs SHALL hold one WARNING naming the snapshot failure's exception class, one INFO
  "failure recorded" record with reason `snapshot_failed` and no "snapshot saved" record, followed
  by exactly one ERROR record, for the quota error

### Requirement: A failure after the report is written is one WARNING

When a step fails after the report loop settled a draft (**research-resume**), the app SHALL log
one WARNING that names the step and the exception's class, and SHALL log no ERROR record for it,
because the turn completes. The citation step's own failure records keep their existing form. When the full
state of the final save cannot be built, encoded or written, the WARNING SHALL also say what was
saved instead: `saved=closing_state`, or `saved=nothing` when no state could be written.

#### Scenario: The final save falls back to the closing state

- **WHEN** research delivered its report and the turn's full state cannot be encoded
- **THEN** the logs SHALL hold one WARNING naming the save, the exception's class and
  `saved=closing_state`, no ERROR record, and the turn's "request completed" record SHALL carry
  `outcome=completed`

### Requirement: A retried snapshot image download is one WARNING per failed attempt

When a snapshot image download fails and another attempt will follow, the app SHALL log one
WARNING. The record names the attempt number, the exception's class and the file URL stripped of
its query string and fragment. A download whose last attempt fails is not logged here: it fails the
turn, which logs its one ERROR.

#### Scenario: A download that succeeds on its second attempt

- **WHEN** a snapshot image's first download fails with HTTP 502 or 503 and its second succeeds
- **THEN** the logs SHALL hold one WARNING for the first attempt and no ERROR

### Requirement: A snapshot image upload failure is one WARNING per failed attempt

When a snapshot image upload fails and another attempt will follow, the app SHALL log one WARNING
naming the attempt number and the exception's class. When an image still cannot be uploaded after
its last attempt, the app SHALL log one WARNING for that image, naming its MIME type, its size and
the exception's class. A files bucket that cannot be resolved is one failure, logged once as one
WARNING, not once per image. None of these is an ERROR: the turn's single ERROR record belongs to
the original failure, and a snapshot whose upload failed is still saved, marked not resumable
(**research-resume**).

#### Scenario: An upload that succeeds on its third attempt

- **WHEN** a snapshot image's first two uploads fail with HTTP 503 and its third succeeds
- **THEN** the logs SHALL hold two WARNING records for that image, one per failed attempt, and no
  ERROR record for the upload

### Requirement: A snapshot image that is gone is one WARNING

When a snapshot image's download answers 404 and the snapshot is discarded (**research-resume**),
the app SHALL log one WARNING naming the file URL stripped of its query string and fragment, besides
the INFO "snapshot discarded" record with the reason `image_missing`. A WARNING, not an INFO, because
a file of a saved snapshot should not vanish while the snapshot can still be resumed, and a
permission fault can answer 404 too. It is not an ERROR: the turn goes on and runs research.

#### Scenario: A snapshot with a deleted image

- **WHEN** research starts and one image of the matching resumable snapshot answers 404
- **THEN** the logs SHALL hold one WARNING for that image, one INFO "snapshot discarded" record with
  the reason `image_missing`, and no ERROR record for it

## MODIFIED Requirements

### Requirement: Log level semantics and ERROR ownership

The service SHALL emit log records according to these level semantics — DEBUG: developer
diagnostics (control flow, intermediate values, structure summaries); INFO: the operational
narrative (startup/configuration summaries plus the request skeleton), metadata-only; WARNING:
unexpected conditions the service handled, after which the request continues, possibly degraded;
ERROR: failures that affected the request outcome. A failure SHALL be logged at ERROR exactly
once, by the layer that owns its final handling (`raise_dial_error` in `error_resolution`);
layers that hand a failure onward — to a fallback path or by raising for an upstream handler —
SHALL log at most WARNING. Routine, expected per-request outcomes SHALL log at DEBUG.

#### Scenario: Failed request produces exactly one ERROR

- **WHEN** a turn fails with an unhandled exception
- **THEN** exactly one ERROR record is emitted (by `raise_dial_error`), carrying the stack trace
  and an 8-character `error_reference`

#### Scenario: Handled degraded condition logs WARNING, not ERROR

- **WHEN** a persisted assistant message's `custom_content.state` fails `PreparationDialState` validation
  and the turn falls back to visible-text history
- **THEN** the record is WARNING, and no ERROR is emitted for the condition

#### Scenario: Routine history fallbacks log at DEBUG

- **WHEN** an assistant message carries no custom content, or custom content whose state is not
  a dictionary (a legacy or plain-text turn)
- **THEN** the fallback records are DEBUG, not WARNING

#### Scenario: Chat-model construction logs at DEBUG

- **WHEN** a chat model is constructed for a request
- **THEN** the construction-parameters record is DEBUG, not INFO

### Requirement: Content allowlist for log records

The service's own call sites SHALL NOT emit user/system/assistant/tool message bodies, tool-call
argument values, tool or LLM response bodies, attachment content, header values, or URL query
strings and fragments in log records at any level. Allowed values are structure: roles, counts,
sizes and lengths, durations, tool/deployment/model/agent names, identifiers, statuses and
outcome enums, error codes and types, finish reasons, MIME types, HTTP status codes, header
names, and URLs stripped to scheme, host, and path (DIAL relative `files/...` paths are allowed
once any query string is stripped). Stack traces and third-party exception text are allowed, but
the service's own exceptions SHALL NOT embed payload content in their messages, and a pydantic
`ValidationError` over content-bearing input (persisted conversation state, application
properties) SHALL be logged as its error count plus `loc` paths and error types — never its
rendered text or traceback.

#### Scenario: Image download failure logs a stripped URL

- **WHEN** an image download from DIAL files fails and the failure is logged
- **THEN** the logged URL contains no query string or fragment

#### Scenario: State validation failure logs structure only

- **WHEN** `PreparationDialState` validation of a persisted assistant state fails
- **THEN** the record carries the error count and the failing `loc` paths with error types, and
  no fragment of the persisted messages

#### Scenario: Application-properties validation failure logs structure only

- **WHEN** an instance's application properties fail validation
- **THEN** the WARNING carries the error count and the failing `loc` paths with error types, and
  no property values
