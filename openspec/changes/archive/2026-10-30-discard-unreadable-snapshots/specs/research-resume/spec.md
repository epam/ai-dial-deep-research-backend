## MODIFIED Requirements

### Requirement: A research failure saves a snapshot of the research progress

When an exception ends a research run after `start_research` passed its gate, and the research
graph has streamed at least one state, the turn SHALL save a snapshot of the progress with its
single state write, then deliver the original error (**dial-agent-with-mcp**). Any kind counts (a
quota error, an upstream outage, a timeout, a bug), and so does a failure a resume would repeat,
whose snapshot is marked not resumable (**Failures a resume would repeat save a snapshot that is
never resumed**). No snapshot is saved when the run fails before its graph streamed any state. Once
the report loop has settled a draft, the run does not fail at all (**A turn never fails once its
report is written**).

#### Scenario: A quota error inside research-agent

- **WHEN** a research-agent model call raises `openai.RateLimitError` because DIAL Core answered
  429 for the user's daily token limit
- **THEN** the turn SHALL persist a snapshot and SHALL then deliver the error with DIAL Core's
  `display_message`, and the state SHALL reach the client ahead of the error chunk

#### Scenario: An upstream outage in research-review

- **WHEN** the research-review model call fails with an HTTP 502 from DIAL Core
- **THEN** the turn SHALL persist a snapshot and deliver the error, exactly as for a quota error

#### Scenario: A failure in preparation saves no snapshot

- **WHEN** the preparation agent's model call raises a quota error, before `start_research` passed
- **THEN** the turn SHALL save no snapshot, because there is no research progress to save, and
  SHALL persist only its failure record (**Every failed turn records that it failed**)

#### Scenario: The research tools cannot be loaded

- **WHEN** an MCP server cannot be reached while the research tools load, before the graph starts
- **THEN** the turn SHALL save no snapshot and SHALL persist only its failure record

#### Scenario: A failed tool call does not end research

- **WHEN** a research tool call fails and is relayed to research-agent as an error tool result
  (**tool-call-fault-tolerance**)
- **THEN** research SHALL go on and no snapshot SHALL be saved for that failure

#### Scenario: A cancellation saves nothing

- **WHEN** the research run ends because the user pressed Stop, the client disconnected, DIAL
  Core's idle timeout closed the connection, or the pod was killed
- **THEN** no state SHALL be saved, and research on a later turn SHALL start from zero
- **AND** this SHALL stand as an accepted limitation: the connection is gone by the time the turn
  ends, and the DIAL SDK allows one state write per turn, so the progress cannot be sent while
  research runs

#### Scenario: A non-streaming request carries no snapshot

- **WHEN** a research run fails on a non-streaming request
- **THEN** the client SHALL receive the error alone and no state, because the DIAL SDK raises on
  the error chunk and drops the merged response, state included; a resume therefore needs a
  streaming client, which DIAL Chat and StatGPT both are

### Requirement: Research resumes only when the latest research record is a resumable snapshot of the current plan

When research starts in a turn, the app SHALL take the latest assistant message in the history that
carries a snapshot. It SHALL resume from that snapshot only when the snapshot's plan id equals the
current plan id, the snapshot is not marked not resumable, and the snapshot can be read; otherwise
research SHALL start fresh. A latest record that is not resumable hides every older one, whatever
its reason: research then starts fresh, and no older snapshot is used. A resumable snapshot of the
current plan whose image is gone is discarded the same way (**A snapshot's images are downloaded
before the resumed run starts**), and so is a snapshot that cannot be read (**A snapshot that
cannot be read is discarded**). Turns between the failure and the resume, failed turns
that saved no snapshot among them, SHALL NOT hide the snapshot.

#### Scenario: A question between the failure and the resume

- **WHEN** the user asks what happened, gets an answer, and then asks to continue
- **THEN** research SHALL resume from the snapshot of the failed turn two answers back

#### Scenario: "continue" while the quota is still exhausted

- **WHEN** the user asks to continue while the quota is still exhausted, so the preparation turn
  fails and saves only its failure record, and later asks to continue again
- **THEN** the later turn SHALL resume from the snapshot of the original failed turn

#### Scenario: A changed query or plan starts fresh

- **WHEN** the user changes the query or the plan after a failed research run, so `update_query` or
  `update_plan` runs, and then approves the new plan
- **THEN** research SHALL start from zero, and the old snapshot SHALL be discarded

#### Scenario: A snapshot that is not resumable starts fresh

- **WHEN** research starts and the latest snapshot in the history is marked not resumable
- **THEN** research SHALL start from zero, even though the snapshot's plan id equals the current one

#### Scenario: A second failure during a resumed run

- **WHEN** a resumed run fails again, after its graph streamed state, with a failure a resume can
  get past
- **THEN** the turn SHALL save a new snapshot, and the next request to continue SHALL resume from
  the new one

