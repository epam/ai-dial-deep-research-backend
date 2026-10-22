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
- **Resuming the delivery step.** The delivery step never fails the turn (D22), so there is nothing
  to resume.
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
  before re-sending it. D20 marks such a failure's snapshot as not resumable.
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

### D4. The coordinator catches `Exception` for the whole turn, and the runner says how far it got

`_run_turn` wraps the rest of the turn in `try/except Exception`, not only `ResearchRunner.run`,
because every failed turn persists a failure record (D21). The `try` starts after the 409 check.
Everything before it, the application properties fetch and their validation included, stays outside
and persists nothing on a failure, as today. Once the report loop has settled a draft, nothing
raises out of the runner (D22), so no case below concerns the delivery. On a failure the
coordinator decides what to persist, in this order, then re-raises the same exception object:

1. **A snapshot refusal** (D13, and a snapshot image whose file is gone, D16). The turn persists
   only the failure record. It comes first because every refusal happens before the graph streams
   any state, so the next case would otherwise hide it.
2. **No research graph state.** The failure came before research started, in the data-sources fetch
   or in preparation, or before the graph streamed any state, for example while the research tools
   load. The turn persists only the failure record (D21).
3. **Anything else.** The coordinator asks the runner for the snapshot and persists it with the
   failure flag (D6). A failure a resume would repeat (D20) takes this path too; its snapshot is
   marked not resumable.

`BaseException` (`asyncio.CancelledError`) is not caught, so a cancellation saves nothing, which
matches the spec's accepted limitation.

Alternatives:

- *Split `run` into `run_graph` and `deliver`* — rejected. The activity stage deliberately stays
  open from the graph into the citation step. Several tests drive `run` directly
  (`tests/test_research_dispatch.py`). A phase flag gives the same answer with no API change.
- *Wrap the failure in a typed exception that carries the snapshot* — rejected. `error_resolution`
  classifies by the exception's own type and body, for example a 429 and its `display_message`.
  It unwraps only concurrency-runtime wrappers.
- *Persist inside the runner* — rejected. Persistence is the coordinator's job, and only the
  coordinator holds the preparation messages and `PrepState`.

### D5. A failure before the graph streamed any state saves no snapshot

This covers an MCP server that cannot be reached while the tools load, and a snapshot image that
still cannot be downloaded after its attempts (not a 404, D16). The turn persists only the failure
record (D21).

- **On a fresh run** there is no progress to save.
- **On a resumed run** the snapshot the run started from stays the latest one in the history, and
  its plan id still matches, because the failure record carries the `PrepState` the turn started
  from. The next request to continue resumes from it.
- **The failed-turn note** still follows the latest failed answer, because the note is triggered by
  the failure flag (D14), not by a snapshot.

Alternatives:

- *Save the state the run started from as the snapshot*: the initial state on a fresh run, or the
  snapshot as read on a resumed run — rejected. It only kept the note after the latest failed
  answer, which the failure flag now does, and on a resumed run it copied up to about a megabyte.
- *Rebuild the snapshot from the partly rehydrated state* — rejected. It would re-upload images that
  are already stored under the same names, and gain nothing.

### D6. What the failed turn persists, and where the snapshot lives

A failed research turn with a snapshot persists `create_dial_state(prep_messages, saved_prep)`,
plus the snapshot and the failure flag under their own keys, in one `set_state`.

- `saved_prep` is a copy of `PrepState` with `plan_approved` and `research_started` false.
- Any other failed turn persists the failure record of D21 instead.
- The snapshot and failure-flag key constants live in `app/history.py`, next to `DialState`, which
  owns the state's shape. The flag never goes into `PrepState`: every turn loads `PrepState` and
  persists it again, so a flag there would be copied into the next successful turn.
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
  kept by a conversation that spans the deploy.

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
  A rewind removes later answers from the request, and their snapshots with them. A snapshot marked
  not resumable (D20) shadows the older ones on purpose: the run it records failed in a way a
  resume repeats, so an older snapshot of the same plan would replay that failure.
