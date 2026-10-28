## Purpose

Saves a research run's progress when the run fails, most often because the user's DIAL quota ran
out, and lets a later turn of the same conversation continue that research where it stopped
instead of starting it again.

## ADDED Requirements

### Requirement: A research failure saves a snapshot of the research progress

When an exception ends a research run after `start_research` passed its gate, and the research
graph has streamed at least one state, the turn SHALL save a snapshot of the progress with its
single state write, then deliver the original error (**dial-agent-with-mcp**). Any kind counts (a
quota error, an upstream outage, a timeout, a bug), and so does a failure a resume would repeat,
whose snapshot is marked not resumable (**Failures a resume would repeat save a snapshot that is
never resumed**). No snapshot is saved when the run fails before its graph streamed any state, or
when the snapshot being resumed is refused. Once the report loop has settled a draft, the run does
not fail at all (**A turn never fails once its report is written**).

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

### Requirement: Every failed turn records that it failed

A turn that fails and is delivered as a protocol error SHALL persist a state that carries a failure
flag, under a key of its own and never inside `PrepState`, which every turn carries forward. A turn
whose research run saved a snapshot persists the parts that **A failed research turn persists the
snapshot beside a reset PrepState** lists, the flag among them. Any other failed turn, and a
failed research turn whose snapshot state cannot be built or encoded, SHALL persist the failure
record: an empty `messages`, the `PrepState` the request's history held when the turn started,
and the flag. That `PrepState` is read again from the request, so a failure during preparation
never changes the recorded query, plan or plan id.

A state that cannot be built or encoded SHALL fall back in the order that **A turn's one state
write falls back in a fixed order** lists. These cases persist nothing: a failure
before the conversation's state is loaded and checked, such as a failure while the application
properties are fetched or validated; a cancellation; a non-streaming request; the refusal of a
conversation whose report was delivered; and a closed choice, which takes no state.

#### Scenario: A failure while the properties are fetched persists nothing

- **WHEN** fetching the application properties fails on a conversation that has a recorded plan
- **THEN** the turn SHALL persist no state, and the next turn SHALL read the latest earlier state,
  so the recorded query, plan and plan id stay as they were

#### Scenario: A preparation failure keeps the turn's starting state

- **WHEN** the user approves the plan and the approval check then fails with a quota error
- **THEN** the persisted `PrepState` SHALL equal the one the turn started from, and the state SHALL
  carry the failure flag

#### Scenario: A snapshot state that cannot be encoded falls back

- **WHEN** a research run fails after its graph streamed state, and the state carrying its
  snapshot cannot be encoded as JSON
- **THEN** the turn SHALL persist the failure record instead, with one state write, and SHALL
  deliver the original error

#### Scenario: The flag is not carried forward

- **WHEN** a turn completes after a failed turn
- **THEN** its state SHALL carry no failure flag

#### Scenario: Saving the failure record never hides the failure

- **WHEN** the failure record itself cannot be built, encoded or saved
- **THEN** the turn SHALL persist no state, SHALL record each save failure once
  (**logging-policy**), and SHALL deliver the original error

### Requirement: A turn never fails once its report is written

A report costs a whole research run, so once the report loop has settled a draft the turn SHALL
complete without a protocol error, whatever fails after that point. A cancellation is the one
exception, because the connection is gone. Every later step SHALL absorb its own failure, keep what
it already did, and record the failure once (**logging-policy**): the citation step, appending the
report, sending its annotations, recording the citation outcome, and saving the turn's state.
Through StatGPT this decides whether the user gets the report at all, because StatGPT shows a
report only when Deep Research's answer ends without an error and its state says research started.

The final save SHALL still close the conversation. When an image cannot be uploaded for any reason,
the files bucket that cannot be resolved included, the image SHALL be replaced by the upload-failure
placeholder (**dial-agent-with-mcp**), and the state SHALL be saved with the research-started flag
set, like that of any turn whose report was delivered. The state SHALL be encoded as JSON before
the turn's one state write. When building or encoding it fails, the turn SHALL save the closing
state instead: an empty `messages`, the turn's `PrepState` with the research-started flag set, and
no failure flag. The closing state closes the conversation as the full state would, so the same
research cannot run again in it, and the turn SHALL still complete without an error.

