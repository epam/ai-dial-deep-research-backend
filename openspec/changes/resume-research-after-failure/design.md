## Context

See `proposal.md` (Why) for the motivation. This section covers only the current mechanics the
design builds on.

**How a turn persists today.**

- `DeepResearchCompletion._run_turn` (`app/completion.py`) rebuilds `PrepState` from the latest
  assistant message that carries a state (`load_last_prep_state`, `app/history.py`).
- It runs the preparation agent. When `start_research` fires, it runs `ResearchRunner.run`
  (`app/research/runner.py`) in the same turn.
- At the end of a successful turn, `_persist` → `create_dial_state` uploads base64 images
  (`upload_image_blocks`, `utils/image_attachments.py`), then calls `choice.set_state` once with
  `{messages, preparation}`.
- A failed turn persists nothing. `ResearchRunner.run` closes its activity stage and re-raises, and
  `run_logged_turn` (`app/turn_lifecycle.py`) resolves the exception through `raise_dial_error`.
- The 409 refusal in `_run_turn` reads only `prep_state.research_started`.

**What the runner sees.**

- `ResearchRunner.run` streams the graph with `stream_mode=["updates", "values"]`,
  `subgraphs=True`, `version="v2"`. It keeps the latest root `values` part as the transcript and
  dedupes stages through `_seen_ids`.
- research-agent is a compiled `create_agent` graph, used directly as a node. One run of it is one
  research iteration.
- `IterationCounterMiddleware.after_agent` increments `research_iteration` only when an iteration
  ends.
- The graph has no checkpointer (`app/research/graph.py`).

**State held outside the graph.**

- `DataQueryStore` (`app/research/data_queries.py`) is filled by a tool-call interceptor and lives
  only in memory. The transcript cannot rebuild it, because the MCP adapter drops `_meta` before a
  tool message exists.
- `CitationLookups` is a cache, refilled on any turn.
- The image budget and the failed-tool repeat allowance are recomputed from the messages on every
  model call. No middleware keeps hidden state.

**Platform facts the design relies on.**

- **One state write per turn.** `aidial_sdk` 0.32.0 raises `Trying to set "state" twice` on a
  second `Choice.set_state` (`aidial_sdk/chat_completion/choice.py`). On an exception, the SDK sends
  the error chunk after the chunks already sent, so a state set before the raise reaches the client.
  Verified live through DIAL Core and DIAL Chat 1.2.4.
- **DIAL Chat keeps the failed answer and its state.** On the next message, DIAL Chat sends the
  failed answer back with its `custom_content.state`. Verified live.
- **"Try again" drops the failed answer.** DIAL Chat's "Try again" drops the failed answer and its
  state, then re-sends the previous user message. Verified live.
- **A quota error is an `openai.RateLimitError`.** DIAL Core answers 429 for a quota error, with a
  `display_message` such as "You've exceeded your daily token limit". The OpenAI client retries it
  three times, then raises `openai.RateLimitError`. A cost limit takes the same path. Verified live.
- **An upstream Azure limit cannot be told from an outage.** It reaches the app as a 502 or a 503
  (`openai.InternalServerError`), exactly as an upstream outage does. Read in DIAL Core's source.

**Proof of concept.** A throwaway proof of concept on this code base, run on the local stack, showed
the approach end to end, directly and through StatGPT with its companion change:

- Research-agent continued from a mid-iteration snapshot, and none of the snapshot's tool calls ran
  again.
- Failures in research-review and in report draft 1 resumed at those nodes.
- "continue" took the one-turn path with the failed-turn note.
- The history search found a snapshot across a turn in between.
- A changed query discarded the snapshot.

Its two defects shaped decisions D16 and D14 below:

- Snapshot tool calls produced 0.00 s stages again.
- With an earlier note wording, the agent skipped `approve_plan`.

## Goals / Non-Goals

**Goals:**

- A failed research turn loses at most the agent turn or node that failed, and the next request to
  continue picks up from there in one turn.
- Nothing is written while research runs. The snapshot uses the turn's one existing state write.
- The snapshot is the app's own data, so a redeploy that does not change the snapshot format leaves
  a pending resume working.
- No node of the research graph changes. A resumed run is a normal run seeded differently.
- The preparation agent and both preparation checks learn of the failure only from the fixed
  note. They never receive the research transcript or any error text.

**Non-Goals:**

Each item below is out of scope for this change and is planned, where it is planned at all, as its
own later change.

- **Saving on a cancellation or a killed pod.** Stop, a client disconnect, DIAL Core's idle timeout
  and a pod restart save nothing. Covering them needs state sent while research runs, which the
  SDK's one-write rule forbids today.
- **Uploading images as they arrive.** Images are uploaded at save time, as today. Uploading during
  the run, with a hash-to-URL map, would make a failed turn's save fast.
