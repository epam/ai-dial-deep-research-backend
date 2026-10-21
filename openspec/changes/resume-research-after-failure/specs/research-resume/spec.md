## Purpose

Saves a research run's progress when the run fails, most often because the user's DIAL quota ran
out, and lets a later turn of the same conversation continue that research where it stopped
instead of starting it again.

## ADDED Requirements

### Requirement: A research failure saves a snapshot of the research progress

When an exception ends a research run after `start_research` passed its gate, in the graph or in
the tool setup before it, the turn SHALL save a snapshot of the progress with its single state
write, then deliver the original error (**dial-agent-with-mcp**). Any kind counts (a quota error, an
upstream outage, a timeout, a bug), except a failure a resume would repeat (next requirement) and a
refusal of the snapshot being resumed.

#### Scenario: A quota error inside research-agent

- **WHEN** a research-agent model call raises `openai.RateLimitError` because DIAL Core answered
  429 for the user's daily token limit
- **THEN** the turn SHALL persist a snapshot and SHALL then deliver the error with DIAL Core's
  `display_message`, and the state SHALL reach the client ahead of the error chunk

#### Scenario: An upstream outage in research-review

- **WHEN** the research-review model call fails with an HTTP 502 from DIAL Core
- **THEN** the turn SHALL persist a snapshot and deliver the error, exactly as for a quota error

#### Scenario: A failure in preparation saves nothing

- **WHEN** the preparation agent's model call raises a quota error, before `start_research` passed
- **THEN** the turn SHALL persist no state, because there is no research progress to save

#### Scenario: A failure in the delivery step saves nothing

- **WHEN** the research graph finished and an exception escapes the delivery step that runs the
  citation step and appends the report
- **THEN** the turn SHALL persist no state and SHALL deliver the error

#### Scenario: A failed tool call does not end research

- **WHEN** a research tool call fails and is relayed to research-agent as an error tool result
  (**tool-call-fault-tolerance**)
- **THEN** research SHALL go on and no snapshot SHALL be saved for that failure

#### Scenario: A cancellation saves nothing

- **WHEN** the research run ends because the user pressed Stop, the client disconnected, DIAL
  Core's idle timeout closed the connection, or the pod was killed
- **THEN** no snapshot SHALL be saved, and research on a later turn SHALL start from zero
- **AND** this SHALL stand as an accepted limitation: the connection is gone by the time the turn
  ends, and the DIAL SDK allows one state write per turn, so the progress cannot be sent while
  research runs

#### Scenario: A non-streaming request carries no snapshot

- **WHEN** a research run fails on a non-streaming request
- **THEN** the client SHALL receive the error alone and no snapshot, because the DIAL SDK raises on
  the error chunk and drops the merged response, state included; a resume therefore needs a
  streaming client, which DIAL Chat and StatGPT both are

### Requirement: Failures a resume would repeat save no snapshot

Two failure classes SHALL save no snapshot: a model call that rejected its input, and an exhausted
research step budget. A resume would replay the run's input and state and likely fail the same way.
The turn SHALL persist an empty `messages` and its `PrepState` with approval, research-started and
plan id cleared, so no earlier snapshot can match. These classes are excluded on purpose; any later
retry or resume mechanism SHALL exclude them too, unless it changes what is re-sent.

#### Scenario: The context outgrew the model

- **WHEN** a research model call is rejected with the error code `context_length_exceeded` or
  `truncate_prompt_error`
- **THEN** the turn SHALL save no snapshot and SHALL deliver the error as today, because the
  research transcript only grows and a resumed call would send at least the same messages again

#### Scenario: A content filter rejected the call

- **WHEN** a research model call is rejected with the error code `content_filter`
- **THEN** the turn SHALL save no snapshot and SHALL deliver the error as today
- **AND** this SHALL hold even when the filter judged the model's output, which a new attempt might
  pass: the code does not say which side the filter judged, and that resume is knowingly given up

#### Scenario: The model rejected the request

- **WHEN** a research model call fails with HTTP 400, 413 or 422, for example because a tool result
  carries an image the model cannot accept
- **THEN** the turn SHALL save no snapshot and SHALL deliver the error as today

#### Scenario: The step budget ran out