Two outcomes of a failed step are accepted, because only a bug or a closed choice causes them.
When appending the report itself fails, the report does not reach the user, yet the saved state
closes the conversation. When the choice is closed, it takes no state, so the answer carries none:
through DIAL Chat the conversation stays open, and through StatGPT the report is not shown as a
report, because StatGPT then reads the answer as a clarification. A closed choice also refuses the
report's content, so the report most likely did not reach the user either.

#### Scenario: The files bucket cannot be resolved at the final save

- **WHEN** research delivered its report and resolving the DIAL files bucket for the transcript's
  images then raises
- **THEN** the turn SHALL end without a protocol error, and its state SHALL be saved with each image
  replaced by its placeholder and the research-started flag set

#### Scenario: The full state cannot be saved after the report

- **WHEN** research delivered its report and building or encoding the turn's full state then
  raises
- **THEN** the turn SHALL save the closing state, SHALL end without a protocol error, and SHALL
  record the failed save once (**logging-policy**)
- **AND** the next request in that conversation SHALL be refused as a conversation whose report was
  delivered, so no research runs and no snapshot is resumed
- **AND** through StatGPT, Deep Research's answer SHALL carry a state whose research-started flag is
  set, so StatGPT shows the report to the user

#### Scenario: An unexpected failure in the citation step

- **WHEN** the report loop settled a draft and the citation step raises outside its own passes
- **THEN** the turn SHALL deliver the draft as the review settled it, and SHALL end without a
  protocol error

#### Scenario: A delivered report through StatGPT

- **WHEN** a turn called through StatGPT delivers its report, and the citation step or the image
  upload of the final save then fails
- **THEN** Deep Research's answer SHALL end without an error and carry a state whose
  research-started flag is set, so StatGPT shows the report to the user

### Requirement: A turn's one state write falls back in a fixed order

The DIAL SDK allows one state write per turn. Every turn that persists a state SHALL save exactly
one of the four states below with that write. Before the write, the app SHALL encode the
candidate state as UTF-8 JSON, the strictest way the SDK sends a response, refusing `NaN`,
infinities and text that is not valid UTF-8. A candidate that cannot be built or
encoded SHALL fall back to the next candidate of its turn, and the write SHALL be made only with a
candidate that encoded. When the last candidate fails too, or the choice is closed, the turn
SHALL persist no state.

| State | `messages` | `preparation` | Snapshot | Failure flag |
|---|---|---|---|---|
| Full state | the turn's whole transcript | the turn's `PrepState` as it is | no | no |
| Closing state | empty | the turn's `PrepState` as it is, research started | no | no |
| Snapshot state | the turn's preparation messages | the turn's `PrepState`, plan-approved and research-started reset | yes | yes |
| Failure record | empty | the `PrepState` the request's history held when the turn started | no | yes |

| Turn | Candidates, in order |
|---|---|
| Its report was written | the full state, then the closing state |
| It completed without research | the full state; when that fails, the turn fails and saves the failure record |
| Its research failed after the graph streamed state | the snapshot state, then the failure record |
| It failed in any other way | the failure record |

#### Scenario: A preparation-only turn whose own save fails

- **WHEN** a turn presents a plan without starting research, and its full state cannot be built
- **THEN** the turn SHALL persist the failure record, and SHALL deliver the save's failure as its
  error

#### Scenario: A candidate that cannot be encoded leaves the write unused

- **WHEN** a candidate state holds a value that JSON cannot encode, or a `NaN`
- **THEN** the app SHALL NOT call the state write with it, so the next candidate can still be saved

### Requirement: Failures a resume would repeat save a snapshot that is never resumed

Two failure classes SHALL save their snapshot marked not resumable: a model call that rejected its
input, and an exhausted research step budget. A resume would replay the run's input and state and
likely fail the same way. The snapshot is kept so that a developer can see what happened during the
run when the client hides Deep Research's stages. It SHALL never be resumed, and research on a later
turn SHALL start from the beginning. The classes are this list, not the protocol error's retryable
classification: an authentication failure or a bug is not retryable, yet a resume succeeds once it
is fixed. These classes are excluded from resuming on purpose; any later retry or resume mechanism
SHALL exclude them too, unless it changes what is re-sent.

#### Scenario: The context outgrew the model