- **Resuming the delivery step.** A failure in the delivery step saves nothing. It makes no model
  call, and the citation step absorbs its own failures, so only a bug reaches it.
- **Letting the report loop re-raise.** The report revision and the two report reviews keep
  absorbing every failure, quota errors and Azure limits included. Whether they should re-raise is
  a product decision.
- **Not retrying a quota 429.** The OpenAI client's three retries of a day or month limit only add
  delay (`max_retries=3`, `utils/llm.py`).
- **Keeping the snapshot through "Try again".** For example, a DIAL file keyed by the conversation.
- **A quota error on an MCP call.** `ToolFailureMiddleware` relays it to research-agent as an error
  tool result, so research goes on until the next model call fails. Whether such a call should stop
  research at once is decided after a probe.
- **Resuming a run whose context outgrew the model**, for example by shrinking the transcript
  before re-sending it. D20 saves no snapshot for such a failure.
- **Partial recovery of a snapshot this code cannot read, and migrations between snapshot
  versions.**
- **A guard against a state too large for DIAL Core** (64 MiB by default).
- **DIAL Chat 0.x.**
- **Resuming for a non-streaming caller.** On a non-streaming request, the SDK drops a failed turn's
  state with the merged response, so there is nothing to resume from. DIAL Chat and StatGPT both
  stream.
- **Driving a resume from `scripts/send_conversation.py`.** It writes its messages file only after
  a successful turn, so a failed answer's state never reaches a `continue`. The manual check goes
  through DIAL Chat (Migration Plan).
- **The StatGPT backend change.** It is tracked in epam/statgpt-backend PR #763, which keeps the
  failed turn with Deep Research's state, adds the Supreme Agent's note, reads the session from
  the latest answer that carries one, and logs only the state's keys and size.

## Decisions

### D1. Write the snapshot once, at the end of the failed turn

The coordinator catches the research failure, writes the state with the turn's only `set_state`,
then re-raises. Nothing is sent during the run.

- *State chunks during the run* — rejected. The SDK refuses a second `set_state`. Bypassing it
  with `choice.send_chunk(StateChunk(...))` sends several state chunks, and DIAL Core's analytics
  assembly fails on those. The SDK's own non-streaming merge would also concatenate the `messages`
  lists. This is the only option that would cover cancellation (Non-Goals), so it is left for when
  the SDK allows it.
- *Write on every node exit* — rejected, for the same reason.

### D2. An app-owned, versioned JSON snapshot, not a LangGraph checkpointer

A LangGraph `InMemorySaver` exported with the state was probed and does resume inside an
iteration. It was rejected for four reasons:

- It saves no more often than our snapshot does, since the state is written once per turn anyway.
- Its msgpack payload needs base64 inside JSON, which made it about 1.6 to 9 times larger than the
  transcript in the probe, depending on the durability mode.
- It keeps base64 images inline.
- It depends on node names, middleware node names and task-id hashes, so a redeploy could break a
  pending resume with no way to detect it.

The app's own JSON carries only data in the app's own vocabulary, with a format version (D11, D13).

### D3. Capture progress from the stream the runner already reads

The runner adds `"tasks"` to its stream modes and keeps three things.

- **The name of the running root node.** A root-namespace `tasks` event without `result` or
  `error` marks a node's start. This works without a checkpointer: probed on langgraph 1.2.9, the
  installed version.
- **The latest root `values` part.** It already keeps this.
- **The latest research-agent `values` part.** This is a `values` part whose namespace starts with
  `research-agent`. It is cleared when a research-agent task starts, so a failure in iteration N
  never uses iteration N − 1's list. The stream sends such a part as soon as the subgraph starts,
  holding its input, so the root part is the fallback only before that first part (observed in
  the proof of concept).

Alternatives:

- *Wrap each node to record its start* — rejected. research-agent is the compiled subgraph used
  directly as a node, and `subgraphs=True` streaming of its inner steps relies on that. A wrapper
  node would also couple the graph to the runner.
- *Infer the node from `updates`* — rejected. An `updates` part arrives only after a node
  finished, so the node that failed never sends one. `updates` also misses the image budget's
  in-place substitutions, which is why the runner already takes its transcript from `values`.
- *Infer it from `emit_activity`* — rejected. research-agent does not announce itself.

### D4. The coordinator catches `Exception`, and the runner says whether the graph phase failed

`_run_turn` wraps `ResearchRunner.run` in `try/except Exception`. On a failure it decides what to
persist, in this order, then re-raises the same exception object:

1. **The delivery step failed.** The runner records whether it has reached the delivery step. If it
   has, the turn persists nothing, as today.
2. **A snapshot refusal** (D13, and a snapshot image whose file is gone, D16). The turn persists
   nothing.