- **WHEN** a research-agent iteration exhausts the research step budget
- **THEN** the turn SHALL save no snapshot and SHALL deliver the step-budget error, whose advice to
  narrow the request and start a new conversation stays true
- **AND** no later turn SHALL re-enter that iteration, which would hand an agent that did not finish
  its whole transcript and a fresh step budget

#### Scenario: A wrapped rejection is still recognized

- **WHEN** a context-length rejection reaches the turn wrapped in a concurrency runtime's container
- **THEN** it SHALL be classified as the rejection it holds, as the error resolution unwraps it, and
  the turn SHALL save no snapshot

#### Scenario: Failures a resume can get past still save a snapshot

- **WHEN** a research model call fails with a quota 429, an HTTP 502 or 503, or a timeout
- **THEN** the turn SHALL save a snapshot, because the same call can succeed once the quota resets
  or the upstream recovers

#### Scenario: A resumed run that hits such a failure does not replay the earlier snapshot

- **WHEN** a run failed with a quota error and saved a snapshot, a later turn resumed from it and
  failed with `context_length_exceeded`, and the user then asks to continue
- **THEN** the failed resumed turn SHALL have persisted the reset `PrepState` with its plan id
  cleared, so the earlier snapshot no longer matches; research SHALL start from zero with a fresh
  plan id, and the turn SHALL show the "[DEBUG] existing snapshot discarded" stage
- **AND** on that turn the earlier failed turn SHALL be followed by the not-resumable note, since its
  snapshot no longer belongs to the current plan

#### Scenario: The failed turn reads as a failed answer

- **WHEN** a turn follows a turn that failed with one of these classes
- **THEN** the preparation agent's history SHALL hold that turn's visible answer text, as for a
  failed turn before this capability, because its persisted `messages` is empty

### Requirement: A failed research turn persists the snapshot beside a reset PrepState

The state a failed research turn writes when it saves a snapshot SHALL carry three parts. Under `messages` it holds only
the turn's preparation messages. Under `preparation` it holds the turn's `PrepState`, with the
plan-approved and research-started flags reset and the query, the plan and the plan id kept. Under
a key of its own it holds the snapshot. The research transcript SHALL be stored only in the
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
- **THEN** its state SHALL carry no snapshot, and no earlier snapshot SHALL be copied into it

### Requirement: The snapshot holds what a resumed run needs

A snapshot SHALL hold: its format version; the plan id that was current when research started;
the resume point; the research transcript; the research graph's channels; and the turn's
data-query records. The resume point is named in the app's own terms (research, research review,
report, report review), not by graph node. The channels are the query, the plans, the iteration
count, the latest draft and its number, the revision instruction and the revision-failed flag.

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
channels SHALL be the research graph's state as that node received it. When the run fails before
the graph produced any state, the snapshot SHALL be built from the state the run started from. On
a fresh run that is the initial state. On a resumed run it is the snapshot the run started from,
saved unchanged, unless the failure is a refusal of that snapshot.

#### Scenario: research-review fails

- **WHEN** research-review fails after research iteration 2
- **THEN** the snapshot's resume point SHALL be research review, and its iteration count SHALL be 2

#### Scenario: The report node fails on the first draft

- **WHEN** the report node fails while it writes draft 1
- **THEN** the snapshot's resume point SHALL be report, and it SHALL hold no draft and draft number 0

#### Scenario: The research tools cannot be loaded on a fresh run

- **WHEN** an MCP server cannot be reached while the research tools load, before the graph starts
- **THEN** the snapshot SHALL hold the initial state: resume point research, and a transcript of the
  first iteration's instruction alone

#### Scenario: A resumed run fails before its graph starts

- **WHEN** a resumed run fails before its graph produced any state, for example because a snapshot
  image still could not be downloaded after three attempts
- **THEN** the turn SHALL save the snapshot it started from, unchanged

### Requirement: A snapshot that cannot be built does not hide the failure

When building or saving the snapshot raises, the turn SHALL persist no state and SHALL deliver the
original error, not the snapshot's. The snapshot's failure SHALL be recorded once
(**logging-policy**) and SHALL cost only the resume.

#### Scenario: The upload bucket cannot be resolved

- **WHEN** research-agent fails with a quota error and resolving the DIAL files bucket for the
  snapshot's images then raises