- **WHEN** a research model call is rejected with the error code `context_length_exceeded` or
  `truncate_prompt_error`
- **THEN** the turn SHALL save a snapshot marked not resumable and SHALL deliver the error, because
  the research transcript only grows and a resumed call would send at least the same messages again

#### Scenario: A content filter rejected the call

- **WHEN** a research model call is rejected with the error code `content_filter`
- **THEN** the turn SHALL save a snapshot marked not resumable and SHALL deliver the error
- **AND** this SHALL hold even when the filter judged the model's output, which a new attempt might
  pass: the code does not say which side the filter judged, and that resume is knowingly given up

#### Scenario: The model rejected the request

- **WHEN** a research model call fails with HTTP 400, 413 or 422, for example because a tool result
  carries an image the model cannot accept
- **THEN** the turn SHALL save a snapshot marked not resumable and SHALL deliver the error

#### Scenario: The step budget ran out

- **WHEN** a research-agent iteration exhausts the research step budget
- **THEN** the turn SHALL save a snapshot marked not resumable and SHALL deliver the step-budget
  error
- **AND** no later turn SHALL re-enter that iteration, which would hand an agent that did not finish
  its whole transcript and a fresh step budget

#### Scenario: A wrapped rejection is still recognized

- **WHEN** a context-length rejection reaches the turn wrapped in a concurrency runtime's container
- **THEN** it SHALL be classified as the rejection it holds, as the error resolution unwraps it, and
  the turn's snapshot SHALL be marked not resumable

#### Scenario: Failures a resume can get past save a resumable snapshot

- **WHEN** a research model call fails with a quota 429, an HTTP 502 or 503, or a timeout
- **THEN** the turn SHALL save a resumable snapshot, because the same call can succeed once the
  quota resets or the upstream recovers

#### Scenario: A resumed run that hits such a failure does not replay the earlier snapshot

- **WHEN** a run failed with a quota error and saved a snapshot, a later turn resumed from it and
  failed with `context_length_exceeded`, and the user then asks to continue
- **THEN** the failed resumed turn SHALL have saved a snapshot marked not resumable, which is now
  the latest snapshot in the history; research SHALL start from zero, and the turn SHALL show the
  "[DEBUG] existing snapshot discarded" stage with the reason that the snapshot is not resumable

### Requirement: A failed research turn persists the snapshot beside a reset PrepState

The state a failed research turn writes when it saves a snapshot SHALL carry four parts. Under
`messages` it holds only the turn's preparation messages. Under `preparation` it holds the turn's
`PrepState`, with the plan-approved and research-started flags reset and the query, the plan and the
plan id kept. Under a key of its own it holds the snapshot. It also carries the failure flag
(**Every failed turn records that it failed**). The research transcript SHALL be stored only in the
snapshot.

#### Scenario: The next turn is not refused

- **WHEN** a message arrives on a conversation whose latest state was written by a failed research
  turn
- **THEN** the app SHALL run the preparation agent for it, and SHALL NOT refuse it as a
  conversation whose research was already handed off

#### Scenario: Preparation never receives the research transcript

- **WHEN** a turn follows a failed research turn
- **THEN** the preparation agent's history SHALL contain the failed turn's preparation messages and
  the failed-turn note, and none of the failed run's research transcript or its images

#### Scenario: A successful turn carries no snapshot

- **WHEN** a turn completes, with or without research
- **THEN** its state SHALL carry no snapshot and no failure flag, and no earlier snapshot SHALL be
  copied into it

### Requirement: The snapshot holds what a resumed run needs

A snapshot SHALL hold: its format version; the plan id that was current when research started;
whether it may be resumed; the resume point; the research transcript; the research graph's
channels; and the turn's data-query records. The resume point is named in the app's own terms
(research, research review, report, report review), not by graph node. The channels are the query,
the plans, the iteration count, the latest draft and its number, the revision instruction and the
revision-failed flag.

#### Scenario: Images are stored as file URLs

- **WHEN** the research transcript carries base64 image blocks at the time the snapshot is saved
- **THEN** each image SHALL be uploaded to DIAL files as for any persisted state
  (**dial-agent-with-mcp**), and the snapshot SHALL hold its URL and no image bytes

#### Scenario: Data-query records survive a client's chunk merge