3. **A failure a resume would repeat** (D20). The turn persists an empty `messages` and the reset
   `PrepState` with `plan_id` cleared, and no snapshot.
4. **Anything else.** The coordinator asks the runner for the snapshot and persists it (D6). `BaseException` (`asyncio.CancelledError`) is not caught, so
a cancellation saves nothing, which matches the spec's accepted limitation.

Alternatives:

- *Split `run` into `run_graph` and `deliver`* — rejected. The activity stage deliberately stays
  open from the graph into the citation step. Several tests drive `run` directly
  (`tests/test_research_dispatch.py`). A phase flag gives the same answer with no API change.
- *Wrap the failure in a typed exception that carries the snapshot* — rejected. `error_resolution`
  classifies by the exception's own type and body, for example a 429 and its `display_message`.
  It unwraps only concurrency-runtime wrappers.
- *Persist inside the runner* — rejected. Persistence is the coordinator's job, and only the
  coordinator holds the preparation messages and `PrepState`.

### D5. A failure before the graph streamed any state

Here the snapshot comes from the state the run started from. On a fresh run, that is the initial
state at resume point research. On a resumed run, it is the snapshot as read, re-persisted
unchanged as the raw dict. This covers an MCP server that cannot be reached while the tools load,
and a snapshot image that still cannot be downloaded after its attempts (not a 404, D16).

Why not save nothing in this case: the failed-turn note must sit after the **latest** failed
answer, because it tells the agent that the previous user message's research failed. If the
failed resume saved nothing, the note would stay after the older failed answer. The latest answer
would then be a stateless fallback `AIMessage` with whatever partial content it had, and the agent
would not know it failed.

*Rebuild the snapshot from the partly rehydrated state* — rejected. It would re-upload images that
are already stored under the same names, and gain nothing.

### D6. What the failed turn persists, and where the snapshot lives

The failed turn persists `create_dial_state(prep_messages, saved_prep)`, plus the snapshot under its
own key, in one `set_state`.

- `saved_prep` is a copy of `PrepState` with `plan_approved` and `research_started` false.
- A failure a resume would repeat persists `create_dial_state([], saved_prep)`, with `plan_id`
  also cleared, and no snapshot (D20).
- The snapshot key constant lives in `app/history.py`, next to `DialState`, which owns the state's
  shape.
- The snapshot is parsed by its own reader, never through `DialState`. `DialState.from_dict` reads
  only `messages` and `preparation`, so a snapshot this code cannot read never makes the turn's
  `PrepState` unreadable.

Alternatives:

- *Persist the research transcript under `messages`, as on success* — rejected. The preparation
  agent would receive the whole research transcript with its images on every later turn. That is
  often several hundred kilobytes, far more than a preparation history. The approval check would
  also read research chatter as conversation.
- *Make the snapshot a typed field of `DialState`* — rejected. A snapshot that fails validation
  would fail `_parse_dial_state`. `load_last_prep_state` would then fall back to an older state or
  a fresh one, and the recorded plan would be lost.

### D7. `PrepState.plan_id`, a fresh id per recorded plan

`plan_id` is a `uuid4().hex` set in three places:

- `update_plan` sets a fresh one on every call.
- `update_query` clears it together with the plan.
- `start_research` gives one to a plan that has none. That is a plan recorded before this change,
  kept by a conversation that spans the deploy, or a plan whose id a failure a resume would repeat
  cleared (D20).

The snapshot stores the `plan_id` current when research started.

Alternatives:

- *A hash of the query and the plan's steps* — rejected. It would keep a snapshot when the same
  plan is recorded again, which is the risk below. But it needs a rule for what counts as "the
  same": whitespace, a reworded step, a re-run clarity check. An id per recording needs no such
  rule. The risk it leaves is visible in the discarded stage and its INFO record.
- *Renew the id in `update_query` as well as clear the plan* — not needed. Clearing the plan
  already leaves no plan to research, and the next `update_plan` sets a fresh id.
- *Name it `research_id` or `query_plan_id`* — `plan_id` was chosen because the id lives and dies
  with the recorded plan.

### D8. The resume is decided by the coordinator once preparation hands off

After preparation ends with `research_started`, `_run_turn` searches the history (D9), applies the
plan-id check and the refusals (D13), shows the stage (D19), and passes the parsed snapshot to the
runner.

*Inside the `start_research` tool* — rejected, for three reasons:

- The tool has no access to the request's history.
- The tools run with `handle_tool_error=True`, so a refusal raised there would become an error
  `ToolMessage` the agent answers in its own words. The chosen behavior is a fixed protocol error.
- The hand-off is silent anyway, so the tool's result text gains nothing.

### D9. Only the latest snapshot in the history is considered

