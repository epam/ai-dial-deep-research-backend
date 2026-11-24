# Spec Delta

## MODIFIED Requirements

### Requirement: The turn shows whether it reused a snapshot

When research starts and the history holds a snapshot, the turn SHALL show one stage. It is
"[DEBUG] reusing snapshot" when the run resumes from the snapshot, and "[DEBUG] existing snapshot
discarded" when the plan ids differ, the snapshot is marked not resumable, one of its images is
gone, its format version is not one this code reads, or it cannot be read. Both stages SHALL carry
only ids, names and counts. They are debug stages (see **debug-stages**), so they SHALL be emitted
only when the deployment shows debug stages. No such stage SHALL be shown when no snapshot is found,
or when the turn fails before deciding: an image that cannot be downloaded fails the turn without a
stage.

#### Scenario: A reused snapshot

- **WHEN** research resumes from a snapshot
- **THEN** the "[DEBUG] reusing snapshot" stage SHALL carry the snapshot's plan id, its resume
  point, its iteration count, the number of research-agent messages, and the latest draft number
- **AND** for resume point research it SHALL also carry the number of the interrupted iteration's
  model calls the snapshot restored, and for resume point report review the report-review round

#### Scenario: A discarded snapshot

- **WHEN** research starts and the latest snapshot will not be resumed
- **THEN** the "[DEBUG] existing snapshot discarded" stage SHALL carry the snapshot's plan id when
  it reads as a string, the current plan id, and the reason: the plan changed, the snapshot is not resumable, with the
  reason the record names when that reads as a known reason, an image is missing, the format
  version is unsupported, or the snapshot is unreadable
- **AND** it SHALL carry the resume point the snapshot names only when that reads as a known resume
  point, because a snapshot discarded for a changed plan, for being not resumable, for its version
  or for being unreadable is not read whole

#### Scenario: A snapshot whose plan id cannot be read

- **WHEN** research starts and the latest snapshot's plan id is not a string
- **THEN** the "[DEBUG] existing snapshot discarded" stage SHALL carry the current plan id and the
  reason that the snapshot is unreadable, and SHALL carry no plan id for the snapshot

#### Scenario: A deployment that hides debug stages shows no snapshot stage

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and research resumes from a snapshot
- **THEN** the turn SHALL resume from the snapshot and SHALL show no "[DEBUG] reusing snapshot"
  stage