- **WHEN** the turn captured data-query records, one of whose server elements holds a list of
  objects that carry an `index` key, and the client rebuilds the streamed failed answer with the
  DIAL SDK's chunk merge before sending it back
- **THEN** the snapshot SHALL hold the records as one JSON-encoded string, and the records SHALL
  read back unchanged. The SDK's chunk merge re-slots any list of objects that carry an `index` key
  and deletes the key, but it does not reach inside a string

### Requirement: A snapshot keeps the progress inside a research iteration

When the failure happens while research-agent runs, the snapshot's transcript SHALL be
research-agent's message list after its last completed model call or tools round. A trailing model
message whose tool calls have no results yet SHALL be left out. A resume therefore repeats at most
the agent turn that failed: its model call, and also its tools round when the failure came during
that round.

#### Scenario: Failure at a model call

- **WHEN** research-agent completed two model calls and both tools rounds, and its third model call
  fails
- **THEN** the snapshot's transcript SHALL end with the second tools round's results, and its resume
  point SHALL be research

#### Scenario: Failure during a tools round

- **WHEN** a research-agent model call requested tool calls and the run fails before all their
  results arrived
- **THEN** the snapshot's transcript SHALL leave out the model message that requested those tool
  calls, so the resumed run makes that model call again

#### Scenario: A new iteration never uses the previous iteration's progress

- **WHEN** research-agent fails in iteration N before it completed any model call
- **THEN** the snapshot's transcript SHALL be the research graph's own transcript, which ends with
  research-review's instruction for iteration N, and SHALL NOT be research-agent's message list
  from iteration N − 1

### Requirement: The resume point is the node that was running

The snapshot's resume point SHALL name the node that was running when the failure happened. Its
channels SHALL be the research graph's state as that node received it.

#### Scenario: research-review fails

- **WHEN** research-review fails after research iteration 2
- **THEN** the snapshot's resume point SHALL be research review, and its iteration count SHALL be 2

#### Scenario: The report node fails on the first draft

- **WHEN** the report node fails while it writes draft 1
- **THEN** the snapshot's resume point SHALL be report, and it SHALL hold no draft and
  draft number 0

### Requirement: A snapshot that cannot be built does not hide the failure

When building, encoding or saving the snapshot raises, its image upload included, the turn SHALL
drop the snapshot, persist only its failure record (**Every failed turn records that it failed**), and
deliver the original error, not the snapshot's. The snapshot's failure SHALL be recorded once
(**logging-policy**) and SHALL cost only the resume. A snapshot too large for DIAL Core is not
caught this way: saving it does not raise, and DIAL Core rejects a later request that carries it.
The app has no size check for it.

#### Scenario: The upload bucket cannot be resolved

- **WHEN** research-agent fails with a quota error and resolving the DIAL files bucket for the
  snapshot's images then raises
- **THEN** the turn SHALL persist its failure record without a snapshot and SHALL deliver the quota
  error, not the bucket error

### Requirement: A failed-turn note follows every failed turn

The preparation agent's history SHALL contain one fixed note, as a system message, directly after
every assistant message whose state carries the failure flag. The clarity and approval checks SHALL
receive the same note as a `System note:` line at that position.

#### Scenario: What the note says

- **WHEN** the note is rendered
- **THEN** it SHALL say two things: the previous user message failed with an error before its answer
  finished; and if the user asks to continue a research whose plan they had approved, the agent
  calls `approve_plan`, then `start_research`, and otherwise handles the user's request as usual
- **AND** it SHALL NOT say whether research progress was saved, and SHALL NOT carry the error text,
  the error reference or any other internal detail

#### Scenario: The user asks what happened

- **WHEN** the user's message after a failed turn asks what happened to the request
- **THEN** the preparation agent SHALL be able to answer from the note that the request failed with
  an error, research SHALL NOT start, and a later request to continue SHALL still resume when the
  latest snapshot is a resumable snapshot of the current plan

#### Scenario: The note keeps its position

- **WHEN** several turns follow a failed turn
- **THEN** on each of them the note SHALL appear directly after the failed turn's messages, so the
  history before it stays the same from turn to turn

#### Scenario: A failure in preparation gets the note

- **WHEN** the approval check fails with a quota error, and the user then writes "continue"
- **THEN** the preparation agent's history SHALL hold the failed turn's visible answer text, then
  the note, then the user's message

