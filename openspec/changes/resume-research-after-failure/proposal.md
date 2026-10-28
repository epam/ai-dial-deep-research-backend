## Why

When a research run fails midway, the turn persists nothing, so all the research done so far is
lost. The most common cause is the user's DIAL quota running out: tokens or cost per day, week or
month. When the user writes "continue" after the quota resets, research starts again from zero
and repeats every tool call it already made. The user must be able to continue the same
conversation and have research pick up where it stopped.

## What Changes

- **A failed research turn saves a snapshot of the research progress.** It is written once, with
  the turn's one `set_state`, before the error is raised through the DIAL error protocol as today.
  The snapshot holds the research transcript, the research graph's channels, the node to re-enter
  at, whether it may be resumed, and the turn's data-query records. Any exception that ends the
  research graph after it streamed state saves one: a quota 429, an upstream limit or outage that
  reaches the app as a 502 or a 503, an app timeout, a bug. A cancellation (Stop, a client
  disconnect, DIAL Core's idle timeout) and a killed pod save nothing, because the connection is
  gone by the time the turn ends.
- **Every failed turn records that it failed.** Its state carries a failure flag under a key of its
  own. A failed turn without a snapshot, such as a failure in preparation or before the research
  graph streamed any state, persists an empty `messages` and the `PrepState` it started from, read
  again from the request. A failure while the application properties are fetched or validated
  persists nothing, as today. If the snapshot cannot be built or saved, the turn drops it and
  persists the failure record instead; the original error is always the one delivered.
- **Every state is checked before the turn's one write.** The SDK allows one state write per turn,
  and a state it cannot serialize uses that write up. So every state is encoded first, and a state
  that cannot be built or encoded falls back to a smaller one: a snapshot state to the failure
  record, and a delivered report's full state to a closing state.
- **A turn never fails once its report is written.** A report costs a whole research run. Once the
  report loop has settled a draft, every later step absorbs its own failure: the citation step,
  the annotations, the citation log record and the final save. A final save whose images cannot be
  uploaded saves placeholders instead, and the state still closes the conversation. A final save
  that cannot be built or encoded saves the closing state instead: an empty `messages` and the
  `PrepState` with research started, without a failure flag, so the same research can never run
  again in that conversation. Through StatGPT this decides whether the user gets the report at all,
  because StatGPT shows a report only when Deep Research's answer ends without an error.
- **Failures a resume would repeat save a snapshot that is never resumed.** A resume re-sends the
  failed run's input, so two classes would fail again on every "continue". The first is the model
  rejecting the input: the context exceeded, a content filter, or a model 400, 413 or 422. The
  second is an exhausted research step budget. Their snapshot is saved marked not resumable, so a
  developer can see what happened during the run, and the next research starts from the beginning.
  The spec names both classes as a standing rule, so later retry or resume work does not include
  them by default. Their error messages state what happened, without telling the user to shorten
  their messages or to start a new conversation.
- **Progress inside a research iteration is kept.** The runner keeps research-agent's message list
  after every model call and every tools round, so a resume repeats at most the agent turn that
  failed.
- **The failed turn leaves the conversation open.** It persists the turn's preparation messages
  and a `PrepState` with `plan_approved` and `research_started` reset. The existing check that
  refuses a conversation whose research already started (HTTP 409) therefore lets the next turn
  through. It now refuses only a conversation whose report was delivered.
- **A plan id ties a snapshot to one query and plan.** `PrepState` gets a `plan_id`. Every
  `update_plan` call sets a fresh one, and `update_query` clears it together with the plan. A
  snapshot is resumed only when its id equals the current `plan_id`, so any change to the query or
  the plan makes research start fresh.
- **Resuming goes through the normal preparation turn.** The preparation agent and both checks see
  one fixed failed-turn note after every failed answer: the previous user message failed before its
  answer finished, and if the user asks to continue a research whose plan they approved, the agent
  calls `approve_plan`, then `start_research`. The note says nothing about whether progress was
  saved. When the user asks to continue, the `approve_plan` reviewer accepts that as approval of
  the plan the user approved before the failure, and `start_research` starts research in the same
  turn without showing the plan again.
- **Research re-enters at the node that failed.** When research starts, the app searches the
  history for the latest snapshot. If its id matches and it may be resumed, the graph starts at
  that node over the saved channels: research-agent, research-review, report or report-review.
  Otherwise research starts from the beginning. A new conditional edge from `START` makes this
  possible, and the nodes themselves do not change. Before the graph starts, the snapshot's images
  are downloaded, with up to three attempts each. An image that still cannot be downloaded fails
  the turn with a retryable "could not be loaded" message, and the snapshot stays the latest one.
  An image whose file is gone (404) is refused like an unreadable snapshot (next bullet). A resume
  needs a streaming client: on a non-streaming request the SDK drops a failed turn's state.
- **A snapshot that cannot be read is refused.** A snapshot carries a format version, and the
  reader ignores fields it does not know. The plan id, the resumable mark and the version form a
  stable header, read in that order, so a snapshot of another plan or one marked not resumable is
  discarded before its version is checked. A matching resumable snapshot of an unknown version
  fails the turn with a non-retryable error saying it was saved by a different version and cannot
  be resumed. A matching resumable snapshot that fails validation fails the turn with a
  non-retryable error saying that an error on our side prevents resuming. Both errors tell the user
  to start a new conversation.
- **The resume is visible.** When research starts and a snapshot is found, the turn shows a
  "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage; the discarded one
  names the reason, a changed plan or a snapshot that is not resumable. The facts it shows go into
  one INFO record as well. Saving a snapshot writes one INFO record, and so does a failure record
  without a snapshot, with its reason. A snapshot or failure record that could not be saved writes
  one WARNING. The turn still raises the original error.
- **Data-query records are stored as one JSON string inside the snapshot.** The DIAL SDK's chunk
  merge, which a client may use to rebuild a streamed answer before sending it back, re-slots any
  list of dicts whose elements carry an `index` key. These records are kept whole as the data
  server sent them, and they are the first server `_meta` data any state persists. A string is out
  of the merge's reach.
- **Specs are brought in line.** They currently say a failed turn persists nothing, that research
  runs only within the turn that launched it, that a conversation whose research started is closed,
  and that data-query records last one turn. The stale "1 MB request body" statement about
  persisted state is corrected.

Unchanged: the report revision and the two report reviews keep absorbing their own failures,
quota errors included, and deliver the latest draft.

## Capabilities

### New Capabilities

- `research-resume`: saving research progress when the research graph fails, and resuming it on a
  later turn. It covers the snapshot's contents and format version, when it is saved, the failure
  record every failed turn persists, the failures a resume would repeat and whose snapshot is
  therefore never resumed, the failed-turn note, the history search and the plan-id match, where
  the resumed run re-enters, the image downloads, the errors for a snapshot that cannot be read,
  the stages that show whether a snapshot was reused, the rule that a turn never fails once its
  report is written, and the four states a turn's one state write can save, with the order in
  which they fall back.

### Modified Capabilities

- `dial-agent-with-mcp`: a failed turn persists a failure record, with a snapshot when its research
  run saved one, before the error is raised; the research-already-handed-off refusal applies once
  the report was delivered; three new turn-aborting conditions for a snapshot that cannot be read
  or loaded; history reconstruction adds the failed-turn note after every failed turn and never
  reads the snapshot; error texts that state what happened; every failure after the report is
  written counts as absorbed; a files bucket that cannot be resolved is handled like a failed
  upload; the stale 1 MB statement about persisted image content.
- `research-execution`: the graph's entry from `START` is research-agent on a fresh run and the
  node the snapshot names on a resumed run; research that failed may continue in a later turn.
- `clarification-and-plan-alignment`: `PrepState` carries a `plan_id`; `update_plan` renews it;
  `approve_plan` accepts a request to continue after a failed run; a failed research turn persists
  `PrepState` with approval and research-started reset, and any other failed turn the `PrepState`
  it started from; a delivered
  report whose full state cannot be saved persists a closing state without the transcript; the
  refusal after research applies once the report was delivered; the
  preparation agent and both checks receive the failed-turn note.
- `data-sources-discovery`: a conversation counts as handed off, and makes no data-sources call,
  only once its report was delivered.
- `report-citations`: the data-query records of a failed run are restored on its resume, so a
  citation of a query from before the failure still resolves.
- `logging-policy`: the INFO records for a saved, reused and discarded snapshot and for a failure
  record without a snapshot, the WARNING for a snapshot or failure record that could not be saved,
  and the WARNING for a step that fails after the report is written, which for the final save says
  what was saved instead.

## Impact

Code:

- `src/dial_deep_research/app/completion.py`: catch any failure of the turn after the 409 check;
  persist the snapshot with the reset `PrepState`, the preparation messages and the failure flag,
  or else the failure record (an empty `messages`, the `PrepState` read from the request, and the
  flag), each save inside its own `try`; then re-raise. The `try` starts after the 409 check. Every state is encoded before the
  turn's one `set_state`, and a state that cannot be built or encoded falls back to the next one.
  Once the report is written, a failed final save is logged, the closing state is saved instead,
  and the turn completes.
  Look up the snapshot when research starts, show the stage and log the record.
- `src/dial_deep_research/app/research/snapshot.py` (new): the snapshot model with its stable
  header (plan id, resumable mark, format version), the history search, the tolerant read and the
  two refusals, and building the resumed state.
- `src/dial_deep_research/app/research/runner.py`: add the `tasks` stream mode to learn the
  running node, keep the latest root and research-agent states, say whether the graph streamed any
  state, absorb every failure once the report loop settled a draft, build the snapshot, run from a
  resumed state, and
  count the snapshot's messages as already seen.
- `src/dial_deep_research/app/research/graph.py`: the conditional edge from `START` and its router.
- `src/dial_deep_research/app/research/state.py`: build the initial state from a snapshot.
- `src/dial_deep_research/app/history.py`: `PrepState.plan_id`, the snapshot's and the failure
  flag's state keys, and the failed-turn note in `reconstruct_history` after every assistant
  message that carries the failure flag.
- `src/dial_deep_research/app/preparation/tools.py`: renew `plan_id` in `update_plan` and clear it
  in `update_query`, give a legacy plan without an id one in `start_research`, and render the
  failed-turn note in `_format_conversation`.
- `src/dial_deep_research/app/preparation/prompts.py`: the failed-turn note's text, and the
  `PLAN_REVIEW_SYSTEM` paragraph on a request to continue after a failed run.
- `src/dial_deep_research/app/error_resolution.py`: three app conditions: a snapshot of an unknown
  version and a snapshot that fails validation (both non-retryable), and a snapshot image that
  could not be downloaded (retryable). The predicate that says whether a failure is one a resume
  would repeat, which marks a snapshot not resumable. The reworded texts for a context overflow, a
  content filter, a model 400, 413 or 422 and an exhausted step budget.
- `src/dial_deep_research/utils/image_attachments.py`: a download for snapshot images that
  retries, does not retry a 404, and raises a typed error; a files bucket that cannot be resolved
  gives every image of a turn's `messages` the upload-failure placeholder, logged once, while the
  snapshot's upload re-raises it so the snapshot is dropped; correct the stale 1 MB comment.

Tests: `tests/test_history_persistence.py`, `tests/test_preparation_tools.py`,
`tests/test_error_resolution.py`, `tests/test_image_attachments.py`, and a new
`tests/test_research_resume.py`: snapshot capture and round trip, entry at each node, the history
search, the plan-id match and the resumable mark, the failure record, the refusals, a real compiled
graph resumed from a mid-iteration snapshot, and the capture itself on a real compiled graph whose
fake model fails mid-iteration. `tests/test_error_resolution.py` also covers the reworded texts.

Docs: `docs/architecture.md`, covering the turn structure, the failed-turn path and the research
graph's entry from `START`.

Systems and dependencies:

- No new environment variable, application property or package.
- Through DIAL Chat, the resume works as soon as this ships: DIAL Chat sends a failed answer back
  with its `custom_content.state`.
- Through StatGPT it also needs the StatGPT backend change in epam/statgpt-backend PR #763. That
  change keeps a failed Deep Research turn, with Deep Research's state, in its session, and gives
  the Supreme Agent a neutral note about the failure. Without it StatGPT discards the state.
- A conversation grows by one research transcript for each failed research attempt. Through
  StatGPT every later answer repeats the whole session until the report is delivered, so many
  failures in one conversation can bring it to DIAL Core's 64 MiB request limit. This is accepted;
  there is no size check (design, Risks).