The search walks `request.messages` backwards to the latest assistant message whose state carries
the snapshot key.

- *Search for any snapshot with a matching id* — not needed. Ids are only ever replaced by fresh
  ones, so when the latest snapshot's id differs from the current one, no older snapshot can match.
  A rewind removes later answers from the request, and their snapshots with them.
- *Copy the snapshot forward into every later answer* — rejected. A successful turn carries no
  snapshot. Copying would add up to about a megabyte to every answer, and DIAL Chat and StatGPT
  already send every earlier answer.

### D10. A conditional edge from `START`, with a router closed over the entry node

`build_research_graph` takes the entry node, defaulting to research-agent. It adds
`add_conditional_edges(START, route_from_start(entry), path_map={…four nodes…})`, in the same
factory style as the four `route_after_*` routers. With the default, the two tests that build the
graph from keyword arguments (`tests/test_report_loop_graph.py`,
`tests/test_research_review_stage.py`) need no change.

Alternatives:

- *A plain edge from `START` to the entry chosen at build time*, as the proof of concept did —
  rejected. The compiled graph's shape would differ from turn to turn. The drawn graph, and a test
  of the graph's edges, would see only one entry.
- *A `resume_at` channel in `ResearchState` read by the router* — rejected. It would put a
  persisted-format value into every node's state and into research-agent's input schema, and no
  node needs it.

### D11. The snapshot model

`ResearchSnapshot` is a pydantic model in a new `app/research/snapshot.py`, with
`extra="ignore"`. Its fields:

- `version: int`
- `plan_id: str`
- `resume_at: ResumePoint`, a `StrEnum` of `research`, `research_review`, `report`, `report_review`
- `messages: list[dict]`, produced by `messages_to_dict`
- `original_query`, `plans`, `research_iteration`, `report`, `report_version`,
  `report_revision_instruction`, `report_revision_failed`
- `data_queries: str` (D12)

The module also builds the resumed `ResearchState`. `state.py` gets the thin
`build_resumed_state` beside `build_initial_state`.

Supporting choices:

- **One mapping table.** It translates `ResumePoint` to node names in one place, used by the
  snapshot builder and by the router. Persisted data therefore never names a graph node, and
  renaming a node does not break a pending resume.
- **The channels mirror `ResearchState`.** A unit test asserts that the snapshot has a field for
  every `ResearchState` key. Adding a channel without updating the snapshot then fails a test
  instead of silently resuming with a missing channel.
- **Stage facts are derived when the snapshot is read.** The completed agent turns are the
  `AIMessage`s after the last `HumanMessage`. The report-review round is `report_version`.

Alternatives:

- *Store node names* — rejected. It couples persisted data to graph internals.
- *Store `agent_turns_completed`*, as the proof of concept did — rejected. It duplicates a fact the
  transcript already holds.

### D12. Data-query records as one JSON-encoded string

`data_queries` is `json.dumps({query_id: record.model_dump(mode="json", by_alias=True)})`. It is read
back with `json.loads` and `DataQueryRecord.model_validate`.

The DIAL SDK's chunk merge re-slots every list of dicts whose elements carry an integer `index`,
at any depth, and then deletes the key (`aidial_sdk/utils/merge_chunks.py`, verified on the
installed SDK). The SDK's own non-streaming path never applies it to a failed turn's state: it
raises on the error chunk and drops the merged response (`aidial_sdk/utils/streaming.py`). The
exposure is a client that rebuilds a streamed answer with the same merge and sends it back, as
`scripts/send_conversation.py` does with `merge` and `cleanup_indices`. The records keep the
server's elements whole, so a server that ever adds an `index` field would have them corrupted by
such a client. A string is copied as it is.

Alternatives:

- *The whole snapshot as one string* — rejected. It would also protect the transcript's tool
  artifacts, but escaping makes a state of about a megabyte bigger, and the state can no longer be
  read by eye.
- *Walk the snapshot and skip saving when an `index` is found* — rejected. That resume would be
  lost.
- *Plain JSON* — rejected. `_meta` would be the first server data any state persists that this
  exposure applies to.

The transcript's tool artifacts keep the exposure they already have today under `messages`.

### D13. Reading a snapshot, and refusing one this code cannot read

The reader works in this order:

1. Take the raw dict.
2. Read `plan_id`. If it is not a string, raise `SnapshotUnreadableError`. If it differs from the
   current id, discard the snapshot (D19) without reading further.
3. Read `version`. If it is not this code's version, raise `SnapshotVersionUnsupportedError`.
4. Validate the model, decode `messages` with `messages_from_dict`, and decode `data_queries`. If
   any of these fails, raise `SnapshotUnreadableError` from the original exception, so the turn's
   ERROR record carries both stack traces.