### Requirement: A request to continue resumes research in the same turn

When the user asks to continue after a failed research run, the preparation flow SHALL be able to
approve the recorded plan and start research in that same turn, without presenting the plan to the
user again. The approval check accepts the request as approval of the plan the user approved before
the failure (**clarification-and-plan-alignment**).

#### Scenario: "continue" after a quota reset

- **WHEN** the user writes "continue" after a failed research run, with the query and the plan
  unchanged
- **THEN** in that turn `approve_plan` SHALL approve the recorded plan, `start_research` SHALL pass
  its gate, and research SHALL resume from the snapshot, with no plan presented in between

### Requirement: Research resumes only from the latest resumable snapshot of the current plan

When research starts in a turn, the app SHALL take the latest assistant message in the history that
carries a snapshot. It SHALL resume from that snapshot only when the snapshot's plan id equals the
current plan id and the snapshot is not marked not resumable; otherwise research SHALL start fresh.
Turns between the failure and the resume, failed turns that saved no snapshot among them, SHALL NOT
hide the snapshot.

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

### Requirement: A plan recorded without a plan id gets one when research starts

When research starts on a plan that carries no plan id, the app SHALL give it a fresh plan id
before research runs. A plan has none when it was recorded before plan ids existed. A failure of
that new research can then be resumed.

#### Scenario: A plan recorded before the upgrade

- **WHEN** a plan recorded by an earlier release is approved and research starts, and that research
  fails
- **THEN** the persisted `PrepState` and the snapshot SHALL carry the same fresh plan id, and a
  request to continue SHALL resume from the snapshot

### Requirement: A resumed run re-enters the graph at the node that failed

A resumed run SHALL start the research graph at the node the snapshot's resume point names, with
every channel filled from the snapshot. It SHALL continue the research loop and the report loop from
where they stopped, never from their start. The nodes SHALL behave as on any run, and none of them
can tell a resumed run from a fresh one.

#### Scenario: Resuming inside a research iteration

- **WHEN** the snapshot was saved inside research-agent in iteration N
- **THEN** research-agent SHALL continue iteration N after its last completed agent turn, the
  iteration count SHALL still read N − 1 until the iteration ends, and no tool call recorded in the
  snapshot SHALL run again

#### Scenario: Resuming at research-review

- **WHEN** the snapshot's resume point is research review after iteration N
- **THEN** research-review of iteration N SHALL run first, with no research-agent call before it

#### Scenario: Resuming at the report node

- **WHEN** the snapshot's resume point is report and it holds no draft
- **THEN** the report node SHALL write draft 1 from the saved transcript

#### Scenario: Resuming at report-review

- **WHEN** the snapshot's resume point is report review and it holds draft N
- **THEN** report-review round N SHALL run over draft N, and drafts 1 to N SHALL NOT be
  written again

#### Scenario: The caps count the work done before the failure

- **WHEN** the snapshot records iteration count N and draft number M
- **THEN** the research iteration cap and the report version budget SHALL apply to N and M as if the
  run had not failed

#### Scenario: A resumed turn shows no stage for a tool call it did not run

- **WHEN** research-agent ends its iteration on a resumed run
- **THEN** the turn SHALL show a tool-call stage, and write a tool-call record, only for tool calls
  made in this turn, never for those recorded in the snapshot

#### Scenario: A resumed turn that completes persists like any research turn

- **WHEN** a resumed run delivers its report
- **THEN** the turn's state SHALL carry the whole research transcript, the snapshot's and this
  turn's, with the report, and a `PrepState` whose research-started flag is set; it SHALL carry no
  snapshot and no failure flag

### Requirement: A snapshot's images are downloaded before the resumed run starts

Before a resumed run starts, the app SHALL download every image that the snapshot's transcript
references. It SHALL try each download up to three times, with exponential backoff starting at one
second. An image that still cannot be downloaded SHALL fail the turn. The placeholder that history
reconstruction puts in place of an image it cannot download is not used for a snapshot.

#### Scenario: A download fails once

- **WHEN** a snapshot image's first download fails and its second succeeds
- **THEN** the resumed run SHALL start with that image in place

#### Scenario: A snapshot image no longer exists