- A failed turn without a snapshot carries no snapshot key, so the search passes over it.
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
- `resumable: bool`, false for a failure a resume would repeat (D20)
- `resume_at: ResumePoint`, a `StrEnum` of `research`, `research_review`, `report`, `report_review`
- `messages: list[dict]`, produced by `messages_to_dict`
- `original_query`, `plans`, `research_iteration`, `report`, `report_version`,
  `report_revision_instruction`, `report_revision_failed`
- `data_queries: str` (D12)

The module also builds the resumed `ResearchState`. `state.py` gets the thin
`build_resumed_state` beside `build_initial_state`.

Supporting choices:

- **A stable header.** `plan_id`, `resumable` and `version` keep their names and meaning in every
  format version, so any release can decide whether a snapshot is to be resumed before it reads
  the rest (D13).
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

`data_queries` is `json.dumps({query_id: record.model_dump(mode="json", by_alias=True)})`. It is
read back with `json.loads` and `DataQueryRecord.model_validate`.

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
   current id, discard the snapshot (D19) with the reason `plan_changed`, without reading further.
   The discard stage and record show the snapshot's `resume_at` only when it reads as a known
   `ResumePoint`, because `resume_at` is not part of the stable header.
3. Read `resumable`. If it is not a boolean, raise `SnapshotUnreadableError`. If it is false,
   discard the snapshot with the reason `not_resumable`, without reading further. Reading it before
   `version` means a non-resumable snapshot of another format version is discarded, not refused.
4. Read `version`. If it is not this code's version, raise `SnapshotVersionUnsupportedError`.
5. Validate the model, decode `messages` with `messages_from_dict`, and decode `data_queries`. If
   any of these fails, raise `SnapshotUnreadableError` from the original exception, so the turn's
   ERROR record carries both stack traces.

Both errors are `AppConditionError` subclasses in `app/error_resolution.py`, with the curated
texts the spec requires. `SnapshotVersionUnsupportedError` is outgoing 409, non-retryable.
`SnapshotUnreadableError` is outgoing 500, non-retryable. A refusal persists only the failure
record (D21), which carries the `PrepState` the turn started from and so keeps the plan id: the same
snapshot stays the latest one and still matches, and the refusal repeats. The image download (D16)
can raise `SnapshotUnreadableError` too, so D4 checks for a refusal before it would save a snapshot.
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

`reconstruct_history` appends one fixed note after every assistant message whose state carries the
failure flag (D21): after its decoded `messages`, or after the fallback `AIMessage` of its native
`content` when `messages` is empty. It reads nothing of a snapshot and needs no parameter.
`_format_conversation` (`app/preparation/tools.py`) renders a system message as a `System note: …`
line instead of dropping it. The text lives in `app/preparation/prompts.py`, as a triple-quoted
constant.

Why every failed turn needs the note: a failed research turn persists its preparation messages,
which end with `start_research`'s "Research has started… your turn is over" result. Without a note
after it, the agent reads research as still running. A failed turn without a snapshot reads as an
empty or partial answer, and without a note the agent cannot tell that it failed.

The note does not say whether progress was saved; the coordinator alone decides whether to resume
(D8, D9). It does not say that the approval was reset either: after a preparation failure the
failure record keeps the `PrepState` the turn started from, which may still have the plan approved.
Its starting wording, to be tested:

> The previous user message failed with an error before its answer finished. If the user asks to
> continue a research whose plan they had approved, call approve_plan, then start_research.
> Otherwise handle the user's request as usual.

- **"Before its answer finished", not "nothing was delivered".** Preparation text streams and stays
  visible above the error, so "nothing was delivered" can be false.
- **The instruction is conditional.** A failure can come before any plan exists, or while the user
  was asking to change the plan. An unconditional "call approve_plan, then start_research" would
  push the agent to approve an old plan, or to call `approve_plan` with no plan recorded.

Evidence from the proof of concept, whose note was triggered by the snapshot alone:

- A probe with a vaguer note ("an error happened while the previous user message was being
  processed") was accepted by every GPT deployment tested. But most of them tied it to the wrong
  message, so the note names the previous user message.
- Without an explicit "call approve_plan, then start_research", the agent sometimes called
  `start_research` without `approve_plan`. The gate then failed, and the agent asked the user to
  confirm the plan again.
- With it, every try took the one-turn path, over few tries. The conditional form has not been
  tried yet.

Alternatives:

- *A `PrepState` flag* — rejected. Every turn loads `PrepState` and persists it again, so the flag
  would be copied into the next successful turn, and it does not mark a position in the history.
- *Trigger on the snapshot's presence* — rejected. A failed turn without a snapshot, such as a
  preparation failure, would get no note.
- *Two notes, resumable and not resumable, chosen by comparing the snapshot's plan id with the
  loaded one* — rejected. It needed the plan id inside `reconstruct_history`, and the
  not-resumable note promised a restart while a snapshot whose plan id could not be read got no
  note at all. One note that promises nothing about progress removes both problems.
- *Add the note only before the new user message, for that call* — rejected. The history before
  the note would change from turn to turn and defeat the prompt cache. The stored position keeps it
  stable.
- *A user-role note* — rejected. The model would attribute it to the user.
- *Include DIAL Core's `display_message`* — rejected. The note carries no error text, so a later
  turn never replays it.

### D15. The approval reviewer prompt changes, and the tool descriptions do not

`PLAN_REVIEW_SYSTEM` gets one paragraph. When the failed-turn note is present, a request to
continue or retry approves the recorded plan, provided the user approved that same plan before the
error.

*Also reword the `approve_plan` and `start_research` descriptions* — not needed. The note names both
calls in order, and the proof of concept took the one-turn path on every try with the descriptions
unchanged. Fewer prompt edits also mean less drift in the turns that have no failure.

### D16. Images, and stages for the snapshot's tool calls

**Upload.** The snapshot's transcript goes through the existing `upload_image_blocks` at save time,
on a list the turn is about to discard, in the mode that re-raises a bucket lookup that fails
(D22). The file names are the existing ones: tool call id plus
block position. A resumed turn that completes uploads the same images again under the same names.
Overwriting them is inferred from `aidial_client` uploading with `PUT` and no `If-None-Match`, not
verified against DIAL Core.

**Download.** A new helper in `utils/image_attachments.py` downloads each image with up to three
attempts and exponential backoff from 1 s, using `STREAM_DROP_MAX_ATTEMPTS` and its initial delay
from `utils/llm.py`. The resumed run calls it before the graph starts. Its outcomes:

- **A 404.** `aidial_client` raises `ResourceNotFoundError` (`aidial_client/resources/files.py`).
  The file is gone for good, so it is not retried. The helper raises `SnapshotUnreadableError`, and
  D4 persists only the failure record, so the conversation is refused like any snapshot that cannot
  be read.
- **Anything else after the last attempt.** The helper raises `SnapshotImageUnavailableError`, a
  retryable `AppConditionError` with the curated "could not be loaded" text. The graph has not
  started, so D5 saves no snapshot, and the snapshot the turn started from stays the latest one. A
  later "continue" can try again.

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

The coordinator writes four INFO records, with the fields the **logging-policy** delta lists:

- "Snapshot saved", with `resumable` and, for a non-resumable snapshot, the failure class (D20);
- "Failure recorded", for a failed turn that saved no snapshot, with the reason
  `preparation_failed` (any failure before research started), `snapshot_refused`,
  `no_graph_state` or `snapshot_failed` (D4, D21);
- "Snapshot reused";
- "Snapshot discarded", with the reason `plan_changed` or `not_resumable`. For a non-resumable
  snapshot the two plan ids are equal, so the ids alone would explain nothing. Its resume point
  appears only when it reads as a known value (D13).

A step that fails after the report is written logs one WARNING naming the step (D22).

Sizes are `len()` of the JSON-encoded snapshot and of the whole state.

A snapshot that cannot be built or saved, and a failure record that cannot be saved, each log one
WARNING with the exception class, never `logger.exception` at ERROR. The single ERROR stays with
`raise_dial_error`. Each retried image download logs one WARNING, with the URL stripped by the
existing `_strip_url_query`.

### D19. The snapshot stage comes from the coordinator

The coordinator emits the "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage
as a closed stage, before the runner opens its first activity stage. It carries the same facts as
the INFO record, the discard reason included. StatGPT shows Deep Research's stages only in debug
mode by default (`stages_config.debug_only`), so no setting is added here.

### D20. Failures a resume would repeat save a snapshot that is never resumed

A resume re-sends the failed run's input and restores its state. For some failures that is certain
or likely to fail the same way, so resuming would only make every "continue" fail again. These
failures still save their snapshot, like any research failure, but marked `resumable: false`. The
snapshot is kept so that a developer can see what happened during the run when the client hides
Deep Research's stages. The resume rule (D9, D13) never resumes it: research on a later turn starts
from the beginning, and the turn shows the discarded stage with the reason `not_resumable`.

- **On a resumed run the mark keeps the earlier snapshot from being replayed.** Turn A fails with a
  429 and saves snapshot S1 for plan id P. Turn B resumes from S1 and fails with a context
  overflow, so it saves S2, also for P, marked not resumable. S2 is now the latest snapshot, and the
  history search (D9) considers only the latest one, so S1 is never replayed.
- **The plan id stays.** Nothing is cleared, so `PrepState` keeps P, and a later fresh run of the
  same plan can itself save a resumable snapshot for P.
- **The failure record is the ordinary one.** The turn persists its preparation messages, the reset
  `PrepState`, the snapshot and the failure flag (D6, D21), and gets the same note as any failed
  turn (D14).

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
| Step budget exhausted | `GraphRecursionError` | A research-agent iteration that never finished would get its whole transcript back and a fresh step budget, and is likely to loop again |

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

**The error messages.** The user-facing texts of these classes state what happened, for example
that the AI model's context window was exceeded, and hold whether the call came from preparation or
from research. Each drops the advice that does not fit a research call: "shorten your messages"
for a context overflow, "rephrase your message" for a content filter, "reduce the size of your
message or attachments" for a 413, "contact your administrator" for a 400 or 422, and "start a new
conversation" for the step budget, because a request to continue in the same conversation starts
the research again from the beginning. The texts stay shared between preparation and research, in
`app/error_resolution.py`.

Alternatives:

- *Save no snapshot, and clear the plan id so no earlier snapshot matches* — rejected. The failed
  turn would carry no record of what the run did, and clearing the id needed its own save path and
  its own note. The mark gives the same outcome on the next turn with the ordinary save. The cost
  is accepted: such a snapshot is often the largest transcript of the conversation, because a
  context overflow means the transcript is huge (Risks).
- *Classify by the resolver's existing `retryable` flag* — rejected. It is too broad: an
  authentication failure, a missing deployment and a connectivity failure are non-retryable too,
  yet a resume succeeds once an admin fixes them, and the progress is worth keeping.
- *Keep the step budget resumable and reword its message* — rejected by the user. An iteration that
  ran out of steps is likely to loop again, at the cost of another full budget of model calls.
- *Resume after shrinking the context* — out of scope (Non-Goals). It changes what is re-sent,
  which is exactly the condition under which the standing rule allows a retry.
- *Persist nothing for these failures* — rejected. On a resumed run it leaves the earlier snapshot
  the latest one, still resumable, so every later "continue" replays the failure.
- *A header-only snapshot without the transcript* — rejected by the user. It would shadow older
  snapshots just as well and keep the conversation small, but it would lose the record of what the
  run did.

### D21. Every failed turn persists a failure record

Deep Research learns that a turn failed only from what that turn saved: the client sends a failed
answer back with its state, but not with its error. So every failed turn persists a failure flag,
and the failed-turn note (D14) follows every message that carries it.

- **Where the flag lives.** Under its own top-level key of the state, next to the snapshot key, or
  as a defaulted field of `DialState`. Never in `PrepState` (D6).
- **The failure record.** A failed turn without a snapshot persists an empty `messages`, the
  `PrepState` read from the request with `load_last_prep_state(request)`, and the flag. The
  preparation runner mutates the loaded `PrepState` in place, so the record reads it again from the
  request rather than taking the live object. A failed research turn with a snapshot persists the
  parts of D6 instead.
- **What persists nothing.** A failure while the application properties are fetched or validated,
  which comes before the `try` (D4); a cancellation; a non-streaming request (the SDK drops the
  state); and the 409 refusal of a conversation whose report was delivered. A failure after the
  report is written does not fail the turn at all (D22).
- **Saving never hides the failure.** Building and saving the snapshot, its image upload included,
  run inside a `try`. When any of it raises, the turn drops the snapshot, persists the failure
  record instead, and still raises the original error. The failure record's own save runs inside a
  `try` too; if it raises, the turn persists nothing and still raises the original error. Each logs
  one WARNING (D18). The SDK allows one `set_state` per turn and has no public accessor that says
  whether a state was set (`aidial_sdk/chat_completion/choice.py`), so the coordinator tracks
  whether it saved.
- **A state too large is not caught.** Saving it does not raise in Deep Research. DIAL Core
  rejects a request above its limit (64 MiB by default) with 413, and the oversized state reaches
  Core only on the next request, which carries the history. Dropping such a snapshot would need a
  size check before the save, which this change does not add (Non-Goals).

Alternatives:

- *Persist nothing for a failure without a snapshot, as today* — rejected. The next turn would see
  an empty or partial answer with no note, and the agent could not tell that the request failed.
- *Persist the live `PrepState` of the failed turn* — rejected. A tool call that ran before the
  failure, such as an `update_plan`, would survive into the next turn although its turn failed.
- *Record a failure of the properties fetch too* — rejected by the user. It would need the 409
  check and `PrepState` loading moved ahead of the fetch, for a failure that is rare and that the
  next turn recovers from by reading the latest earlier state.

### D22. A turn never fails once its report is written

A report costs a whole research run. Once the report loop has settled a draft, the turn completes
without a protocol error, whatever fails after that point; only a cancellation still ends it.
Through StatGPT this decides whether the user gets the report at all. StatGPT buffers Deep
Research's answer and shows it as the report only when the stream ends without an error and the
state it carries says `research_started`; an answer without that state it reads as a
clarification (`statgpt/app/chains/deep_research/deep_research_tool.py`, `DeepResearchRunner.run`
and `_research_started`, read in the backend repository).

What runs after the draft is settled, and how each step absorbs its failure:

| Step | On a failure |
|---|---|
| The citation step's three passes | Already absorbed: each keeps what the passes before it finished (`_run_citation_step`). |
| Anything else in the citation step, outside those passes | Caught in `_deliver_report`, which holds only the settled draft: the draft is appended as the review settled it. |
| Appending the report | Caught: one WARNING. The report does not reach the user, yet the state saved next closes the conversation. Accepted: only a closed choice or a bug makes `append_content` raise (`aidial_sdk/chat_completion/choice.py`). |
| Sending the annotations | Already absorbed: the tags show as plain text (`_send_annotations`). |
| Writing the citation log record | Caught: one WARNING. |
| Saving the state (`_persist`): the image upload | A bucket lookup (`dial.bucket.get_raw()`) that raises is one failure, logged once: every image then gets the existing upload-failure placeholder, as one failed upload does today. The state is saved with `research_started` set, so the conversation closes like any other whose report was delivered. |
| Saving the state: building the state dict (`DialState(...).to_dict()`) and `set_state` | Caught: one WARNING, and the turn still completes. Nothing is persisted. `set_state` can raise because the SDK serializes the chunk with `json.dumps` when it is sent. |

**The bucket lookup has two callers that treat its failure differently.** The final save of a
turn's `messages` replaces every image with a placeholder. The save of a failed research turn's
snapshot re-raises it, so the snapshot is dropped and the failure record saved instead (D21),
because a snapshot with placeholders would resume research without its images. `upload_image_blocks`
therefore takes a parameter that says which of the two its caller wants, or the caller resolves
the bucket and passes it in.

Each caught failure logs one WARNING naming the step, and no ERROR, because the turn completes
(**logging-policy** delta). The turn's "request completed" record carries `outcome=completed`.

Consequences:

- D4 has no delivery case, and no snapshot ever has a delivery resume point.
- A resumed run cannot fail after its report, so an older resumable snapshot is never left behind
  for a report the user already has, except when the state write itself fails (Risks).

Alternatives:

- *Persist nothing when a step after the report fails, and deliver the error* — rejected by the
  user. The report would be lost through StatGPT, and through DIAL Chat the conversation would stay
  open with the older snapshot resumable, so a "continue" would redo delivered work.
- *Save the snapshot on such a failure and resume the delivery step* — rejected. It is more work for
  a failure that the steps can simply absorb, and it is post-MVP in the feature design.

## No changes required

- **`app/research/nodes.py`.** Every node reads its inputs from the state, so it cannot tell a
  resumed run from a fresh one. The report loop keeps absorbing its failures as it does today.
- **`app/research/middleware.py`.** `IterationCounterMiddleware` reads `research_iteration` from
  the state, so a resumed iteration ends at the right count.
- **`app/middleware.py` (image budget) and `app/tool_failures.py`.** Both recompute their counts
  from the messages on every call.
- **`app/research/data_queries.py`.** `DataQueryRecord` already dumps and validates by alias, and
  the runner restores into `DataQueryStore.records` (D17).
- **`app/preparation/agent.py` and `app/preparation/runner.py`.** The agent takes its history from
  `reconstruct_history`, whose signature does not change (D14). The middleware that stops after
  `start_research` is unchanged.
- **`app/turn_lifecycle.py`.** `raise_dial_error` is unchanged. A state set before the raise
  reaches the client ahead of the error chunk.
- **The 409 check in `app/completion.py`.** It reads `research_started`, which a failed turn
  persists as false.
- **`load_last_prep_state` and `DialState.from_dict`.** `DialState` reads only `messages` and
  `preparation`, so the snapshot key and the failure-flag key are ignored, unless the flag becomes a
  defaulted field of `DialState` (D21). `PrepState` ignores unknown fields, so a rollback reads the
  new `plan_id` harmlessly. `load_last_prep_state` is also what the failure record uses to read the
  `PrepState` the turn started from (D21).
- **`utils/llm.py`.** The OpenAI client's `max_retries=3` stays (Non-Goals).
- **`app_properties.py`, `dial_conf/core/applications-template.json`,
  `docs/generated-app-schema.json`, the README environment-variables table.** There is no new
  property or environment variable.

## Risks / Trade-offs

- **[A cancellation or a killed pod saves nothing]** → This is accepted and stated in the spec. The
  user sees research start from zero, as today.
- **[A content-filter hit on the model's output loses its resume]** → D20 cannot tell an output
  hit, which a new attempt might pass, from an input hit, which it would not. Both save a snapshot
  that is never resumed. This is accepted: such hits are rare in a research run, and research
  restarts from zero, as today.
- **[A future retry mechanism retries every exception]** → It would bring back the endless
  "continue" that D20 prevents. D20 is written as a standing rule, and the predicate's code comment
  points at it.
- **["Try again" in DIAL Chat drops the failed answer with its snapshot]** → Research restarts from
  zero, or resumes from an older snapshot when one is left in the history. Nothing is built for it
  in this change (Non-Goals).
- **["Try again" after a non-resumable failure replays the run that failed]** → It drops the latest
  failed answer and its non-resumable snapshot, so an older resumable snapshot of the same plan
  becomes the latest again, and the next run resumes into the failure D20 records. This is
  accepted: the user asked for that retry explicitly.
- **[Recording the same plan again restarts research]** → Every `update_plan` renews the id. That
  can happen, for example, when the approval reviewer calls the recorded plan stale. The discarded
  stage and its INFO record make this visible.
- **[The model skips `approve_plan` on "continue"]** → `start_research`'s gate refuses, and the
  agent asks the user to confirm. That costs one extra turn, not progress. The note's instruction
  to call `approve_plan`, then `start_research` makes it rare.
- **[The note's conditional wording is untested]** → The proof of concept tested only an
  unconditional instruction. The wording is tested in the end-to-end runs (Open Questions).
- **[The conversation grows]** → Each failed research answer carries one research transcript, up to
  about a megabyte, and a non-resumable one is often the largest, because a context overflow means
  the transcript is huge. Through StatGPT the growth multiplies: StatGPT keeps every snapshot in its
  session and copies the whole session into every later answer until the report is delivered, so a
  request carries roughly the session's size once per StatGPT answer since the first failure. For
  example (inferred, not measured), three snapshots of about 1 MB make a session of about 3 MB,
  and about 20 answers after the first failure bring the history to DIAL Core's 64 MiB limit. From
  then on Core rejects every request of that conversation with 413, and the conversation cannot
  continue. This is accepted: there is no size guard (Non-Goals), and StatGPT keeps all snapshots.
- **[A resumed run that fails at its first call saves a near-duplicate]** → Its first streamed
  state is the restored one, so the new snapshot nearly equals the one it started from, up to about
  a megabyte more in the conversation. This is accepted.
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
- **[The state write fails after the report]** → The turn completes (D22), but nothing is
  persisted. Through DIAL Chat the report is shown, and the next turn reads the latest earlier
  state, so the conversation stays open, and a "continue" may resume an older snapshot. Through
  StatGPT the answer carries no state, so StatGPT reads the report as a clarification: it does not
  show it as the report, and it keeps the session open. This is accepted: it needs building the
  state or `set_state` itself to fail, for example when the SDK's `json.dumps` of the state raises.
- **[The transcript's tool artifacts can still meet the `index` merge]** → This is today's exposure
  under `messages`, unchanged. Only non-streaming callers are affected.

## Migration Plan

- **No data migration.** Old conversations carry no snapshot. A plan recorded before the deploy
  gets a `plan_id` when its research starts (D7).
- **Deploy order is free.** The StatGPT backend change acts only when Deep Research sends a state
  with its error. Before it lands, StatGPT discards the snapshot and "continue" restarts research,
  as today. Through DIAL Chat, the resume works as soon as this change ships.
- **Rollback.** Older code ignores the snapshot key, the failure-flag key and `plan_id`. The failed
  answer's reset `PrepState` lets "continue" approve and restart research from zero. Redeploying
  this change makes a pending snapshot resumable again, as long as the format version is unchanged.
- **Verification during implementation.** Two unit tests use a real compiled research graph with
  a fake model:
  - **Capture.** The fake model raises on its third call. The test asserts the captured resume point
    and transcript, which checks D3 against LangGraph's real event order: clearing on
    research-agent's start, the namespace match, dropping the trailing model message.
  - **Resume.** It resumes from that snapshot and asserts that only the failed model call runs again
    and that `research_iteration` comes out right.

  A manual run on the local stack injects a quota error and resumes through DIAL Chat.

## Open Questions

- **The two Claude deployments and a mid-history system message.** Test on an environment that
  serves them. The answer changes neither the specs nor the approach; a deployment that rejects the
  message would need its own adapter fix.
- **The note's exact wording.** It may be tuned after end-to-end runs through StatGPT with a real
  channel, including its conditional instruction (D14). The spec fixes what the note says, not its
  words.
- **The error texts' exact wording.** The spec fixes that each text states what happened and which
  advice it drops (D20); the final words are a product decision.