- **THEN** the turn SHALL persist no state and SHALL deliver the quota error, not the bucket error

### Requirement: A failed-turn note follows every failed research turn

The preparation agent's history SHALL contain a fixed note, as a system message, directly after
every assistant message carrying a snapshot. A snapshot whose plan id equals that of the turn's
loaded `PrepState` gets the resumable note; a snapshot of another plan gets the not-resumable note;
a snapshot whose plan id cannot be read gets none. The clarity and approval checks SHALL receive the
same note as a `System note:` line at that position.

#### Scenario: What the resumable note says

- **WHEN** the resumable note is rendered
- **THEN** it SHALL say four things: the research run that the previous user message started failed
  before it finished; nothing of that run was delivered to the user; its progress was saved, so
  research on the same query and plan can continue; and the plan's approval was reset, so continuing
  means calling `approve_plan`, then `start_research`
- **AND** it SHALL NOT carry the error text, the error reference or any other internal detail

#### Scenario: What the not-resumable note says

- **WHEN** the not-resumable note is rendered
- **THEN** it SHALL say that the research run the previous user message started failed before it
  finished, that nothing of it was delivered to the user, that its progress cannot be continued,
  and that research on the current query and plan starts from the beginning once the user approves
  the plan, by calling `approve_plan`, then `start_research`
- **AND** it SHALL NOT carry the error text, the error reference or the reason the progress cannot
  be continued

#### Scenario: The user asks what happened

- **WHEN** the user's message after a failed research turn asks what happened to the request
- **THEN** the preparation agent SHALL be able to answer from the note that the research run failed
  before a report and can continue, research SHALL NOT start, and a later request to continue SHALL
  still resume

#### Scenario: The note keeps its position

- **WHEN** several turns follow a failed research turn, with the plan unchanged
- **THEN** on each of them the note SHALL appear directly after the failed turn's messages, so the
  history before it stays the same from turn to turn

#### Scenario: A snapshot of an earlier plan gets the not-resumable note

- **WHEN** after a failed research run the user changed the plan, or a later failure a resume would
  repeat cleared the plan id
- **THEN** the failed turn's messages SHALL be followed by the not-resumable note, so the agent
  neither reads the turn's `start_research` hand-off as research still running nor is promised
  progress that can no longer be resumed

#### Scenario: A snapshot whose plan id cannot be read gets no note

- **WHEN** a failed turn's snapshot carries no readable plan id
- **THEN** history reconstruction SHALL add no note for it and SHALL NOT fail

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

### Requirement: Research resumes only from the latest snapshot of the current plan

When research starts in a turn, the app SHALL take the latest assistant message in the history that
carries a snapshot. It SHALL resume from that snapshot only when the snapshot's plan id equals the
current plan id; otherwise research SHALL start fresh. Turns between the failure and the resume
SHALL NOT hide the snapshot.

#### Scenario: A question between the failure and the resume

- **WHEN** the user asks what happened, gets an answer, and then asks to continue
- **THEN** research SHALL resume from the snapshot of the failed turn two answers back

#### Scenario: "continue" while the quota is still exhausted

- **WHEN** the user asks to continue while the quota is still exhausted, so the preparation turn
  fails and saves nothing, and later asks to continue again
- **THEN** the later turn SHALL resume from the snapshot of the original failed turn

#### Scenario: A changed query or plan starts fresh

- **WHEN** the user changes the query or the plan after a failed research run, so `update_query` or
  `update_plan` runs, and then approves the new plan
- **THEN** research SHALL start from zero, and the old snapshot SHALL be discarded

#### Scenario: A second failure during a resumed run

- **WHEN** a resumed run fails again, with a failure a resume can get past
- **THEN** the turn SHALL save a new snapshot, and the next request to continue SHALL resume from
  the new one

#### Scenario: No snapshot in the history

- **WHEN** research starts on a conversation with no snapshot in its history
- **THEN** research SHALL start fresh, as before this capability existed

### Requirement: A plan recorded without a plan id gets one when research starts

When research starts on a plan that carries no plan id, the app SHALL give it a fresh plan id
before research runs. A plan has none when it was recorded before plan ids existed, or when a
failure a resume would repeat cleared its id. A failure of that new research can then be resumed.