Both errors are `AppConditionError` subclasses in `app/error_resolution.py`, with the curated
texts the spec requires. `SnapshotVersionUnsupportedError` is outgoing 409, non-retryable.
`SnapshotUnreadableError` is outgoing 500, non-retryable. The lookup runs outside the research
`try`, so a refusal persists nothing. The image download (D16) runs inside it and can raise
`SnapshotUnreadableError` too, so D4 checks for a refusal before it would save anything.
A third subclass, `SnapshotImageUnavailableError`, is retryable (D16).

Tolerant reading (`extra="ignore"`, defaults for added fields) keeps most releases from needing a
version bump. A release that changes the format incompatibly bumps the version. The project accepts
that a resume pending across such a release is refused.

Alternatives:

- *Discard the snapshot and research from zero* — rejected by the user. Losing progress silently
  is worse than a clear message.
- *Tell the user through the preparation agent with a different note* — rejected by the user. The
  text would be the model's own, and the error reference matters for "an error on our side".
- *422 for the version refusal* — rejected for 409. 409 matches the existing handed-off refusal:
  the conversation's state conflicts with what this deployment can continue.

### D14. The failed-turn note is a `SystemMessage` inserted during reconstruction

`reconstruct_history` appends a note after the decoded `messages` of every assistant message whose
state carries a snapshot. It takes the loaded `PrepState.plan_id` as a parameter, from
`PrepAgentRunner.run` (`app/preparation/runner.py`), and reads nothing of the snapshot but its
`plan_id`. There are two fixed notes:

- **The resumable note** follows a snapshot whose `plan_id` equals the loaded one.
- **The not-resumable note** follows a snapshot of another plan: the user changed the plan, or a
  failure a resume would repeat cleared the id (D20). The resumable note's "its progress was saved
  … can continue" would no longer be true there. With no note at all, the turn's persisted
  `start_research` → "Research has started… your turn is over" result would stand with nothing
  after it, and the agent would read research as still running (the layout D5 and D20 reject).
- **No note** follows a snapshot whose `plan_id` is missing or not a string. Reconstruction never
  raises over it. Research start refuses such a snapshot (D13). `_format_conversation` (`app/preparation/tools.py`) renders a
system message as a `System note: …` line instead of dropping it. The text lives in
`app/preparation/prompts.py`, as a triple-quoted constant.

The resumable note's wording is the proof of concept's, which the spec's four points describe:

> The research run that the previous user message started failed with an error before it finished.
> Nothing of that run was delivered to the user. Its progress was saved, so research on the same
> query and plan can continue from where it stopped. The plan's approval was reset by the failure.
> To continue, call approve_plan, then start_research.

The not-resumable note follows the same pattern, untested:

> The research run that the previous user message started failed with an error before it finished.
> Nothing of that run was delivered to the user, and its progress cannot be continued. Research on
> the current query and plan starts from the beginning once the user approves the plan. To start it,
> call approve_plan, then start_research.

Evidence for the resumable wording:

- A probe with a vaguer note ("an error happened while the previous user message was being
  processed") was accepted by every GPT deployment tested. But most of them tied it to the wrong
  message.
- Without the last sentence, the agent sometimes called `start_research` without `approve_plan`.
  The gate then failed, and the agent asked the user to confirm the plan again.
- With it, every try took the one-turn path, over few tries.

Alternatives:

- *A `PrepState` flag* — rejected. It duplicates the snapshot's presence and does not mark a
  position in the history.
- *Trigger on the snapshot's presence alone*, as the proof of concept did — rejected in the third
  review pass. After a changed plan, or after a resumed run fails with a D20 class, the note would
  still tell the agent and the approval check that progress was saved and can continue, and the
  reviewer's paragraph (D15) would approve "continue" on that basis. The only cost of the plan-id
  check is one change in the history's prefix when the plan changes.
- *No note for a snapshot of another plan* — rejected in the fourth review pass. The failed turn's
  `start_research` hand-off would stand in the history with nothing after it.
- *Add the note only before the new user message, for that call* — rejected. The history before
  the note would change from turn to turn and defeat the prompt cache. The stored position keeps it
  stable.
- *A user-role note* — rejected. The model would attribute it to the user.
- *Include DIAL Core's `display_message`* — rejected. The note carries no error text, so a later
  turn never replays it.

### D15. The approval reviewer prompt changes, and the tool descriptions do not

`PLAN_REVIEW_SYSTEM` gets one paragraph. When a system note says the research run failed, a
request to continue or retry approves the recorded plan, provided the user approved that same plan
before the error.

*Also reword the `approve_plan` and `start_research` descriptions* — not needed. The note names both
calls in order, and the proof of concept took the one-turn path on every try with the descriptions
unchanged. Fewer prompt edits also mean less drift in the turns that have no failure.

### D16. Images, and stages for the snapshot's tool calls

**Upload.** The snapshot's transcript goes through the existing `upload_image_blocks` at save time,
on a list the turn is about to discard. The file names are the existing ones: tool call id plus
block position. A resumed turn that completes uploads the same images again under the same names.
Overwriting them is inferred from `aidial_client` uploading with `PUT` and no `If-None-Match`, not
verified against DIAL Core.

**Download.** A new helper in `utils/image_attachments.py` downloads each image with up to three
attempts and exponential backoff from 1 s, using `STREAM_DROP_MAX_ATTEMPTS` and its initial delay
from `utils/llm.py`. The resumed run calls it before the graph starts. Its outcomes:

- **A 404.** `aidial_client` raises `ResourceNotFoundError` (`aidial_client/resources/files.py`).
  The file is gone for good, so it is not retried. The helper raises `SnapshotUnreadableError`, and
  D4 persists nothing, so the conversation is refused like any snapshot that cannot be read.
- **Anything else after the last attempt.** The helper raises `SnapshotImageUnavailableError`, a
  retryable `AppConditionError` with the curated "could not be loaded" text. D5 re-saves the
  snapshot unchanged, so a later "continue" can try again.

The typed errors are needed because `aidial_client` raises its own `DialException`, which
`error_resolution._extract_error_details` does not recognize. Untyped, it would resolve to the
generic non-retryable message.

`AsyncDial` itself retries 408, 409, 429 and transport errors twice per request
(`aidial_client/_constants.py`, `DEFAULT_MAX_RETRIES = 2`). The three attempts therefore come to at
most nine requests for those errors, which is accepted for a rare path.

**Stages.** The runner adds the snapshot's message ids to `_seen_ids` before streaming. When
research-agent ends, the parent graph re-emits the subgraph's whole message list. Without the ids,
every snapshot tool call would become a 0.00 s stage and an INFO "Tool call completed" record,
which the proof of concept observed.

Alternatives:

- *Reuse `rehydrate_image_blocks` and its placeholder* — rejected. The resumed report could cite a
  page whose image research-agent no longer sees, with nothing to show for it.
- *Upload images as they arrive* — this is in Non-Goals.

### D17. The data-query records are restored before the graph runs

After `load_mcp_tools` creates the turn's `DataQueryStore`, the runner fills `records` from the
snapshot. The capture interceptor then adds and replaces records by id as it does today. Nothing in
`data_queries.py` changes.

### D18. Logging

The coordinator writes the INFO "Snapshot saved" record. It also writes "Snapshot skipped" (D20),
"Snapshot reused" and "Snapshot discarded", with the fields the **logging-policy** delta lists. Sizes are `len()` of the
JSON-encoded snapshot and of the whole state.

A snapshot that cannot be built logs one WARNING with the exception class, never `logger.exception`
at ERROR. The single ERROR stays with `raise_dial_error`. Each retried image download logs one
WARNING, with the URL stripped by the existing `_strip_url_query`.

### D19. The snapshot stage comes from the coordinator

The coordinator emits the "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage
as a closed stage, before the runner opens its first activity stage. It carries the same facts as
the INFO record. StatGPT shows Deep Research's stages only in debug mode by default
(`stages_config.debug_only`), so no setting is added here.

### D20. Failures a resume would repeat save no snapshot

A resume re-sends the failed run's input and restores its state. For some failures that is certain
or likely to fail the same way, so a snapshot would only make every "continue" fail again. Each
attempt would also add another research transcript to the conversation, while the failed-turn
note kept saying research can continue. These failures save no snapshot. The coordinator logs one
INFO "Snapshot skipped" record naming the class (D18).

**What such a failed turn persists.** It persists an empty `messages` and the reset `PrepState`:
`plan_approved` and `research_started` false, and `plan_id` cleared. The rule is the same for a
fresh run and a resumed one.
- **Clearing the id matters on a resumed run.** Turn A fails with a 429 and saves snapshot S1 for
  plan id P. Turn B resumes from S1 and fails with a context overflow. If turn B persisted nothing,
  `load_last_prep_state` would skip its stateless answer and reload turn A's `PrepState`, still
  carrying P. The history search (D9) would find S1, which still matches, so every later "continue"
  would replay the failure.
- **With the id cleared, nothing can match.** Turn B's `PrepState` is the latest, and it has no id.
  `start_research` gives the plan a fresh one (D7), no snapshot carries it, and research starts from
  zero, showing the discarded stage. The earlier failed turn's note becomes the not-resumable one,
  since its snapshot no longer belongs to the current plan (D14).
- **For a fresh run the outcome equals today's.** The approval is reset and research starts fresh.
- **Why `messages` is empty.** With it empty, `reconstruct_history` falls back to the failed
  answer's visible text, exactly as a failed turn reads today. Persisting the preparation messages
  would leave `start_research`'s "Research has started… your turn is over" result in the history
  with nothing after it, and the agent would read research as still running.
  `load_last_prep_state` reads `preparation` whether `messages` is empty or not.

**This is a standing rule, not a detail of this change.** These classes are the app's list of
failures that re-sending cannot fix. Any later retry or resume mechanism consults the same
predicate instead of retrying every exception. The post-MVP report-loop re-raise and any change to
how a quota 429 is retried are the obvious next candidates. The code comment on the predicate says
so, next to the codes it lists.

| Class | Matched by | Why a resume repeats it |
|---|---|---|
| Input rejected: the model's context was exceeded | error code `context_length_exceeded` or `truncate_prompt_error` | The research transcript only grows, so a resumed call sends at least the same messages |
| Input rejected: a content filter | error code `content_filter` | Deterministic when the filter judged the input. When it judged the output, a new attempt might pass, and that resume is knowingly given up: the code does not say which side was judged |
| Input rejected: the model refused the request | a model call's HTTP 400, 413 or 422 | The same request, for example an image from a tool result the model cannot accept, is sent again |
| Step budget exhausted | `GraphRecursionError` | A research-agent iteration that never finished would get its whole transcript back and a fresh step budget. Its message, "narrow the request and start a new conversation", stays true only if no resume is offered |

**How it is classified.** The predicate is a new public function in `app/error_resolution.py`,
built from the same pieces the user-facing message is built from:
- It unwraps a concurrency-runtime container first, as `resolve_exception` does.
- It reads the error code through the same extraction (`_extract_error_details`, with its
  status-from-code backfill), and checks it against the same codes `_CODE_MESSAGES` lists.
- It counts a 400, 413 or 422 only for an `openai.APIError`, a model call. A DIAL Core or MCP
  4xx in research setup is a configuration fault, and an admin's fix makes it resumable.
- It matches the step budget by `GraphRecursionError`.

Building the predicate on that extraction means it and the error message can never disagree on
what an input rejection is.

Alternatives:

- *Save a snapshot anyway, and reword the messages and the note* — rejected. "continue" cannot
  succeed for these classes, and each attempt makes every later request bigger.
- *Classify by the resolver's existing `retryable` flag* — rejected. It is too broad: an
  authentication failure, a missing deployment and a connectivity failure are non-retryable too,
  yet a resume succeeds once an admin fixes them, and the progress is worth keeping.
- *Keep the step budget resumable and reword its message* — rejected by the user. An iteration that
  ran out of steps is likely to loop again, at the cost of another full budget of model calls.
- *Resume after shrinking the context* — out of scope (Non-Goals). It changes what is re-sent,
  which is exactly the condition under which the standing rule allows a retry.
- *Persist nothing for these failures* — rejected after the second review pass. On a resumed run it
  leaves the earlier snapshot resumable, as shown above.
- *Clear the id only when the failing run was a resume* — rejected by the user. For a fresh run the
  outcome is the same either way, so one rule is simpler than a branch.
- *Persist a "discarded" marker under the snapshot key* — rejected. It adds format to the snapshot,
  while the plan id already decides whether a snapshot matches.

## No changes required

- **`app/research/nodes.py`.** Every node reads its inputs from the state, so it cannot tell a
  resumed run from a fresh one. The report loop keeps absorbing its failures as it does today.
- **`app/research/middleware.py`.** `IterationCounterMiddleware` reads `research_iteration` from
  the state, so a resumed iteration ends at the right count.
- **`app/middleware.py` (image budget) and `app/tool_failures.py`.** Both recompute their counts
  from the messages on every call.
- **`app/research/data_queries.py`.** `DataQueryRecord` already dumps and validates by alias, and
  the runner restores into `DataQueryStore.records` (D17).
- **`app/preparation/agent.py`.** The agent takes its history from `reconstruct_history`, which
  `app/preparation/runner.py` now calls with the loaded plan id (D14). The middleware that stops
  after `start_research` is unchanged.
- **`app/turn_lifecycle.py`.** `raise_dial_error` is unchanged. A state set before the raise
  reaches the client ahead of the error chunk.
- **The 409 check in `app/completion.py`.** It reads `research_started`, which a failed turn
  persists as false.
- **`load_last_prep_state` and `DialState.from_dict`.** `DialState` reads only `messages` and
  `preparation`, so the extra key is ignored. `PrepState` ignores unknown fields, so a rollback
  reads the new `plan_id` harmlessly.
- **`utils/llm.py`.** The OpenAI client's `max_retries=3` stays (Non-Goals).
- **`app_properties.py`, `dial_conf/core/applications-template.json`,
  `docs/generated-app-schema.json`, the README environment-variables table.** There is no new
  property or environment variable.

## Risks / Trade-offs

- **[A cancellation or a killed pod saves nothing]** → This is accepted and stated in the spec. The
  user sees research start from zero, as today.
- **[A content-filter hit on the model's output loses its resume]** → D20 cannot tell an output
  hit, which a new attempt might pass, from an input hit, which it would not. Both save no snapshot.
  This is accepted: such hits are rare in a research run, and research restarts from zero, as
  today.
- **[A future retry mechanism retries every exception]** → It would bring back the endless
  "continue" that D20 prevents. D20 is written as a standing rule, and the predicate's code comment
  points at it.
- **["Try again" in DIAL Chat drops the failed answer with its snapshot]** → Research restarts from
  zero. Nothing is built for it in this change (Non-Goals).
- **[Recording the same plan again restarts research]** → Every `update_plan` renews the id. That
  can happen, for example, when the approval reviewer calls the recorded plan stale. The discarded
  stage and its INFO record make this visible.
- **[The model skips `approve_plan` on "continue"]** → `start_research`'s gate refuses, and the
  agent asks the user to confirm. That costs one extra turn, not progress. The note's last sentence
  makes it rare.
- **[The conversation grows]** → Each failed answer carries one research transcript, up to about a
  megabyte. Through StatGPT, every answer until the report carries the whole session again. A few
  such turns stay far below DIAL Core's 64 MiB limit, and there is no size guard (Non-Goals).
- **[A failed turn with many images ends later]** → They are uploaded in parallel at save time,
  which took a few seconds for a few dozen images in the proof of concept. A resume downloads them
  before its first model call.
- **[A quota error in the report loop delivers an unreviewed or partly reviewed draft]** → This is
  today's behavior, kept on purpose (Non-Goals).
- **[A system message in the middle of the history]** → It was accepted by the five GPT
  deployments in `LLMModelsEnum`. The two Claude deployments there were not tested, because the
  local DIAL Core does not serve them. Test on an environment that serves them before a channel
  uses them.
- **[A resumed iteration gets a fresh step budget]** → `recursion_limit` applies to each graph run.
  An iteration that failed after k steps may therefore run up to k plus the full budget in total.
  The budget still bounds each turn.
- **[A resume runs with today's data sources, code and properties]** → The snapshot carries data
  only. The data sources are fetched again and may differ from those of the failed run.
- **[A refused snapshot blocks the conversation]** → An unreadable matching snapshot, or one with an
  image whose file is gone, is refused on every request to continue. The message tells the user to
  start a new conversation, and changing the query or the plan also gets past it. A snapshot whose
  `plan_id` itself cannot be read is the exception: it counts as matching (D13), so only a new
  conversation gets past it.
- **[The transcript's tool artifacts can still meet the `index` merge]** → This is today's exposure
  under `messages`, unchanged. Only non-streaming callers are affected.

## Migration Plan

- **No data migration.** Old conversations carry no snapshot. A plan recorded before the deploy
  gets a `plan_id` when its research starts (D7).
- **Deploy order is free.** The StatGPT backend change acts only when Deep Research sends a state
  with its error. Before it lands, StatGPT discards the snapshot and "continue" restarts research,
  as today. Through DIAL Chat, the resume works as soon as this change ships.
- **Rollback.** Older code ignores the snapshot key and `plan_id`. The failed answer's reset
  `PrepState` lets "continue" approve and restart research from zero. Redeploying this change makes
  a pending snapshot resumable again, as long as the format version is unchanged.
- **Verification during implementation.** Two unit tests use a real compiled research graph with
  a fake model:
  - **Capture.** The fake model raises on its third call. The test asserts the captured resume point
    and transcript, which checks D3 against LangGraph's real event order: clearing on research-agent's
    start, the namespace match, dropping the trailing model message.
  - **Resume.** It resumes from that snapshot and asserts that only the failed model call runs again
    and that `research_iteration` comes out right.

  A manual run on the local stack injects a quota error and resumes through DIAL Chat.
- **A spec delta still missing.** The `data-sources-discovery` scenario "A handed-off conversation
  makes no call" says "whose research already started on an earlier turn". Under this change, a
  conversation counts as handed off once its report was delivered, and a failed research run does
  not count. That scenario's WHEN needs the same rewording as the `dial-agent-with-mcp`
  research-already-handed-off scenario, in a `data-sources-discovery` delta. The delta must be added
  to this change before it is archived.

## Open Questions

- **The two Claude deployments and a mid-history system message.** Test on an environment that
  serves them. The answer changes neither the specs nor the approach; a deployment that rejects the
  message would need its own adapter fix.
- **The note's exact wording.** It may be tuned after end-to-end runs through StatGPT with a real
  channel. The spec fixes what the note says, not its words.