- **WHEN** a snapshot image's download answers 404
- **THEN** it SHALL NOT be retried, and the turn SHALL be refused as for a snapshot that cannot be
  read: the "an error on our side prevents resuming" message, and only the failure record persisted

#### Scenario: A download keeps failing

- **WHEN** a snapshot image cannot be downloaded in three attempts, for a reason other than a 404
- **THEN** the turn SHALL fail with the retryable message that the saved research progress could not
  be loaded (**dial-agent-with-mcp**), SHALL save no new snapshot, and the snapshot it started from
  SHALL stay the latest one, so a later request to continue can try again

### Requirement: The snapshot format is versioned and read tolerantly

A snapshot SHALL carry a format version. Its reader SHALL ignore fields it does not know. Where a
field is absent and has a default, the reader SHALL use the default, so a change that only adds
such fields keeps the version. A change that a reader of the current version could not read SHALL
bump the version. The plan id, the resumable mark and the version form a header that every format
version SHALL keep, so that any release can tell whether a snapshot is to be resumed before it reads
the rest.

#### Scenario: A field added by a later release

- **WHEN** a snapshot of the current version carries a field this code does not know
- **THEN** the snapshot SHALL be read, and the field ignored

### Requirement: A matching snapshot that cannot be read fails the turn

The app SHALL compare plan ids, then read the resumable mark, before it reads the rest of the
snapshot. A matching resumable snapshot whose version this code does not read SHALL fail the turn
with a non-retryable error: the research was saved by a different version and cannot be resumed. A
matching resumable snapshot that cannot be read for any other reason SHALL fail the turn with a
non-retryable error: an error on our side prevents resuming it. Neither refusal saves a snapshot:
the turn persists only its failure record, which keeps the plan id.

#### Scenario: A snapshot saved by a different version

- **WHEN** research starts with a matching resumable snapshot whose format version this code does
  not read, for example after a release changed the format, or after a rollback
- **THEN** the turn SHALL fail with the "saved by a different version and cannot be resumed"
  message, which tells the user to start a new conversation (**dial-agent-with-mcp**)

#### Scenario: A snapshot that fails to read

- **WHEN** research starts with a matching resumable snapshot of a known version that fails
  validation or whose transcript cannot be decoded, or with a snapshot whose plan id cannot be read
  or whose resumable mark is not a boolean
- **THEN** the turn SHALL fail with the "an error on our side prevents resuming" message, which
  tells the user to start a new conversation, and the turn's error record SHALL carry the stack
  trace

#### Scenario: A snapshot that will not be resumed is discarded, not refused

- **WHEN** research starts with a snapshot whose plan id differs from the current one, or which is
  marked not resumable, whatever its version or contents
- **THEN** research SHALL start fresh, and the snapshot SHALL be discarded without being
  read further

#### Scenario: The refusal repeats

- **WHEN** a turn was refused for a snapshot that cannot be read, and the user asks to continue
  again
- **THEN** the turn SHALL be refused again in the same way, because the refusal saved no snapshot
  and kept the plan id, so the same snapshot is still the latest one and still matches

### Requirement: The turn shows whether it reused a snapshot

When research starts and the history holds a snapshot, the turn SHALL show one stage. It is
"[DEBUG] reusing snapshot" when the run resumes from the snapshot, and "[DEBUG] existing snapshot
discarded" when the plan ids differ or the snapshot is marked not resumable. Both stages SHALL carry
only ids, names and counts. They SHALL always be emitted, because "[DEBUG]" is only part of the
title. No such stage SHALL be shown when no snapshot is found.

#### Scenario: A reused snapshot

- **WHEN** research resumes from a snapshot
- **THEN** the "[DEBUG] reusing snapshot" stage SHALL carry the snapshot's plan id, its resume
  point, its iteration count, the number of transcript messages, and the latest draft number
- **AND** for resume point research it SHALL also carry the number of agent turns the iteration had
  completed, and for resume point report review the report-review round

#### Scenario: A discarded snapshot

- **WHEN** research starts and the latest snapshot will not be resumed
- **THEN** the "[DEBUG] existing snapshot discarded" stage SHALL carry the snapshot's plan id, the
  current plan id, and the reason: the plan changed, or the snapshot is not resumable
- **AND** it SHALL carry the resume point the snapshot names only when that reads as a known resume
  point, because a discarded snapshot is not read past its header