#### Scenario: A plan recorded before the upgrade

- **WHEN** a plan recorded by an earlier release is approved and research starts, and that research
  fails
- **THEN** the persisted `PrepState` and the snapshot SHALL carry the same fresh plan id, and a
  request to continue SHALL resume from the snapshot

#### Scenario: A plan whose id a carved-out failure cleared

- **WHEN** research starts on a plan whose id was cleared by a turn that exhausted the step budget
- **THEN** the plan SHALL get a fresh plan id, which no snapshot in the history carries

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
- **THEN** report-review round N SHALL run over draft N, and drafts 1 to N SHALL NOT be written again

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
  snapshot

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
  read: the "an error on our side prevents resuming" message, and no state persisted

#### Scenario: A download keeps failing

- **WHEN** a snapshot image cannot be downloaded in three attempts, for a reason other than a 404
- **THEN** the turn SHALL fail with the retryable message that the saved research progress could not
  be loaded (**dial-agent-with-mcp**), and SHALL save the snapshot it started from, unchanged

### Requirement: The snapshot format is versioned and read tolerantly

A snapshot SHALL carry a format version. Its reader SHALL ignore fields it does not know. Where a
field is absent and has a default, the reader SHALL use the default, so a change that only adds
such fields keeps the version. A change that a reader of the current version could not read SHALL
bump the version.

#### Scenario: A field added by a later release

- **WHEN** a snapshot of the current version carries a field this code does not know
- **THEN** the snapshot SHALL be read, and the field ignored

### Requirement: A matching snapshot that cannot be read fails the turn

The app SHALL compare plan ids before it reads the rest of the snapshot. A matching snapshot whose
version this code does not read SHALL fail the turn with a non-retryable error: the research was
saved by a different version and cannot be resumed. A matching snapshot that cannot be read for any
other reason SHALL fail the turn with a non-retryable error: an error on our side prevents resuming
it. Neither refusal persists state.

#### Scenario: A snapshot saved by a different version

- **WHEN** research starts with a matching snapshot whose format version this code does not read,
  for example after a release changed the format, or after a rollback
- **THEN** the turn SHALL fail with the "saved by a different version and cannot be resumed"
  message, which tells the user to start a new conversation (**dial-agent-with-mcp**)

#### Scenario: A snapshot that fails to read

- **WHEN** research starts with a matching snapshot of a known version that fails validation or
  whose transcript cannot be decoded, or with a snapshot whose plan id cannot be read
- **THEN** the turn SHALL fail with the "an error on our side prevents resuming" message, which
  tells the user to start a new conversation, and the turn's error record SHALL carry the stack
  trace

#### Scenario: A stale snapshot that cannot be read is discarded, not refused

- **WHEN** research starts with a snapshot whose plan id differs from the current one, whatever its
  version or contents
- **THEN** research SHALL start fresh, and the snapshot SHALL be discarded without being read further

#### Scenario: The refusal repeats

- **WHEN** a turn was refused for a snapshot that cannot be read, and the user asks to continue
  again
- **THEN** the turn SHALL be refused again in the same way, because the refusal persisted nothing

### Requirement: The turn shows whether it reused a snapshot

When research starts and the history holds a snapshot, the turn SHALL show one stage. It is
"[DEBUG] reusing snapshot" when the run resumes from the snapshot, and "[DEBUG] existing snapshot
discarded" when the plan ids differ. Both stages SHALL carry only ids, names and counts. They SHALL
always be emitted, because "[DEBUG]" is only part of the title. No such stage SHALL be shown when no
snapshot is found.

#### Scenario: A reused snapshot

- **WHEN** research resumes from a snapshot
- **THEN** the "[DEBUG] reusing snapshot" stage SHALL carry the snapshot's plan id, its resume point,
  its iteration count, the number of transcript messages, and the latest draft number
- **AND** for resume point research it SHALL also carry the number of agent turns the iteration had
  completed, and for resume point report review the report-review round

#### Scenario: A discarded snapshot

- **WHEN** research starts and the latest snapshot's plan id differs from the current one
- **THEN** the "[DEBUG] existing snapshot discarded" stage SHALL carry the snapshot's plan id, the
  current plan id and the resume point the snapshot names
