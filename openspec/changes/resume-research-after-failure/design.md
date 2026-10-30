## Context

See `proposal.md` (Why) for the motivation. This section covers only the current mechanics the
design builds on.

**How a turn persists today.**

- `DeepResearchCompletion._run_turn` (`app/completion.py`) rebuilds `CrossTurnPrepState` from the latest
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
  ends. This change replaces both with a node function that runs the agent and counts the
  iteration (D24).
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
- A resumed run is a normal run seeded differently. No node can tell the two apart, and the resume
  code only loads the saved state and re-enters at the saved node; it derives nothing.
- Every research turn whose graph started saves one research record, whether the run failed or
  succeeded. The record keeps every response of the research graph's models whole, so what
  happened in a run can be read without DIAL stages or traces. Model inputs are never stored.
- The preparation agent and both preparation checks learn of the failure only from the fixed
  note. They never receive the research transcript, its images or any error text. The
  preparation agent's history holds only earlier preparation-agent messages and no images.

**Non-Goals:**

Each item below is out of scope for this change and is planned, where it is planned at all, as its
own later change.

- **Saving on a cancellation or a killed pod.** Stop, a client disconnect, DIAL Core's idle timeout
  and a pod restart save nothing. Covering them needs state sent while research runs, which the
  SDK's one-write rule forbids today.
- **Uploading images as they arrive.** A failed run's images are uploaded at save time (D16).
  Uploading during the run, with a hash-to-URL map, would make a failed turn's save fast.
- **Passing research-review's response on.** Research-review's assessment is stored but read by no
  node. Passing it to research-agent, showing earlier responses to research-review, and running
  research-review over research-agent's prompt prefix are tracked in
  epam/ai-dial-deep-research-backend issues #116, #121 and #120. Each changes an LLM call's input
  and needs its own eval run.
- **Follow-up messages after a delivered report.** The next request is refused (D22), and the
  design does not account for a later turn that reads a completed run's record.
- **Migrating states saved before this change.** An old state keeps its `messages` key, and this
  code ignores it (Migration Plan).
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

- *Wrap each node to record its start* — rejected. A wrapper that records node starts would couple
  the graph to the runner, and the `tasks` stream already reports each start. research-agent does
  run inside a node function (D24), but that function maps the agent's state and records nothing
  for the runner; the agent's parts keep their namespace under it.
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

1. **A snapshot refusal** (D13). The turn persists
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
  coordinator holds the preparation messages and `CrossTurnPrepState`.

### D5. A failure before the graph streamed any state saves no snapshot

This covers an MCP server that cannot be reached while the tools load, and a snapshot image that
still cannot be downloaded after its attempts (not a 404, D16). The turn persists only the failure
record (D21).

- **On a fresh run** there is no progress to save.
- **On a resumed run** the snapshot the run started from stays the latest one in the history, and
  its plan id still matches, because the failure record carries the `CrossTurnPrepState` the turn started
  from. The next request to continue resumes from it.
- **The failed-turn note** still follows the latest failed answer, because the note is triggered by
  the failure flag (D14), not by a snapshot.

Alternatives:

- *Save the state the run started from as the snapshot*: the initial state on a fresh run, or the
  snapshot as read on a resumed run — rejected. It only kept the note after the latest failed
  answer, which the failure flag now does, and on a resumed run it copied up to about a megabyte.
- *Rebuild the snapshot from the partly rehydrated state* — rejected. It would re-upload images that
  are already stored under the same names, and gain nothing.

### D6. The state's shape: a preparation part and a research part

A turn's `custom_content.state` has three top-level keys. The preparation graph and the research
graph each own one, so neither graph's messages are mixed into the other's.

```json
{
  "preparation": {
    "research_started": false,
    "plan_approved": false,
    "agent_messages": [],
    "query_reviews": [],
    "plan_reviews": []
  },
  "research": {
    "plan_id": "…",
    "resumable": true,
    "not_resumable_reason": null,
    "version": 1,
    "resume_at": "report",
    "research_query": "…",
    "approved_plan": [],
    "research_agent_messages": [],
    "research_reviews": [],
    "reports": [],
    "report_reviews": []
  },
  "turn_failed": true
}
```

The example is a failed run's snapshot: the flags are reset and the failure flag is set. A completed
run's state keeps the `CrossTurnPrepState` flags as preparation left them, holds a record with `resumable`
false, the reason `completed` and no `resume_at`, and carries no failure flag.

The example shows two of `CrossTurnPrepState`'s fields and leaves out some research fields (D11).

- **`preparation`** keeps every `CrossTurnPrepState` field directly under it, as today, because StatGPT
  reads `preparation.research_started` and marks that read as a contract
  (`statgpt/app/chains/deep_research/deep_research_tool.py`, read in the backend repository). Three
  keys sit next to those fields:
  - `agent_messages`: the preparation agent's model replies and tool results of this turn, as
    `messages_to_dict` writes them. It holds no user message, because the request carries those,
    and no earlier turn. It never holds an image, because the preparation agent has no MCP tools.
  - `query_reviews`: every `QueryReviewResponse` of this turn's query clarity checks, whole. The
    query review runs on every `update_query`, so it is a list.
  - `plan_reviews`: every `PlanReviewResponse` of this turn's plan approval checks, whole. It runs
    on every `approve_plan`, so it is a list too.

  The two review lists are for observability only, and no part of the app reads them. The tool
  results in `agent_messages` keep only the part of a review that reaches the agent: the clarifying
  questions, or the approval's failure reason.