#### Scenario: A resumed run that fails before its graph starts keeps the earlier snapshot

- **WHEN** a resumed run fails before its graph streamed any state, for example because an MCP
  server cannot be reached while the research tools load
- **THEN** the turn SHALL save no snapshot, its failure record SHALL keep the plan id, and the next
  request to continue SHALL resume from the snapshot the failed turn started from

#### Scenario: No snapshot in the history

- **WHEN** research starts on a conversation with no snapshot in its history
- **THEN** research SHALL start fresh, as before this capability existed

### Requirement: The turn shows whether it reused a snapshot

When research starts and the history holds a snapshot, the turn SHALL show one stage. It is
"[DEBUG] reusing snapshot" when the run resumes from the snapshot, and "[DEBUG] existing snapshot
discarded" when the plan ids differ, the snapshot is marked not resumable, one of its images is
gone, its format version is not one this code reads, or it cannot be read. Both stages SHALL carry
only ids, names and counts. They SHALL always be emitted, because "[DEBUG]" is only part of the
title. No such stage SHALL be shown when no snapshot is found, or when the turn fails before
deciding: an image that cannot be downloaded fails the turn without a stage.

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

## ADDED Requirements

### Requirement: A snapshot that cannot be read is discarded

The app SHALL compare plan ids, then read the resumable mark, then the format version, before it
reads the rest of the snapshot. A snapshot SHALL be discarded, and research SHALL start from the
beginning in the same turn, when any of these holds:

- The research record is not a JSON object, or its plan id is not a string, whatever the current
  plan id. The reason is `unreadable`.
- It is a snapshot of the current plan whose resumable mark is not a boolean. The reason is
  `unreadable`.
- It is a resumable snapshot of the current plan whose format version this code does not read. The
  reason is `version_unsupported`.
- It is a resumable snapshot of the current plan, of a known version, that fails validation, or
  whose research-agent messages or data-query records cannot be decoded. The reason is
  `unreadable`.

No turn SHALL fail because of what a snapshot contains. A refusal could only tell the user to
start a new conversation, which also runs the research from the beginning and costs the
conversation too. The discard is logged as one WARNING (**logging-policy**), which is how a
developer learns of it. The record the fresh run saves then becomes the latest one, so the same
snapshot is not met again.

#### Scenario: A snapshot saved by a different version

- **WHEN** research starts with a matching resumable snapshot whose format version this code does
  not read, for example after a release changed the format, or after a rollback
- **THEN** the snapshot SHALL be discarded with the reason `version_unsupported`, and research
  SHALL start from the beginning in the same turn, with no protocol error

#### Scenario: A snapshot that fails to read

- **WHEN** research starts with a matching resumable snapshot of a known version that fails
  validation or whose research-agent messages cannot be decoded
- **THEN** the snapshot SHALL be discarded with the reason `unreadable`, and research SHALL start
  from the beginning in the same turn, with no protocol error

#### Scenario: A snapshot header that cannot be read

- **WHEN** research starts and the latest research record is not a JSON object or has a plan id
  that is not a string
- **THEN** the snapshot SHALL be discarded with the reason `unreadable`, whatever the current plan
  id, and research SHALL start from the beginning in the same turn

#### Scenario: A resumable mark that cannot be read

- **WHEN** research starts and the latest snapshot has a resumable mark that is not a boolean
- **THEN** the snapshot SHALL be discarded with the reason `unreadable` when its plan id equals the
  current one, and with the reason `plan_changed` when it does not

#### Scenario: A snapshot that will not be resumed is discarded without being read whole

- **WHEN** research starts with a snapshot whose plan id differs from the current one, or which is
  marked not resumable, whatever its version or contents
- **THEN** research SHALL start fresh, and the snapshot SHALL be discarded with the reason
  `plan_changed` or `not_resumable`, without being read further

#### Scenario: The next request after a discard

- **WHEN** a turn discarded an unreadable snapshot and its fresh research run saved a record
- **THEN** the next request that starts research SHALL read that record, not the unreadable one

#### Scenario: A fresh run that fails before its graph starts

- **WHEN** a turn discarded an unreadable snapshot and its fresh research run failed before its
  graph streamed any state, so the turn saved only its failure record
- **THEN** the next request that starts research SHALL discard the same snapshot again and run
  research from the beginning, and SHALL NOT fail because of it

## REMOVED Requirements

### Requirement: A matching snapshot that cannot be read fails the turn

**Reason**: A refused turn could only tell the user to start a new conversation, which also runs
the research from the beginning, and the refusal repeated on every later request because the
refused snapshot stayed the latest record. Discarding the snapshot reruns the research in place.

**Migration**: Replaced by **A snapshot that cannot be read is discarded**. No stored data
changes: a snapshot that the old code refused is discarded by the new code.
