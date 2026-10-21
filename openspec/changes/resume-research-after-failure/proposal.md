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
  at, and the turn's data-query records. Any exception that ends the research graph saves one: a
  quota 429, an upstream limit or outage that reaches the app as a 502 or a 503, an app timeout, a
  bug. A failure in preparation or in the delivery step saves nothing, as today. A cancellation
  (Stop, a client disconnect, DIAL Core's idle timeout) and a killed pod save nothing either, because
  the connection is gone by the time the turn ends.
- **Failures a resume would repeat save no snapshot, on purpose.** A resume re-sends the failed run's
  input, so two classes would fail again on every "continue". The first is the model rejecting the
  input: the context exceeded, a content filter, or a model 400, 413 or 422. The second is an
  exhausted research step budget. Such a failed turn persists only the reset `PrepState`, with its
  plan id cleared, so no earlier snapshot of the plan can match and the next research starts fresh.
  The spec names both classes as a standing rule, so later retry or resume work does not include
  them by default.
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
- **Resuming goes through the normal preparation turn.** Both the preparation agent and the
  approval check see a fixed failed-turn note after the failed answer: the research run failed,
  nothing was delivered, its progress was saved, and the approval was reset. When the user asks to
  continue, the `approve_plan` reviewer accepts that as approval of the plan the user approved
  before the failure, and `start_research` starts research in the same turn without showing the
  plan again.
- **Research re-enters at the node that failed.** When research starts, the app searches the
  history for the latest snapshot. If its id matches, the graph starts at that node over the saved
  channels: research-agent, research-review, report or report-review. A new conditional edge from
  `START` makes this possible, and the nodes themselves do not change. Before the graph starts, the
  snapshot's images are downloaded, with up to three attempts each. An image that still cannot be
  downloaded fails the turn with a retryable "could not be loaded" message and keeps the snapshot.
  An image whose file is gone (404) is refused like an unreadable snapshot (next bullet). A resume
  needs a streaming client: on a non-streaming request the SDK drops a failed turn's state.
- **A snapshot that cannot be read is refused.** A snapshot carries a format version, and the
  reader ignores fields it does not know. A matching snapshot of an unknown version fails the turn
  with a non-retryable error saying it was saved by a different version and cannot be resumed. A
  matching snapshot that fails validation fails the turn with a non-retryable error saying that an
  error on our side prevents resuming. Both errors tell the user to start a new conversation.
  A failed turn whose snapshot belongs to another plan gets a second fixed note that says its
  progress cannot be continued, so the note never promises progress that can no longer be resumed.
- **The resume is visible.** When research starts and a snapshot is found, the turn shows a
  "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage. The facts it shows go
  into one INFO record as well. Saving a snapshot writes one INFO record, and a snapshot that could
  not be built writes one WARNING. The turn still raises the original error.
- **Data-query records are stored as one JSON string inside the snapshot.** The DIAL SDK's chunk
  merge, which a client may use to rebuild a streamed answer before sending it back, re-slots any
  list of dicts whose elements carry an `index` key. These records are kept whole as the data server sent them, and they are the first server
  `_meta` data any state persists. A string is out of the merge's reach.
- **Specs are brought in line.** They currently say a failed turn persists nothing, that research
  runs only within the turn that launched it, and that data-query records last one turn. The stale
  "1 MB request body" statement about persisted state is corrected.

Unchanged: the report revision and the two report reviews keep absorbing their own failures,
quota errors included, and deliver the latest draft.

## Capabilities

### New Capabilities

- `research-resume`: saving research progress when the research graph fails, and resuming it on a
  later turn. It covers the snapshot's contents and format version, when it is saved and what the
  failed turn persists, the failures a resume would repeat and that therefore save no snapshot, the
  failed-turn note, the history search and the plan-id match, where the
  resumed run re-enters, the image downloads, the errors for a snapshot that cannot be read, and
  the stages that show whether a snapshot was reused.

### Modified Capabilities

- `dial-agent-with-mcp`: a failed research turn persists state before the error is raised; the
  research-already-handed-off refusal applies once the report was delivered; two new turn-aborting
  conditions for a snapshot that cannot be read; history reconstruction adds the failed-turn note
  and never reads the snapshot; the stale 1 MB statement about persisted image content.
- `research-execution`: the graph's entry from `START` is research-agent on a fresh run and the
  node the snapshot names on a resumed run; research that failed may continue in a later turn.
- `clarification-and-plan-alignment`: `PrepState` carries a `plan_id`; `update_plan` renews it;
  `approve_plan` accepts a request to continue after a failed run; a failed research turn persists
  `PrepState` with approval and research-started reset; the refusal after research applies once
  the report was delivered; the preparation agent and both checks receive the failed-turn note.
- `report-citations`: the data-query records of a failed run are restored on its resume, so a
  citation of a query from before the failure still resolves.
- `logging-policy`: the INFO records for a saved, skipped, reused and discarded snapshot, and the
  WARNING for a snapshot that could not be built.

## Impact

Code:

- `src/dial_deep_research/app/completion.py`: catch a research failure; persist the snapshot with
  the reset `PrepState` and the preparation messages, or, for a failure a resume would repeat, only
  the reset `PrepState` with its plan id cleared; then re-raise. Look up the snapshot when
  research starts, show the stage and log the record.
- `src/dial_deep_research/app/research/snapshot.py` (new): the snapshot model and its format
  version, the history search, the tolerant read and the two refusals, and building the resumed
  state.
- `src/dial_deep_research/app/research/runner.py`: add the `tasks` stream mode to learn the
  running node, keep the latest root and research-agent states, tell a graph failure from a
  delivery failure, build the snapshot, run from a resumed state, and count the snapshot's messages
  as already seen.
- `src/dial_deep_research/app/research/graph.py`: the conditional edge from `START` and its router.
- `src/dial_deep_research/app/research/state.py`: build the initial state from a snapshot.
- `src/dial_deep_research/app/history.py`: `PrepState.plan_id`, the snapshot's state key, and the
  failed-turn notes in `reconstruct_history` after every assistant message that carries a snapshot;
  `reconstruct_history` takes the loaded plan id.
- `src/dial_deep_research/app/preparation/runner.py`: pass the loaded `PrepState.plan_id` to
  `reconstruct_history`.
- `src/dial_deep_research/app/preparation/tools.py`: renew `plan_id` in `update_plan` and clear it
  in `update_query`, give a legacy plan without an id one in `start_research`, and render the
  failed-turn note in `_format_conversation`.
- `src/dial_deep_research/app/preparation/prompts.py`: the two failed-turn notes' texts, and the
  `PLAN_REVIEW_SYSTEM` paragraph on a request to continue after a failed run.
- `src/dial_deep_research/app/error_resolution.py`: three app conditions: a snapshot of an unknown
  version and a snapshot that fails validation (both non-retryable), and a snapshot image that
  could not be downloaded (retryable). Also the predicate that says whether a failure is one a
  resume would repeat.
- `src/dial_deep_research/utils/image_attachments.py`: a download for snapshot images that
  retries, does not retry a 404, and raises a typed error; correct the stale 1 MB comment.

Tests: `tests/test_history_persistence.py`, `tests/test_preparation_tools.py`,
`tests/test_error_resolution.py`, `tests/test_image_attachments.py`, and a new
`tests/test_research_resume.py`: snapshot capture and round trip, entry at each node, the history
search, the plan-id match, the refusals, a real compiled graph resumed from a mid-iteration
snapshot, and the capture itself on a real compiled graph whose fake model fails mid-iteration.

Docs: `docs/architecture.md`, covering the turn structure, the failed-turn path and the research
graph's entry from `START`.

Systems and dependencies:

- No new environment variable, application property or package.
- Through DIAL Chat, the resume works as soon as this ships: DIAL Chat sends a failed answer back
  with its `custom_content.state`.
- Through StatGPT it also needs the StatGPT backend change in epam/statgpt-backend PR #763. That
  change keeps a failed Deep Research turn, with Deep Research's state, in its session, marked as
  failed. Without it StatGPT discards the state.
- A conversation grows by one research transcript for each failed attempt. Snapshots stay far
  below DIAL Core's 64 MiB request limit.