- **`research`** is the research record (D11). Every research turn whose graph streamed state saves
  one. A failed run's record is the snapshot a later turn may resume. A successful run's record is
  marked not resumable with the reason `completed` (D20). A turn without research has no `research`
  key.
- **`turn_failed`** is the failure flag (D21). It stays at the top level, because a turn can also
  fail in preparation, with no research at all.

A failed research turn's `preparation` holds a copy of `CrossTurnPrepState` with `plan_approved` and
`research_started` false. Any other failed turn persists the failure record of D21 instead.

Supporting choices:

- **The three key constants live in `app/history.py`.** `PreparationDialState` models only the
  value under `preparation`, and `create_dial_state` is the one place that lays out the three
  top-level keys. The flag never goes into `CrossTurnPrepState`: every turn loads `CrossTurnPrepState` and persists
  it again, so a flag there would be copied into the next successful turn.
- **The research record is parsed by its own reader, never through `PreparationDialState`.**
  `PreparationDialState.from_dict` receives only the value under `preparation`, so a record this
  code cannot read never makes the turn's `CrossTurnPrepState` unreadable.
- **Only model outputs are stored, never model inputs.** The state lives in the user's
  conversation, which the user can download and share. Model inputs carry the system prompts and
  the client rules of the application properties, which must not reach the user. The inputs can be
  rebuilt from the transcript and the configuration.

Alternatives:

- *Keep one `messages` key holding the preparation messages and the research transcript* —
  rejected. The preparation agent would receive every earlier research transcript with its images,
  often several hundred kilobytes, and the approval check would read research chatter as
  conversation.
- *Nest `CrossTurnPrepState` under `preparation.state`* — rejected. It would break StatGPT's read of
  `preparation.research_started` and need a coordinated deploy.
- *One `preparation_reviews` list for both checks* — rejected for two lists named after the check,
  which say what each entry is without a type field.
- *Make the research record a typed field of `PreparationDialState`* — rejected. A record that fails
  validation would fail `_parse_dial_state`. `load_last_prep_state` would then fall back to an older
  state or a fresh one, and the recorded plan would be lost.

### D7. `CrossTurnPrepState.plan_id`, a fresh id per recorded plan

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

### D9. Only the latest research record in the history is considered

The search walks `request.messages` backwards to the latest assistant message whose state carries
the `research` key. It looks past later assistant messages that carry none:

- **Preparation-only turns after the failed turn**, such as a question before the user asks to
  continue. The plan id then decides (D13): a newly recorded plan discards the record.
- **A failed turn that saved only its failure record**: a failure in preparation, a failure before
  the graph streamed any state (D5), or a failed run whose snapshot state could not be built or
  encoded (D23). The walk reaches the previous snapshot and resumes from it. For the last case this
  is a fallback to older progress, kept on purpose: rerunning research from the start would lose
  more.

A turn that delivered its report is never resumed. The next request is refused with 409 before the
history is rebuilt (D22), so no search runs.

- *Search for any snapshot with a matching id* — not needed. Ids are only ever replaced by fresh
  ones, so when the latest record's id differs from the current one, no older record can match.
  A rewind removes later answers from the request, and their records with them.
- *Fall back past a record that is not resumable to an older resumable one* — rejected. Such a
  record hides every older one, whatever its reason (D20), and research reruns from the start; the
  new turn's own record then becomes the latest. For a failure a resume would repeat, a fallback
  would replay that failure on every "continue". For a missing image, it would gain some progress at
  the cost of a second rule. One rule is simpler.
- *Copy the snapshot forward into every later answer* — rejected. Copying would add up to about a
  megabyte to every answer, and DIAL Chat and StatGPT already send every earlier answer.

### D10. A conditional edge from `START`, with a router closed over the entry node

`build_research_graph` takes the entry node, defaulting to research-agent. It adds
`add_conditional_edges(START, route_from_start(entry), path_map={…four nodes…})`, in the same
factory style as the four `route_after_*` routers. With the default, the two tests that build the
graph from keyword arguments (`tests/test_report_loop_graph.py`,
`tests/test_research_review_stage.py`) need no change for the entry; they change for the renamed
state fields (task 14.4).

Alternatives:

- *A plain edge from `START` to the entry chosen at build time*, as the proof of concept did —
  rejected. The compiled graph's shape would differ from turn to turn. The drawn graph, and a test
  of the graph's edges, would see only one entry.
- *A `resume_at` channel in `ResearchState` read by the router* — rejected. It would put a
  persisted-format value into every node's state and into research-agent's input schema, and no
  node needs it.

### D11. The research record and the research state it mirrors

`ResearchSnapshot` is a pydantic model in a new `app/research/snapshot.py`, with
`extra="ignore"`. It is the research record of D6: a failed run's record is the snapshot, and a
successful run's record has the same shape. Its header:

- `plan_id: str`
- `resumable: bool`
- `not_resumable_reason: NotResumableReason | None`, a `StrEnum` of `completed`,
  `repeating_failure` and `image_upload_failed` (D20), `None` when `resumable` is true
- `version: int`
- `resume_at: ResumePoint | None`, a `StrEnum` of `research`, `research_review`, `report`,
  `report_review`; `None` for a completed run's record, which names no node to re-enter

The rest mirrors `ResearchState`, field for field:

| Field | What it holds | Who reads it while the graph runs |
|---|---|---|
| `research_query` | The query as preparation finalized it (`CrossTurnPrepState.current_query`). | Research-review's prompt, the writer's request, and the review request both reviews share. |
| `approved_plan` | The plan the user approved. | The plan list in research-review's prompt and the writer's request; the review request. |
| `research_agent_messages` | Research-agent's conversation: the first instruction, its model replies and tool results, and the instruction for each further iteration. | Research-agent, the status tool, research-review's findings, the writer, report-review's glossary results and the grounded review. |
| `research_iteration` | How many research iterations finished. | Research-agent's node function, which counts it (D24), research-review's budget and the two routers after research-agent and research-review. |
| `research_reviews` | Each research-review response, a whole `ResearchReview`, in order. | Its next steps feed the plan list and the routing after research-review. Nothing reads the assessment. |
| `reports` | Each draft, in order, as the writer wrote it. The delivered text, after the citation step, is kept only in the assistant content. | The writer (the previous draft), report-review (the draft under review), the router after the writer (the version budget), and the runner (the delivered draft). |
| `report_reviews` | One entry per report-review round: the draft number, `rule_violations` (what the seven app rules found), `blind_review` and `grounded_review` (each call's response, `null` when the call failed; a grounded review that answered with no text counts as failed). Items are derived only from responses that are present, so a stored value is never parsed into an error and an absent blind review never reads as an approval. | The writer (its revision instruction) and the router after report-review. |
| `report_revision_failed` | Whether the latest revision's model call failed. | The router after the writer. |
| `data_queries` | The turn's data-query records, as one string (D12). | The data-query report rule and the citation step, through the runner's store. |

The research-agent model call gets the query and the approved plan from its first instruction, not
from the fields. Research-agent receives only research-review's next steps, wrapped in the fixed
instruction; the whole response stays in `research_reviews`.

**Values derived from these fields are derived by the node that reads them, on every run.**
Resume code derives nothing, so a fresh and a resumed run take the same code path:

- The plan list, "Plan 1:, Plan 2:, …", is built from `approved_plan`, then the next steps of each
  entry of `research_reviews` that returned some. Each later plan is therefore exactly the next
  steps research-agent was given, and no assessment appears in it.
- The routing after research-review counts the plans as 1 plus the number of reviews that returned
  next steps.
- The draft number is the length of `reports`, and the latest draft is its last entry.
- The writer builds its revision instruction from the latest `report_reviews` entry only: the
  rule violations, then the blind review's violations, then the grounded review's items. A failed
  call contributes nothing, as it does today. The writer still sees only the previous draft and
  that one instruction, never earlier drafts or earlier rounds.
- The app rules' violations are saved as the review measured them. The writer never runs the rules
  again: three of them depend on lookups through DIAL and the MCP servers, which can fail or answer
  differently on a later turn.

The report node's comment that a rejected draft is "never re-sent to a model nor persisted"
(`app/research/nodes.py`, the report node's return) is rewritten: drafts are persisted in
`reports`, and only "never re-sent to a model" holds, because no node reads an earlier draft.

The module also builds the resumed `ResearchState`. `state.py` gets the thin
`build_resumed_state` beside `build_initial_state`.

Supporting choices:

- **A stable header.** `plan_id`, `resumable` and `version` keep their names and meaning in every
  format version, so any release can decide whether a record is to be resumed before it reads the
  rest (D13). `not_resumable_reason` is read only to show it; a record that is not resumable is
  discarded whatever its reason.
- **Typed fields restore typed values.** `research_reviews`, `reports` and `report_reviews` are
  declared with their models, for example `list[ResearchReview]`, so `model_validate` turns the
  stored dicts back into the same models a fresh run holds. Without that, a resumed run would hold
  dicts where a fresh run holds models, and an attribute read such as `review.next_steps` would
  fail only on resume. A field added to one of these models later needs a default, or older
  records fail validation and are refused (D13).
- **`SNAPSHOT_VERSION` follows its rule and stays 1.** The format has not been released, so the
  field renames and the new fields are part of version 1.
- **One mapping table.** It translates `ResumePoint` to node names in one place, used by the
  snapshot builder and by the router. Persisted data therefore never names a graph node, and
  renaming a node does not break a pending resume.
- **The fields mirror `ResearchState`.** A unit test asserts that the record has a field for every
  `ResearchState` key. Adding a field to the state without updating the record then fails a test
  instead of silently resuming with a missing field.
- **Stage facts are derived when the record is read.** The restored model calls of the interrupted
  iteration are the `AIMessage`s after the last `HumanMessage`. The report-review round is the length of `reports`.

Alternatives:

- *Keep the reviews and drafts in a separate list next to the resume values* — rejected. The latest
  draft and the next steps would be stored twice, and the two copies could disagree.
- *Rebuild the resume values from an append-only list of model responses* — rejected. Several
  values are not model responses (`research_iteration`, the rule violations,
  `report_revision_failed`, the data-query records). The image budget also replaces a tool result
  in place under its message id, which an append-only list would not show.
- *Keep `plans` beside `research_reviews`* — rejected. The next steps would be stored twice.
- *Store node names* — rejected. It couples persisted data to graph internals.
- *Store the count of restored model calls*, as the proof of concept did — rejected. It duplicates a fact the
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

The transcript's tool artifacts keep the exposure a persisted tool result has always had: they
stay plain JSON in `research_agent_messages`.

### D13. Reading a snapshot, and refusing one this code cannot read

The reader works in this order:

1. Take the raw dict.
2. Read `plan_id`. If it is not a string, raise `SnapshotUnreadableError`. If it differs from the
   current id, discard the snapshot (D19) with the reason `plan_changed`, without reading further.
   The discard stage and record show the snapshot's `resume_at` only when it reads as a known
   `ResumePoint`, and its `not_resumable_reason` only when it reads as a known reason, because
   neither is part of the stable header and another release may write a value this code does
   not know.
3. Read `resumable`. If it is not a boolean, raise `SnapshotUnreadableError`. If it is false,
   discard the snapshot with the reason `not_resumable`, without reading further. Reading it before
   `version` means a non-resumable snapshot of another format version is discarded, not refused.
4. Read `version`. If it is not this code's version, raise `SnapshotVersionUnsupportedError`.
5. Validate the model, which restores the review and draft models (D11), decode
   `research_agent_messages` with `messages_from_dict`, and decode `data_queries`. If any of these
   fails, raise `SnapshotUnreadableError` from the original exception, so the turn's
   ERROR record carries both stack traces.

Both errors are `AppConditionError` subclasses in `app/error_resolution.py`, with the curated
texts the spec requires. `SnapshotVersionUnsupportedError` is outgoing 409, non-retryable.
`SnapshotUnreadableError` is outgoing 500, non-retryable. A refusal persists only the failure
record (D21), which carries the `CrossTurnPrepState` the turn started from and so keeps the plan id: the same
snapshot stays the latest one and still matches, and the refusal repeats. A snapshot image that
answers 404 is not a refusal: the snapshot is discarded and research runs fresh (D16). A third
subclass, `SnapshotImageUnavailableError`, is retryable (D16).

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

`reconstruct_prep_agent_history` (this change renames `reconstruct_history`, because the function
builds only the preparation agent's history) reads each earlier assistant message's
`preparation.agent_messages`, never its `research` record. A state without that field, such as one
saved before this change, parses with an empty list and falls back to one `AIMessage` of the
message's native `content`, as a turn without state does. A state that fails validation takes the
existing fallback of `_parse_dial_state`: one WARNING and the native `content`. No image is ever
downloaded, so `rehydrate_image_blocks` has no caller and is removed.

The function appends one fixed note after every assistant message whose state carries the
failure flag (D21): after its decoded agent messages, or after the fallback `AIMessage` of its
native `content` when they are empty. It reads nothing of a research record and needs no
parameter.
`_format_conversation` (`app/preparation/tools.py`) renders a system message as a `System note: …`
line instead of dropping it. The text lives in `app/preparation/prompts.py`, as a triple-quoted
constant.

Why every failed turn needs the note: a failed research turn persists its preparation messages,
which end with `start_research`'s "Research has started… your turn is over" result. Without a note
after it, the agent reads research as still running. A failed turn without a snapshot reads as an
empty or partial answer, and without a note the agent cannot tell that it failed.

The note does not say whether progress was saved; the coordinator alone decides whether to resume
(D8, D9). It does not say that the approval was reset either: after a preparation failure the
failure record keeps the `CrossTurnPrepState` the turn started from, which may still have the plan approved.
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

- *A `CrossTurnPrepState` flag* — rejected. Every turn loads `CrossTurnPrepState` and persists it again, so the flag
  would be copied into the next successful turn, and it does not mark a position in the history.
- *Trigger on the snapshot's presence* — rejected. A failed turn without a snapshot, such as a
  preparation failure, would get no note.
- *Two notes, resumable and not resumable, chosen by comparing the snapshot's plan id with the
  loaded one* — rejected. It needed the plan id inside `reconstruct_prep_agent_history`, and the
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

A failed run needs its images to resume, and a successful run's images are needed by nothing in the
app. So only a failed run's record uploads images, and a successful run's record keeps none.

**The placeholder.** An image that is not stored is replaced, in its own slot of the message's
content list, by one text block of a fixed format:

```text
[image not stored: <reason>, <mime type>, sha256=<hex>]
```

The reason is `successful run` or `upload failed`. The hash is the SHA-256 of the image bytes, in
hex; an eval needs it to identify each image. Because the
placeholder keeps the image's slot, the k-th placeholder of a `ToolMessage` stands for the k-th
image of that tool call's result. The format replaces the upload-failure placeholder
`[image upload failed: …]`, so one reader recognizes both cases.

**A successful run uploads nothing.** `_persist` replaces every image block of the research record
with the `successful run` placeholder and makes no upload and no bucket lookup. No retry runs on
this path, because nothing on it goes over the network.

**A failed run uploads at save time.** The snapshot's transcript goes through `upload_image_blocks`
at save time, on a list the turn is about to discard. All images of one save are uploaded
concurrently, one request per image. The file names are the existing ones: tool call id plus block
position. A resumed run that fails again uploads the same images under the same names. Overwriting
them is inferred from `aidial_client` uploading with `PUT` and no `If-None-Match`, not verified
against DIAL Core.

- **Retries.** Each upload is tried up to four times when it fails with HTTP 500, 502, 503 or 504,
  waiting 1, 2 and then 4 s between attempts. Any other failure is not retried. `AsyncDial`'s own
  retries (408, 409, 429 and transport errors, twice per request, `aidial_client/_constants.py`)
  run inside each attempt.
- **An upload that still fails, or a bucket lookup that fails.** The image gets the `upload failed`
  placeholder, the snapshot is still saved, and it is marked not resumable with the reason
  `image_upload_failed` (D20). A resume without that image could let the report state what the
  image showed with nothing left to check it against; a correct report outranks the saved progress,
  so research reruns from the start. The snapshot is kept for debugging. A bucket lookup that fails
  gives every image the placeholder, logged once.

**Download.** A new helper in `utils/image_attachments.py` downloads each image of the snapshot's
research-agent messages, all of them concurrently. The coordinator calls it in
`_find_resumable_snapshot`, after `read_snapshot` returned a resumable snapshot and before it shows
the snapshot stage, so the stage always says what the turn does. Its outcomes:

- **HTTP 502 or 503.** Retried: up to three attempts, waiting 1 and then 2 s.
- **A 404.** `aidial_client` raises `ResourceNotFoundError` (`aidial_client/resources/files.py`).
  The file is gone for good, so it is not retried. The helper reports it, and the coordinator
  discards the snapshot with the `DiscardReason` `image_missing`: it shows the discarded stage, logs
  one WARNING and the INFO "snapshot discarded" record (D18), and research runs fresh in the same
  turn. The turn's own record then becomes the latest one. A refusal would repeat on every later
  request, because the snapshot would stay the latest record, and resuming without the image could
  make the report wrong.
- **Any other failure, or a 502 or 503 after the last attempt.** The helper raises
  `SnapshotImageUnavailableError`, a retryable `AppConditionError` with the curated "could not be
  loaded" text. The graph has not started, so D5 saves no snapshot, and the snapshot the turn
  started from stays the latest one. A later "continue" can try again.

The typed errors are needed because `aidial_client` raises its own `DialException`, which
`error_resolution._extract_error_details` does not recognize. Untyped, it would resolve to the
generic non-retryable message. The retried statuses are read from `DialException.status_code`; a
transport error that survives the client's own retries carries 500 and is not retried on download.

**Stages.** The runner adds the snapshot's message ids to `_seen_ids` before streaming. The runner
reads tool calls from the `messages` key of `updates` parts (`_handle_updates`). Under D24 the
research-agent node's own root `updates` part carries the whole list under
`research_agent_messages`, which `_handle_updates` does not read, and the agent's inner `updates`
parts carry only each step's new messages. So no part the runner reads re-sends the snapshot's
messages, and the ids are a guard: they keep the snapshot's tool calls from becoming 0.00 s stages
and INFO "Tool call completed" records, which the proof of concept observed when the agent was a
directly added node, should a later change read the root list again. The `_handle_part` and `_already_seen` docstrings say which key
they read.

Alternatives:

- *Resume a snapshot with a placeholder in place of an image* — rejected. The resumed report could
  cite a page whose image research-agent no longer sees, with nothing to show for it.
- *Drop the whole snapshot when one image cannot be uploaded* — rejected. It gives the same next
  turn, a rerun from the start, but loses the record of what the run did.
- *Upload a successful run's images too, for debugging* — rejected. No part of the app reads them,
  and the upload and its retries would delay a turn whose report is already written.
- *Retry downloads on every failure but a 404* — rejected. Only a 502 or a 503 is likely to pass on
  the next attempt; the client already retries timeouts, transport errors and 429.
- *Upload images as they arrive* — this is in Non-Goals.

### D17. The data-query records are restored before the graph runs

After `load_mcp_tools` creates the turn's `DataQueryStore`, the runner fills `records` from the
snapshot. The capture interceptor then adds and replaces records by id as it does today. Nothing in
`data_queries.py` changes.

### D18. Logging

The coordinator writes four INFO records, with the fields the **logging-policy** delta lists:

- "Snapshot saved", with `resumable` and, for a non-resumable snapshot, its
  `not_resumable_reason` and, for `repeating_failure`, the failure class (D20). It is written only
  for a failed turn; a successful run's record is part of the completed turn and gets no record of
  its own;
- "Failure recorded", for a failed turn that saved no snapshot, with the reason
  `preparation_failed`, `snapshot_refused`,
  `no_graph_state` or `snapshot_failed` (D4, D21). `preparation_failed` covers every failure
  before the research runner was created, a preparation-only turn's own failed save included. The
  coordinator creates the research runner before it looks for a snapshot, so a snapshot image that
  cannot be downloaded is recorded as `no_graph_state`, like any failure before the graph streamed
  state, never as `preparation_failed`;
- "Snapshot reused";
- "Snapshot discarded", with the reason `plan_changed`, `not_resumable` or `image_missing`. Every
  image that answered 404 also gets one WARNING. For a non-resumable
  snapshot the two plan ids are equal, so the ids alone would explain nothing. Its resume point
  appears only when it reads as a known value (D13).

A step that fails after the report is written logs one WARNING naming the step (D22). For the
final save, the WARNING also says what was saved instead: `saved=closing_state`, or
`saved=nothing` when the closing state could not be written either (D23).

Sizes are `len()` of the JSON-encoded snapshot and of the whole state. The state's size comes from
the encoding the state check of D23 already made; the snapshot is encoded on its own for its size.

A snapshot that cannot be built or saved, and a failure record that cannot be saved, each log one
WARNING with the exception class, never `logger.exception` at ERROR: one WARNING per snapshot state
or failure record that could not be saved (D23). A turn without research whose full state fails
logs no WARNING, because that failure is the turn's own error and gets its one ERROR. The single
ERROR stays with
`raise_dial_error`. Each retried image download, and each retried image upload of a snapshot, logs
one WARNING with the attempt number and the exception class, a download also with the URL stripped
by the existing `_strip_url_query`. An upload whose last attempt fails logs one WARNING, because it
costs only the resume (D16).

### D19. The snapshot stage comes from the coordinator

The coordinator emits the "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage
as a closed stage, before the runner opens its first activity stage. It carries the same facts as
the INFO record, the discard reason included. StatGPT shows Deep Research's stages only in debug
mode by default (`stages_config.debug_only`), so no setting is added here.

### D20. Failures a resume would repeat save a snapshot that is never resumed

A record that is not resumable says why in `not_resumable_reason` (D11). There are three reasons:

| Reason | Set when |
|---|---|
| `completed` | The run delivered its report. Nothing is left to resume, and the next request is refused anyway (D22). |
| `repeating_failure` | The run failed in one of the classes below, which a resume would repeat. |
| `image_upload_failed` | An image of the snapshot could not be uploaded, or the files bucket could not be resolved (D16). |

Whatever the reason, the record is discarded when research next starts, and research reruns from the
start; no older record is considered (D9). A failure of more than one kind sets
`repeating_failure`, because it says the most about what went wrong. The rest of this decision is
about `repeating_failure`.

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
- **The plan id stays.** Nothing is cleared, so `CrossTurnPrepState` keeps P, and a later fresh run of the
  same plan can itself save a resumable snapshot for P.
- **The failed turn persists as any failed research turn.** It saves its `preparation` part with
  the reset `CrossTurnPrepState`, its `research` record and the failure flag (D6, D21), and gets the same
  note as any failed turn (D14).

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
  as a defaulted field of `PreparationDialState`. Never in `CrossTurnPrepState` (D6).
- **The failure record.** A failed turn without a snapshot persists a `preparation` part holding
  the `CrossTurnPrepState` read from the request with `load_last_prep_state(request)` and empty
  `agent_messages`, `query_reviews` and `plan_reviews`, no `research` record, and the flag. The
  preparation runner mutates the loaded `CrossTurnPrepState` in place, so the record reads it again from the
  request rather than taking the live object. A failed research turn with a snapshot persists the
  parts of D6 instead, and falls back to the failure record when its snapshot state cannot be built
  or encoded (D23).
- **What persists nothing.** A failure while the application properties are fetched or validated,
  which comes before the `try` (D4); a cancellation; a non-streaming request (the SDK drops the
  state); and the 409 refusal of a conversation whose report was delivered. A failure after the
  report is written does not fail the turn at all (D22).
- **Saving never hides the failure.** Building and saving the snapshot run inside a `try`. An image
  that cannot be uploaded does not raise here: it marks the snapshot not resumable (D16). When
  building or encoding the snapshot state raises, the turn drops the snapshot, persists the failure
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
- *Persist the live `CrossTurnPrepState` of the failed turn* — rejected. A tool call that ran before the
  failure, such as an `update_plan`, would survive into the next turn although its turn failed.
- *Once preparation finished, persist the turn's preparation messages and its reset `CrossTurnPrepState`
  instead* — rejected by the user. Its gain would be to keep a plan the failed turn re-recorded
  after `approve_plan` reported the recorded one as stale. Without it, the next turn recovers: the
  approval check reports the plan as stale again and the agent re-records it. The gain is rare,
  and the cost is a fifth state and a third fallback step in D23.
- *Record a failure of the properties fetch too* — rejected by the user. It would need the 409
  check and `CrossTurnPrepState` loading moved ahead of the fetch, for a failure that is rare and that the
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
| Saving the state (`_persist`): the images | Nothing can fail: every image of the research record gets the `successful run` placeholder, with no upload and no bucket lookup (D16). |
| Saving the state: building the state dict and checking that it serializes | Caught: one WARNING, and the turn still completes. The closing state is saved instead (D23): a `preparation` part with the turn's `CrossTurnPrepState` with `research_started` set and nothing else, no `research` record, and no failure flag. The next request is refused with 409, and StatGPT reads `research_started` and shows the answer as the report. |
| Saving the state: `set_state` | After the check of D23, it raises only on a closed choice, which takes no state at all. Caught: one WARNING, and nothing is persisted. |

Each caught failure logs one WARNING naming the step, and no ERROR, because the turn completes
(**logging-policy** delta). The turn's "request completed" record carries `outcome=completed`.

Consequences:

- D4 has no delivery case, and no snapshot ever has a delivery resume point.
- A resumed run cannot fail after its report, so an older resumable snapshot is never left behind
  for a report the user already has, except when the choice is closed before the state is written
  (Risks).

Alternatives:

- *Persist nothing when the final save fails* — rejected by the user. Through DIAL Chat the
  conversation would stay open with an older snapshot resumable, so a "continue" would pay for the
  same research again, and through StatGPT the report would not be shown as a report.
- *Persist nothing when a step after the report fails, and deliver the error* — rejected by the
  user. The report would be lost through StatGPT, and through DIAL Chat the conversation would stay
  open with the older snapshot resumable, so a "continue" would redo delivered work.
- *Save the snapshot on such a failure and resume the delivery step* — rejected. It is more work for
  a failure that the steps can simply absorb, and it is post-MVP in the feature design.

### D23. Every state is checked before the turn's one write, and a state that fails falls back

The SDK allows one `set_state` per turn, and `set_state` marks the state as submitted before it
serializes it: it sets `_state_submitted` and only then calls `send_chunk`, whose debug log runs
`json.dumps` on the chunk (`aidial_sdk/chat_completion/choice.py`, lines 164 and 68). A state that
cannot be serialized therefore uses up the write and saves nothing. So the coordinator encodes
every candidate state first, and calls `set_state` only with a state that encoded. The SDK encodes
the chunk again when it sends the response: with a plain `json.dumps` on a streaming request
(`aidial_sdk/utils/streaming.py`, line 40), and through Starlette's `JSONResponse` on a
non-streaming one (`aidial_sdk/application.py`, line 286), which renders with
`ensure_ascii=False, allow_nan=False` and then encodes the text as UTF-8
(`starlette/responses.py`, `JSONResponse.render`). The check encodes the same way as that render,
the strictest of these encoders, so a state that passed the check passes all of them: a `NaN`
from a tool result never reaches a client as an invalid JSON token, and a lone surrogate never
fails a non-streaming response after the report.

After the check, `set_state` raises only on a closed choice, because the turn calls it once and on
an opened choice. A closed choice takes no state at all, so no fallback can help there.

A state that cannot be built or cannot be encoded falls back to the next one in this order. The
research-resume spec owns the four states and this order ("A turn's one state write falls back in
a fixed order").

The four states, in the shape of D6:

| State | `preparation` | `research` | `turn_failed` |
|---|---|---|---|
| Full state | The turn's `CrossTurnPrepState` as it is, its agent messages and its reviews. | When research ran: the completed run's record, not resumable with reason `completed`, images as placeholders. | No. |
| Closing state | The turn's `CrossTurnPrepState` with `research_started` set, nothing else. | None. | No. |
| Snapshot state | The turn's `CrossTurnPrepState` with `plan_approved` and `research_started` reset, its agent messages and its reviews. | The failed run's record. | Yes. |
| Failure record | The `CrossTurnPrepState` the request's history held when the turn started, nothing else. | None. | Yes. |

| Turn | Candidate states, in order |
|---|---|
| The report was written | The full state, then the closing state. |
| The turn completed without research | The full state. When it fails, the turn fails and saves the failure record (D21). |
| Research failed after its graph streamed state | The snapshot state (D6), then the failure record (D21). |
| The turn failed in any other way | The failure record. |

**The closing state** is the final save of a turn whose report was written, without its research
record: only its `CrossTurnPrepState` with `research_started` set, and no failure flag. Its `CrossTurnPrepState`
encodes as any turn's does. It closes the conversation as the full state would: the next request
is refused with 409 before the history is rebuilt, so no later turn reads the record it lacks.

Each snapshot state or failure record that cannot be saved logs one WARNING with the exception
class, and a failed final save after the report logs its one WARNING with `saved=` (D18). The
"Snapshot saved"
record takes the state's size from the encoding the check made.

Alternatives:

- *Call `set_state` and catch what it raises* — rejected. A serialization failure inside
  `set_state` has already used up the write, so no fallback could follow.
- *Save a closing state that keeps the report as one message* — rejected. No later turn reads it,
  and a state that keeps any part of the transcript can fail for the reason the full state failed.

### D24. research-agent runs inside a node function that maps its conversation

The research graph keeps research-agent's conversation in its own field, `research_agent_messages`,
and a node function runs the agent. The function calls the compiled `create_agent` graph with
`{"messages": state["research_agent_messages"]}`, returns its `messages` as
`research_agent_messages`, and returns `research_iteration` increased by one. A compiled agent added
directly as a node shares only same-named channels with its parent, and `create_agent`'s
`AgentState` fixes the conversation key as `messages`: with any other name, the agent receives an
empty conversation and nothing raises (verified with a probe on the installed `langgraph` and
`langchain`). LangGraph's guide "Use subgraphs" gives this node function, "Call a subgraph inside a
node", as the way to keep a private message history per agent.

The node function counts the iteration, the way the report node records its draft. The count goes
up only after the agent returns, so a failure mid-iteration still leaves N − 1, and a resumed run
reads N − 1 until that iteration ends. `IterationCounterMiddleware` is removed: it existed only
because the agent was added directly as a node.

Streaming is unchanged. The agent's own `values`, `updates` and `tasks` parts still arrive under the
namespace `research-agent:<task id>` and still use the key `messages` (verified with a probe that
streams with `subgraphs=True` and `version="v2"`), so the runner's capture (D3) keeps reading them as
it does. A unit test pins that namespace and key.

The node passes the execution config it receives to the agent: `agent.ainvoke(..., config=config)`.
The runner starts the research graph with `recursion_limit` set to the channel's
`max_research_graph_steps`. A nested run inherits that config implicitly when the node passes
none. But `create_agent` attaches its own config, `recursion_limit=9_999`, to the graph it
returns, and that preset wins over an inherited limit. A config passed to `ainvoke` wins over the
preset. Without it, research-agent's run would ignore the channel's step budget, and an agent that
never finishes would not be stopped. Callbacks reach the agent either way. This was verified with a
probe on the installed `langgraph` and `langchain`: a nested graph with a preset limit ran past the
parent's limit without the config, and raised `GraphRecursionError` with it. A unit test pins that
the step budget stops a research-agent that never finishes.

Alternatives:

- *Keep the graph channel named `messages`* — rejected. The name says nothing about whose messages
  they are, next to `preparation.agent_messages`.
- *Rename only the record's field and map it in the snapshot builder and `build_resumed_state`* —
  rejected. The graph and the record would then name the same list differently, and the record
  would no longer mirror the state field for field.

## No changes required

- **What the research graph's LLM calls receive.** The nodes read the renamed fields and build
  their derived values from them (D11), but every prompt carries the same text as before this
  change. The report loop keeps absorbing its failures.
- **`app/middleware.py` (image budget) and `app/tool_failures.py`.** Both recompute their counts
  from the messages on every call.
- **`app/research/data_queries.py`.** `DataQueryRecord` already dumps and validates by alias, and
  the runner restores into `DataQueryStore.records` (D17).
- **`app/preparation/agent.py`.** The middleware that stops after `start_research` is unchanged.
- **`app/turn_lifecycle.py`.** `raise_dial_error` is unchanged. A state set before the raise
  reaches the client ahead of the error chunk.
- **The 409 check in `app/completion.py`.** It reads `research_started`, which a failed turn
  persists as false.
- **StatGPT.** It reads only `preparation.research_started`, which stays in place (D6). Its
  companion change keeps a failed turn's state whole without reading any other key.
- **`load_last_prep_state`.** It reads `CrossTurnPrepState` from `preparation`, whose fields stay where they
  are (D6). `CrossTurnPrepState` ignores unknown fields, so a rollback reads the new `plan_id` and the new
  sibling keys harmlessly. `load_last_prep_state` is also what the failure record uses to read the
  `CrossTurnPrepState` the turn started from (D21).
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
  which took a few seconds for a few dozen images in the proof of concept. An image whose upload
  meets a server error can add up to 7 s of waiting across its retries (D16). A resume downloads
  them before its first model call.
- **[A successful run's images are not kept]** → Debugging a completed run does not see them;
  each placeholder's hash still identifies its image. This is accepted: no part of the app reads
  them.
- **[A response model gains a required field]** → Records saved before that release fail
  validation, and a matching resumable one is refused (D13). The spec requires a default for every
  field added later to `ResearchReview` or to the report-review entry, so this happens only through
  a mistake that review should catch.
- **[A completed run's record grows the conversation]** → It carries every draft and every review
  response next to the transcript, without images. The conversation is closed after a delivered
  report: Deep Research refuses the next request before it reads the history.
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
- **[A refused snapshot blocks the conversation]** → An unreadable matching snapshot is refused on
  every request to continue. The message tells the user to
  start a new conversation, and changing the query or the plan also gets past it. A snapshot whose
  `plan_id` itself cannot be read is the exception: it counts as matching (D13), so only a new
  conversation gets past it. A snapshot whose image is gone is not refused: it is discarded, and
  research reruns in the same turn (D16).
- **[The choice is closed before the state is written after the report]** → The turn completes
  (D22), but nothing is persisted, because a closed choice takes no state (D23). The next turn
  reads the latest earlier state, so the conversation stays open, and a "continue" may resume an
  older snapshot. Through StatGPT the answer carries no state, so StatGPT does not show it as the
  report. This is accepted: a closed choice also refuses the report's content, so the report most
  likely did not reach the user either.
- **[A non-resumable snapshot that cannot be saved leaves an older resumable one]** → A resumed
  run that fails in a way a resume repeats (D20), and whose snapshot state then cannot be built or
  encoded, saves a failure record without a snapshot. The older resumable snapshot of the same plan
  stays the latest one, so the next "continue" replays the failure, which D20 exists to prevent.
  The realistic cause is a tool result holding a value the check refuses, such as a `NaN` in a
  server's structured content, which repeats on every replay. A failed image upload is not a cause:
  it marks the snapshot not resumable and still saves it (D16). This is accepted: it needs a
  repeating failure and a failed snapshot save in the same turn. Whether to replace non-finite
  floats before encoding is an open question.
- **[A closing state carries no research record]** → The conversation is closed, so no later turn
  reads it (D23). Debugging and evals lose that one turn's research record. This is accepted: it needs the full state to fail to build or encode.
- **[The transcript's tool artifacts can still meet the `index` merge]** → A persisted tool result
  has always been exposed to it, and it stays plain JSON in `research_agent_messages`. Only
  non-streaming callers are affected. A task before archiving checks whether any server sends such
  a field.

## Migration Plan

- **No data migration.** Old conversations carry no research record. A plan recorded before the
  deploy gets a `plan_id` when its research starts (D7). An old state keeps its `messages` key,
  which this code ignores: its turn has no `preparation.agent_messages`, so the preparation agent
  gets that turn's native `content` as one `AIMessage` (D14). Its `CrossTurnPrepState` reads as before,
  because the fields under `preparation` do not move.
- **Deploy order is free.** The StatGPT backend change acts only when Deep Research sends a state
  with its error. Before it lands, StatGPT discards the snapshot and "continue" restarts research,
  as today. Through DIAL Chat, the resume works as soon as this change ships.
- **Rollback.** Older code ignores the `research` key, the failure-flag key, `plan_id` and the new
  keys under `preparation`. It finds no `messages` key, so it reads each new turn as a turn without
  state and uses its native `content`. The failed answer's reset `CrossTurnPrepState` lets "continue" approve
  and restart research from zero. Redeploying this change makes a pending snapshot resumable again,
  as long as the format version is unchanged.
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
- **A guard against non-finite floats.** The strict encoding (D23) refuses a `NaN` or an infinity,
  and the MCP client keeps a literal `NaN` that a server sends in its structured content (probed on
  the installed `mcp` package). A guard would replace every non-finite float with `null` before the
  state is encoded and log one WARNING with the count. StatGPT's data-query tool sends no floats in
  its structured content, read in its source and confirmed with a live call: its values travel as
  CSV text, where a `NaN` is a string and passes the check. The guard would therefore protect only against other servers. Not
  decided.
