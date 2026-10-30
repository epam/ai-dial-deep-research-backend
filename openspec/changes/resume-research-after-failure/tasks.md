# Tasks

Decision numbers (D1–D24) refer to this change's `design.md`.

## 1. Error resolution: snapshot conditions, the resume-repeat predicate, reworded texts

- [x] 1.1 Add three `AppConditionError` subclasses to `app/error_resolution.py` (D13, D16):
  `SnapshotVersionUnsupportedError` (outgoing 409, non-retryable: the research was saved by a
  different version of Deep Research and cannot be resumed; start a new conversation),
  `SnapshotUnreadableError` (outgoing 500, non-retryable: an error on our side prevents resuming
  the research; start a new conversation) and `SnapshotImageUnavailableError` (outgoing 500,
  retryable: the saved research progress could not be loaded). Verify in
  `tests/test_error_resolution.py` that each resolves to its text, status and retryable flag and
  that only the retryable one gets the "try again later" sentence, and in
  `tests/test_error_delivery.py` that the version refusal is delivered as a 409 protocol error.
- [x] 1.2 Add the public predicate that names the failure class a resume would repeat (D20):
  `input_rejected` for the error codes `context_length_exceeded`, `truncate_prompt_error` and
  `content_filter`, and for an `openai.APIError` with status 400, 413 or 422;
  `step_budget_exhausted` for `GraphRecursionError`; none for anything else. It unwraps a
  concurrency-runtime container first and reads the code through `_extract_error_details`, so it
  and the user-facing message never disagree. Its comment states the standing rule: any later
  retry or resume mechanism consults it. Verify in `tests/test_error_resolution.py` each class, a
  context-length rejection wrapped in an exception group, a DIAL Core or `httpx` 400 that is not a
  model call (none), and a quota 429, a 502, a 503 and a timeout (none).
- [x] 1.3 Reword the texts for a context overflow, a content filter, a model 400, 413 and 422, and
  an exhausted step budget so each states what happened and holds for a preparation call and a
  research call alike (D20). Each drops one piece of advice: "shorten your messages" (context
  overflow), "rephrase your message" (content filter), "contact your administrator" (400, 422),
  "reduce the size of your message or attachments" (413) and "start a new conversation" (step
  budget). Verify in `tests/test_error_resolution.py` that
  each cause returns its new text and that none of the dropped phrases appears. The final words
  are a product decision, so list the new texts in the PR description for review.

## 2. Plan id

- [x] 2.1 Add `plan_id: str | None = None` to `CrossTurnPrepState` (`app/history.py`), and name in its
  docstring the three tools that write it. Verify in `tests/test_history_persistence.py` that a
  `preparation` dict without `plan_id` still validates and that one with it round-trips through
  `PreparationDialState`.
- [x] 2.2 In `app/preparation/tools.py`, set a fresh `uuid4().hex` in `update_plan` on every call,
  clear `plan_id` together with the plan in `update_query`, and give a plan without an id a fresh
  one in `start_research` before it sets `research_started` (D7). Verify in
  `tests/test_preparation_tools.py`: recording the same steps twice gives two different ids;
  `update_query` after a recorded plan leaves `plan_id` empty; `start_research` on an approved plan
  without an id sets one, and keeps an existing id unchanged.

## 3. Failure flag and the failed-turn note

- [x] 3.1 Add the snapshot and failure-flag state key constants to `app/history.py`, next to
  `PreparationDialState` (D6, D21). The flag lives at the top level of the state, never in `CrossTurnPrepState`, and
  `PreparationDialState.from_dict` keeps reading only `messages` and `preparation`. Verify in
  `tests/test_history_persistence.py` that `load_last_prep_state` reads the `CrossTurnPrepState` of a state
  that also carries both keys, including one whose snapshot value is not a valid snapshot.
  Revised by 14.1 and 14.3: the snapshot key is `research`, and the preparation history reads
  `preparation.agent_messages` in place of `messages`.
- [x] 3.2 Add the failed-turn note to `app/preparation/prompts.py` as a triple-quoted constant with
  the starting wording of D14. In `reconstruct_history`, append it as a `SystemMessage` after every
  assistant message whose state carries the failure flag: after its decoded `messages`, or after
  the fallback `AIMessage` of its native `content` when `messages` is empty. Reconstruction reads
  nothing of the snapshot. Update the function's docstring. Verify in
  `tests/test_history_persistence.py`: a flagged state with preparation messages and a snapshot
  gives the messages, then the note, then the next user message, with nothing of the snapshot's
  transcript and no download of its images; a flagged state with an empty `messages` gives the
  native-content `AIMessage`, then the note; an unflagged state gets no note; with several turns
  after the failed one, the note stays directly after the failed turn. Revised by 14.3: the
  failed turn's messages come from `preparation.agent_messages`.
- [x] 3.3 Make `_format_conversation` (`app/preparation/tools.py`) render the failed-turn note as a
  `System note: …` line at its position, keep dropping every other system message, tool call and
  tool result, and update its docstring. Verify in `tests/test_preparation_tools.py` that the
  conversation rendered for the clarity check and for the approval check carries the line between
  the failed turn's text and the next user message.
- [x] 3.4 Add one paragraph to `PLAN_REVIEW_SYSTEM` (D15): after a failed turn, a request to
  continue or retry approves the recorded plan only when the user approved that same plan before
  the failure, and the note by itself approves nothing. Verify in
  `tests/test_preparation_tools.py` that the rendered approval prompt carries the paragraph; the
  model's behavior is checked end to end in 12.3.

## 4. Images for snapshots and for the final save

- [x] 4.1 Let the caller of `upload_image_blocks` (`utils/image_attachments.py`) choose what a
  failed bucket lookup (`dial.bucket.get_raw()`) does (D22): for a turn's `messages`, every image
  gets the existing upload-failure placeholder and the failure is logged once, as one WARNING
  naming the save and the exception class; for a snapshot, the lookup error is re-raised. A failed
  upload of one image keeps getting one placeholder. Verify in `tests/test_image_attachments.py`
  that a raising `get_raw()` gives three images three placeholders and exactly one WARNING in the
  first mode, and raises in the second. Revised by 14.7 and 14.8: only a snapshot uploads, and a
  failed upload or bucket lookup leaves placeholders and marks the snapshot not resumable instead
  of raising; rewrite the `get_raw()` tests in `tests/test_research_resume.py` to match.
- [x] 4.2 Add the snapshot image download to `utils/image_attachments.py` (D16). It turns every
  URL-form image block of the given messages back into base64, tries each download up to
  `STREAM_DROP_MAX_ATTEMPTS` times with exponential backoff from the initial delay `utils/llm.py`
  uses, does not retry `aidial_client`'s `ResourceNotFoundError` and raises
  `SnapshotUnreadableError` for it, and raises `SnapshotImageUnavailableError` after the last
  failed attempt. Revised by 14.8: a 404 discards the snapshot instead of raising. Each failed attempt that another attempt follows logs one WARNING with the
  attempt number, the exception class and the URL stripped by `_strip_url_query`. Verify in
  `tests/test_image_attachments.py` with a fake `AsyncDial` and a patched sleep: a failure then a
  success restores the base64 and logs one WARNING; a 404 makes one request and raises
  `SnapshotUnreadableError`; three failures raise `SnapshotImageUnavailableError` after two
  WARNINGs; no record carries a query string. Revised by 14.8: only HTTP 502 and 503 are retried,
  and any other failure raises at once.
- [x] 4.3 Correct the module docstring of `utils/image_attachments.py`, which cites a 1 MB request
  body limit: every later request carries the states of all earlier turns, and DIAL Core rejects a
  request above its size limit (64 MiB by default) with 413. Verify the docstring matches the
  **dial-agent-with-mcp** delta's scenario on the request size.

## 5. Snapshot model, reader and history search

- [x] 5.1 Create `app/research/snapshot.py` with `ResumePoint` (a `StrEnum` of `research`,
  `research_review`, `report`, `report_review`), the one table that maps it to graph node names,
  the format version constant, and `ResearchSnapshot` with `extra="ignore"` and the fields of D11.
  Verify in a new `tests/test_research_resume.py`: a snapshot round-trips through
  `model_dump(mode="json")` and the reader; a field this code does not know is ignored;
  `ResearchSnapshot` has a field for every `ResearchState` key, so adding a channel without one
  fails the test.
- [x] 5.2 Store the data-query records as one JSON string (D12): `json.dumps` of
  `{query_id: record.model_dump(mode="json", by_alias=True)}` on save, `json.loads` and
  `DataQueryRecord.model_validate` on read. Verify that records whose server element holds a list
  of objects carrying an `index` key read back unchanged after the state passes through the DIAL
  SDK's chunk merge (`aidial_sdk/utils/merge_chunks.py`).
- [x] 5.3 Implement the reader in the order of D13: `plan_id` (not a string →
  `SnapshotUnreadableError`; different from the current id → discard, reason `plan_changed`), then
  `resumable` (not a boolean → `SnapshotUnreadableError`; false → discard, reason
  `not_resumable`), then `version` (not this code's → `SnapshotVersionUnsupportedError`), then the
  model, `messages_from_dict` and the data-query records (any failure → `SnapshotUnreadableError`
  raised from the original exception). A discard carries the snapshot's `resume_at` only when it
  reads as a known `ResumePoint`. Verify every branch in `tests/test_research_resume.py`,
  including: a snapshot of another plan with an unknown version and a broken body is discarded; a
  non-resumable snapshot of an unknown version is discarded; a broken body raises with
  `__cause__` set.
- [x] 5.4 Add the history search (D9): walk `request.messages` backwards to the latest assistant
  message whose state carries the snapshot key and return that raw value. Verify: a snapshot two
  answers back is found across a successful answer and across a failed turn without a snapshot; a
  newer non-resumable snapshot hides an older resumable one; a history without a snapshot gives
  none.
- [x] 5.5 Add `build_resumed_state` to `app/research/state.py` beside `build_initial_state`,
  filling every channel from a read snapshot, and derive the stage facts when a snapshot is read
  (D11): the restored model calls of the interrupted iteration (the `AIMessage`s after the last
  `HumanMessage`) for resume point research, and the report-review round (`report_version`) for report review. Verify that
  every `ResearchState` key is set and that the facts match a hand-built transcript.

## 6. Graph entry from START

- [x] 6.1 Give `build_research_graph` (`app/research/graph.py`) an entry parameter that defaults to
  research-agent, and replace the plain `START` edge with
  `add_conditional_edges(START, route_from_start(entry), path_map=…)` over the four nodes, the
  router living in `graph.py` in the factory style of the `route_after_*` routers (D10). Update the
  module docstring. Verify that `tests/test_report_loop_graph.py` and
  `tests/test_research_review_stage.py` pass unchanged, that the compiled graph has an edge from
  `START` to each of the four nodes, and that every node name in the mapping table of 5.1 is a node
  of the compiled graph.
- [x] 6.2 Update the research graph section of `docs/architecture.md`: the diagram's entry from
  `START` (research-agent on a fresh run, the snapshot's resume point on a resumed run), with a
  short excerpt and a link to the **research-execution** spec. Verify that the Mermaid diagram
  renders and that the prose names current behavior only.

## 7. Runner: capturing progress

- [x] 7.1 In `ResearchRunner` (`app/research/runner.py`), add `"tasks"` to the stream modes and
  keep: the running root node, from a root-namespace `tasks` event without `result` or `error`;
  the latest root `values` part, as today; the latest research-agent `values` part (a namespace
  starting with `research-agent`), cleared when a research-agent task starts; and whether the graph
  streamed any state (D3). Keep `_handle_part`'s docstring in line. Verify that
  `tests/test_research_dispatch.py` passes unchanged, and that a test feeding hand-built parts
  confirms the clearing and the namespace match.
- [x] 7.2 Add the runner method the coordinator calls to build the snapshot (D3, D4, D11): the
  resume point from the running node through the mapping table; the transcript from the
  research-agent part when research-agent was running and such a part exists, otherwise from the
  root part, without a trailing `AIMessage` whose tool calls have no results; the channels from
  the latest root part; the data-query records from the turn's `DataQueryStore`; and the
  `plan_id` and `resumable` mark the coordinator passes. The runner also says whether the graph
  streamed any state. Verify with a real compiled research graph and a fake model in
  `tests/test_research_resume.py`: the model raising on its third call gives resume point
  research and a transcript ending with the second tools round; a failure during a tools round
  leaves out the `AIMessage` that requested it; research-review failing after iteration 2 gives
  resume point research review and iteration count 2; the report node failing on draft 1 gives
  resume point report, no draft and draft number 0; research-agent failing in iteration N before
  its first model call gives the root transcript, ending with research-review's instruction for
  iteration N.

## 8. Runner: the resumed run

- [x] 8.1 Let `ResearchRunner.run` take an optional read snapshot. With one, before the graph
  starts: download its images with the helper of 4.2 (revised by 14.8: the coordinator downloads them
  before the snapshot stage); restore its data-query records into
  `DataQueryStore.records` right after `load_mcp_tools` (D17); add its message ids to `_seen_ids`
  (D16); then build the graph with the snapshot's resume point as entry and start it from
  `build_resumed_state`. Update `run`'s docstring. Verify with a real compiled graph and a fake
  model, resumed from the snapshot captured in 7.2 (design, Migration Plan, "Resume"): only the
  failed model call runs again, no tool call recorded in the snapshot runs again,
  `research_iteration` reads N − 1 until the iteration ends and N after it, and no tool-call stage
  and no INFO "Tool call completed" record appears for a tool call of the snapshot.
- [x] 8.2 Verify entry at the other three nodes with fake models: resume point research review runs
  research-review of iteration N first, with no research-agent call before it; resume point report
  with no draft writes draft 1 from the saved transcript; resume point report review with draft N
  runs review round N over draft N and writes no earlier draft; the iteration cap and the report
  version budget count the snapshot's iteration count and draft number.
- [x] 8.3 Verify the resumed research-agent call's input (**research-execution** delta): from a
  snapshot whose transcript holds the seed instruction and two completed model calls, one tool
  result carrying a URL-form image, the next model call receives those messages in order, the image
  as a base64 block, and none of the preparation messages or the failed-turn note.
- [x] 8.4 Verify the restored data-query records at the citation step (**report-citations**
  delta): a resumed report citing `[data_query dq_0123abcd45]`, captured before the failure,
  becomes a pill that opens its data explorer URL, and a record the resumed run captures for the
  same id replaces the restored one.

## 9. A turn never fails once its report is written

- [x] 9.1 In `ResearchRunner._deliver_report`, catch an `Exception` raised by the citation step
  outside its own passes and deliver the draft as the review settled it; catch a failure of
  `append_content` and of the citation log record, each with one WARNING naming the step and the
  exception class; a cancellation still closes the stage as failed and propagates (D22). Update
  the docstring. Verify in `tests/test_report_delivery.py` that each injected failure ends `run`
  without an exception, with one WARNING and no ERROR record.
- [x] 9.2 In `DeepResearchCompletion._persist` (`app/completion.py`), use the placeholder mode of
  4.1 for the final save, and catch a failure of building the state dict or of `set_state` with
  one WARNING naming the save, so the turn completes with nothing persisted (D22). Verify at the
  turn level: a raising `get_raw()` after a delivered report ends the turn with
  `outcome=completed`, one WARNING, no ERROR, and a state whose images are placeholders and whose
  `research_started` is set; a raising `set_state` ends the turn with `outcome=completed` and no
  state. Revised by 13.2: a failed build or encoding saves the closing state. Revised by 14.7: the
  final save makes no upload at all.

## 10. Coordinator: persisting a failed turn

- [x] 10.1 In `DeepResearchCompletion._run_turn`, wrap everything after the 409 check in
  `try/except Exception` and, on a failure, persist in the order of D4, then re-raise the same
  exception object: a snapshot refusal (`SnapshotVersionUnsupportedError`,
  `SnapshotUnreadableError`) → the failure record; research not started → the failure record;
  research started but the graph streamed no state → the failure record; anything else → the
  snapshot. The failure record is an empty `messages`, the `CrossTurnPrepState` read again with
  `load_last_prep_state(request)`, and the failure flag (D21). `BaseException` is not caught.
  Verify at the turn level: a failed properties fetch persists no state; a preparation failure
  after `update_plan` persists the failure record without the new plan; a failure while the
  research tools load persists the failure record; a cancellation persists nothing.
- [x] 10.2 Persist a failed research turn's snapshot (D6, D20, D21): in one `set_state`, the
  turn's preparation messages under `messages`, a copy of `CrossTurnPrepState` with `plan_approved` and
  `research_started` false under `preparation`, the snapshot under its key with its images uploaded
  in the re-raise mode of 4.1, and the failure flag; `resumable` is false exactly when the
  predicate of 1.2 names a class. Building and saving run in a `try`: on any failure, log one
  WARNING with the exception class and persist the failure record instead. The failure record's
  save runs in a `try` too, and logs one WARNING and persists nothing when it raises. The
  coordinator tracks whether it already called `set_state`. Verify at the turn level: a quota
  error in research-agent on a streaming request sends the state, snapshot included, ahead of the
  error chunk carrying DIAL Core's `display_message`; a `context_length_exceeded` rejection saves a
  snapshot marked not resumable; a raising `get_raw()` persists the failure record and delivers
  the quota error, not the bucket error; a raising failure-record save persists nothing and
  delivers the original error. Revised by 13.3: a snapshot state that cannot be encoded falls
  back to the failure record too. Revised by 14.8: a raising `get_raw()` saves the snapshot marked
  not resumable with the reason `image_upload_failed`, not the failure record.
- [x] 10.3 Write the INFO records "Snapshot saved" and "Failure recorded" with the fields of the
  **logging-policy** delta (D18): for a saved snapshot the plan id, resumable, resume point,
  iteration count, transcript messages, draft number, data-query records, the snapshot's and the
  state's JSON sizes, and the failure class when not resumable; for a failure record the reason,
  `preparation_failed`, `snapshot_refused`, `no_graph_state` or `snapshot_failed`. Verify that
  each record precedes the turn's single ERROR record, that a preparation failure logs one
  "Failure recorded" and exactly one ERROR, and that no record carries message text, the query, a
  plan step, a query id or a URL.
- [x] 10.4 Verify that a failed research turn leaves the conversation open: the next request runs
  the data-sources fetch and the preparation agent instead of the 409 refusal
  (`tests/test_data_sources_turn.py`); its preparation history holds the failed turn's preparation
  messages and the note, and nothing of the snapshot's transcript; a turn that completes after a
  failed turn carries no snapshot and no failure flag; a conversation whose report was delivered
  is still refused with 409 and persists nothing.
- [x] 10.5 Update `DeepResearchCompletion`'s docstring and the turn structure in
  `docs/architecture.md` with the failed-turn path: what a failed turn persists in each case of D4,
  that the failure flag puts the note into every later history, and that a turn never fails once
  its report is written. Verify that the diagrams render and that the prose links the
  **research-resume** spec instead of restating its rules.

## 11. Coordinator: resuming

- [x] 11.1 After preparation ends with `research_started`, search the history (5.4), read the
  latest snapshot against the current `plan_id` (5.3), and pass a resumable one to
  `ResearchRunner.run` (D8). A refusal raises before the runner starts, so 10.1 persists only the
  failure record. Verify at the turn level: "continue" with an unchanged plan resumes; a changed
  plan, or a latest snapshot marked not resumable, starts fresh with no data-query records
  restored; a refused snapshot is refused again on the next request, because the failure record
  kept the plan id; a resumed run that fails before its graph streams state keeps the earlier
  snapshot as the latest one; a second failure after the graph streamed state saves a new snapshot
  that the next request resumes from.
- [x] 11.2 Emit the "[DEBUG] reusing snapshot" or "[DEBUG] existing snapshot discarded" stage as a
  closed stage before the runner opens its first activity stage, and one INFO "Snapshot reused" or
  "Snapshot discarded" record with the same facts (D18, D19): for a reused snapshot the plan id,
  resume point, iteration count, transcript messages and draft number, plus the completed agent
  turns or the report-review round; for a discarded one the two plan ids, the reason, and the
  resume point when it reads as known. No stage is shown when no snapshot is found. Verify the
  stage titles, bodies and order, and the records' fields, in `tests/test_research_resume.py`.
- [x] 11.3 Update the preparation flow and turn structure in `docs/architecture.md` with the resume
  path: the failed-turn note, the history search, the plan-id match, the stage, and the entry at
  the snapshot's resume point. Verify that the diagrams render and that the prose links the
  **research-resume** spec.

## 12. Integration checks

- [x] 12.1 Run `make format`, `make lint` and `make test`; all pass.
- [x] 12.2 Run `openspec validate resume-research-after-failure --strict`; it reports no errors.
  The six "Requirement text is very long" warnings in `specs/research-resume/spec.md` are
  accepted.
- [x] 12.3 On the local stack, make a research-agent model call fail with a quota error, then write
  "continue" through DIAL Chat once the failure is removed (design, Migration Plan). Check that the
  failed answer carries the snapshot; that "continue" goes through `approve_plan` and
  `start_research` in one turn without showing the plan; that the "[DEBUG] reusing snapshot" stage
  shows; and that no tool call of the snapshot runs again. Repeat with a question between the
  failure and "continue", and with a changed query, whose snapshot is discarded. This also checks
  the note's conditional wording and the `PLAN_REVIEW_SYSTEM` paragraph (design, Open Questions).
  Keep conversation artifacts and notes in `$TMPDIR`, outside the checkout.
- [x] 12.4 Check the whole change against `no_sensitive_info.md`: tests, fixtures, docstrings and
  docs use placeholders such as `ACME` and `IMF:WEO`, and nothing from the live runs of 12.3
  reaches the repository.

## 13. State-write fallbacks

- [x] 13.1 In `app/completion.py`, route every state write through one helper (D23): it encodes the
  candidate state as Starlette's `JSONResponse` renders it (`ensure_ascii=False`,
  `allow_nan=False`, then UTF-8), and calls `_TurnProgress.save_state`
  only when the encoding succeeded, so a state that cannot be encoded leaves the turn's one write
  unused. It returns the encoded text, for the state size of the "Snapshot saved" record. Verify
  in a unit test that a state holding a value `json.dumps` cannot encode, and a state holding
  `float("nan")`, each raise before `set_state` is called and leave `state_saved` false.
- [x] 13.2 In `_persist`, when the report was written and the full state cannot be built or
  encoded, save the closing state (D22, D23): an empty `messages`, the turn's `CrossTurnPrepState` with
  `research_started` set, and no failure flag. Write the one WARNING after the closing state's
  write, naming the save and the exception class, with `saved=closing_state` when that write
  succeeded and `saved=nothing` when it raised. Verify at the turn level: a raising
  `create_dial_state` and an unencodable state after a delivered report each end the turn with
  `outcome=completed`, no ERROR, one WARNING and the closing state; the next request on that
  conversation is refused with 409 and runs no research; a raising `set_state` persists nothing
  and logs one WARNING with `saved=nothing`.
- [x] 13.3 In `_persist_failure`, write the snapshot state and the failure record through the
  helper of 13.1 (D21, D23): a snapshot state that cannot be built or encoded falls back to the
  failure record, and a failure record that cannot be built or encoded persists nothing. Each
  state that could not be saved logs one WARNING with the exception class. Verify at the turn
  level: an unencodable snapshot state persists the failure record with one WARNING; an
  unencodable failure record persists nothing; the original error is delivered in every case.
- [x] 13.4 Take the "Snapshot saved" state size from the encoding of 13.1, and the snapshot size
  from its own encoding (**logging-policy** delta, D18). Update the log assertions of the existing
  tests, and add one for a preparation-only turn whose own save fails: one "Failure recorded"
  record with `reason=preparation_failed`, followed by exactly one ERROR.
- [x] 13.5 Update `DeepResearchCompletion`'s docstrings and the failed-turn section of
  `docs/architecture.md`: replace the failed-turn diagram with one that shows the four states and
  the fallback order for each kind of turn, the report-written turn included, and link the
  research-resume requirement "A turn's one state write falls back in a fixed order" as the owner
  of the rule. Verify that the diagram renders and that the prose
  links the **research-resume** spec instead of restating its rules.
- [x] 13.6 Run `make format`, `make lint` and `make test`, and
  `openspec validate resume-research-after-failure --strict`; all pass.

## 14. The state's two parts, the research record and the image rules

- [x] 14.1 Split the turn's state into `preparation`, `research` and `turn_failed` (design D6) in
  `app/history.py`: `CrossTurnPrepState`'s fields stay directly under `preparation`, next to
  `agent_messages`, `query_reviews` and `plan_reviews`; rename the `research_snapshot` key to
  `research`; drop the `messages` key. Update `PreparationDialState`, `create_dial_state` and the four states
  of `app/completion.py` (`_persist`, `_persist_snapshot`, `_persist_failure_record`,
  `_save_closing_state`) to the table of D23. Verify that `preparation.research_started` is read
  from the same path as before, and that an old state with `messages` and no `agent_messages`
  parses.
- [x] 14.2 Keep each `QueryReviewResponse` of `update_query` and each `PlanReviewResponse` of
  `approve_plan` whole (`app/preparation/tools.py`), and have `PrepAgentRunner`
  (`app/preparation/runner.py`) hand them and the turn's agent messages to the coordinator for
  `preparation.query_reviews`, `preparation.plan_reviews` and `preparation.agent_messages`. A failed
  research turn saves them too; the failure record saves empty lists (D21).
- [x] 14.3 Rename `reconstruct_history` to `reconstruct_prep_agent_history` in `app/history.py`,
  `app/preparation/runner.py`, `scripts/send_conversation.py` and the tests. Make it read only
  `preparation.agent_messages`, never the `research` record, and download no image (D14). A state
  without `agent_messages` falls back to one `AIMessage` of the native `content`. Remove
  `rehydrate_image_blocks` from `utils/image_attachments.py`, with its tests. Verify that the
  preparation agent's history holds no research transcript and no image block after a completed
  turn, a failed research turn and an old state.
  Update `tests/test_history_persistence.py`, which uses `reconstruct_history`,
  `rehydrate_image_blocks` and the `research_snapshot` key.
- [x] 14.4 Change `ResearchState` (`app/research/state.py`) and the nodes (`app/research/nodes.py`)
  to the fields of D11: `original_query` becomes `research_query`, `plans` is replaced by
  `approved_plan` and the append-only `research_reviews`, `messages` becomes
  `research_agent_messages`, `report` and `report_version` become the append-only `reports`, and
  `report_revision_instruction` becomes the append-only `report_reviews`, whose entry holds the
  draft number, `rule_violations`, `blind_review` and `grounded_review`. Research-review appends its
  whole `ResearchReview`; report-review appends one entry per round, with an empty response for a
  failed call. Build in the consuming node: the plan list from `approved_plan` and each review's
  next steps, the routing count in `route_after_research_review`, the draft number from
  `len(reports)`, and the writer's revision instruction from the latest `report_reviews` entry
  (rule violations, then blind violations, then grounded items). Update the runner's reads of the
  final state (`_messages`, `_report`) and `build_initial_state`. Run research-agent inside a node function
  (D24): it calls the compiled agent with `{"messages": state["research_agent_messages"]}`, returns
  the agent's `messages` as `research_agent_messages` and `research_iteration` increased by one, and
  passes its own `config` to the agent so that the step budget applies to the agent's run;
  remove `IterationCounterMiddleware` (`app/research/middleware.py`) and its `state_schema`. Add a
  test that the agent's streamed parts keep the namespace `research-agent:<task id>` and the key
  `messages`, and a test that a failure mid-iteration leaves `research_iteration` unchanged. Store a
  failed review call, and a grounded review that answered with no text, as `None`, and derive items
  only from responses that are present. Update the `_handle_part` and `_already_seen` docstrings to
  name the key they read (D16). Update the tests that build research states with the old fields:
  `tests/test_research_routing.py`, `tests/test_report_loop.py`, `tests/test_report_loop_graph.py`,
  `tests/test_research_review_stage.py`, `tests/test_faithful_relay.py`,
  `tests/test_output_guardrails.py` and `tests/test_stream_drop_retry.py`; replace
  `tests/test_iteration_counter.py` with the node-function counting test. Verify that each LLM call's
  messages are byte-for-byte the same as before for one fixed fake run.
- [x] 14.5 Rewrite the report node's comment that a rejected draft is "never re-sent to a model nor
  persisted" (`app/research/nodes.py`): drafts are kept in `reports`, and only "never re-sent to a
  model" holds. Rewrite the same two claims in the `_deliver_report` docstring
  (`app/research/runner.py`): drafts are persisted, and the delivered text is not.
  Stop adding the delivered report to the persisted messages: remove the
  `AIMessage(content=text)` append in `ResearchRunner._deliver_report` (`app/research/runner.py`),
  so `run` returns research-agent's messages only, and update its docstring to say the delivered
  text goes to the assistant content alone. Verify that a completed run's record holds no report
  `AIMessage` and that its last draft is the draft the review judged.
- [x] 14.6 Make `ResearchSnapshot` (`app/research/snapshot.py`) the research record of D11: the
  header `plan_id`, `resumable`, `not_resumable_reason` (`completed`, `repeating_failure`,
  `image_upload_failed`), `version`, `resume_at` (`None` for a completed run's record), then the fields of `ResearchState`, with
  `research_reviews` and `report_reviews` declared with their models so `model_validate` restores
  them. Give every field of those models that is added later a default (a comment at each model
  says so). Keep `SNAPSHOT_VERSION` at 1. Update `build_snapshot`, `read_snapshot`,
  `find_latest_snapshot`, `build_resumed_state`, the stage facts (the report-review round is
  `len(reports)`) and the test that the record mirrors every `ResearchState` key. The discard stage
  and record show `not_resumable_reason` only when it reads as a known reason, as for
  `resume_at`.
- [x] 14.7 Save a successful run's research record in `_persist` (`app/completion.py`): marked not
  resumable with the reason `completed`, and with every image as the `successful run` placeholder,
  with no upload and no bucket lookup (D16). The closing state carries no `research` record.
- [x] 14.8 In `utils/image_attachments.py`, implement the placeholder
  `[image not stored: <reason>, <mime type>, sha256=<hex>]` in the image's own slot, with the
  reasons `successful run` and `upload failed` (D16). Add the mode that replaces every image without
  uploading. For a snapshot, retry each upload on HTTP 500, 502, 503 and 504, up to four attempts,
  waiting 1, 2 and then 4 s, and report which images could not be stored instead of raising; a
  failed bucket lookup counts as every image failing. `_persist_snapshot` then marks the snapshot
  not resumable with `image_upload_failed`. Retry a snapshot download only on HTTP 502 and 503, up
  to three attempts, waiting 1 and then 2 s. Move the download from `ResearchRunner.run` into
  `DeepResearchCompletion._find_resumable_snapshot`, after `read_snapshot` returns a resumable
  snapshot and before the stage: a 404 discards the snapshot with a new `DiscardReason`
  `image_missing`, shows the discarded stage, logs one WARNING and the INFO record, and lets
  research run fresh; any other failure after its attempts still raises
  `SnapshotImageUnavailableError`. A 404 on any image wins over other failures. Create the
  `ResearchRunner` before the lookup, so a download failure is recorded as `no_graph_state` (D18).
  Make `_find_resumable_snapshot` async and pass it the turn's `AsyncDial`; remove `dial`, the
  "needs a DIAL client" check and the download sentence from `ResearchRunner.run` and its
  docstring; fix the `SnapshotUnreadableError` docstring ("or one of its images no longer exists")
  and the `DiscardedSnapshot` docstring ("Read no further than its header"), which holds only for
  `plan_changed` and `not_resumable`. Rewrite the runner-level tests in
  `tests/test_research_resume.py` that pass `dial=` to `runner.run` so the snapshot arrives already
  downloaded, move the download half into a coordinator test, and update the 404 test in
  `tests/test_image_attachments.py`. Test that a 404 runs research from zero in the same turn, that
  a 404 beside a 503 still discards, that the turn's own record is found next, that a 503 after the
  last attempt is recorded as `no_graph_state`, and that the WARNING and the INFO record are
  written. Keep
  uploads and downloads concurrent. Update the module docstring, and log the WARNINGs of D18.
- [x] 14.9 Record the not-resumable reason for a failure a resume would repeat as
  `repeating_failure` (D20), and write `not_resumable_reason` in the "Snapshot saved" record
  (**logging-policy** delta, D18).
- [x] 14.10 Test the research state's lists in every scenario, with a compiled graph and fake
  models: written and read in the same run (two iterations, then the routing decision and the
  writer's plan text); saved in a failed snapshot (every entry whole and in order); read back from
  the snapshot as models equal to those saved, and used by the resumed nodes as by a fresh run; a
  resumed run that fails again (the restored entries, then the new ones, with no duplicates); a
  successful turn's record (every entry, reason `completed`); and preparation's reviews, saved on
  success and on failure.
- [x] 14.11 Test each not-resumable reason (`completed`, `repeating_failure`,
  `image_upload_failed`): the next turn that starts research discards the record, starts fresh, and
  receives none of the record's content, and its own record is the one found afterwards. Test the
  image rules: a successful run's record holds placeholders with the right hash and no URL, and
  makes no upload call; a snapshot upload that fails with 503 twice and then succeeds is stored; one
  that keeps failing leaves the placeholder and a not-resumable snapshot; a download retries 502
  and 503 only. Test that a repeating failure that also loses an image saves the reason
  `repeating_failure`.
- [x] 14.12 Update `docs/architecture.md`: the turn structure with the state's two parts, the
  history the preparation agent reads, the research graph's state fields and what each node
  appends, and the four states of the failed-turn diagram. In the resume section, the images are
  downloaded before the snapshot stage, a 404 leads to the discarded stage and a fresh run in the
  same turn, and the link uses the requirement title "Research resumes only when the latest research
  record is a resumable snapshot of the current plan". Link the specs rather than restating
  them. The README needs no change: no environment variable is added or removed.
- [x] 14.13 Check the whole section against `no_sensitive_info.md`, then run `make format`,
  `make lint`, `make test` and `openspec validate resume-research-after-failure --strict`; all
  pass.

## 15. Before archiving

- [ ] 15.1 Check whether any MCP server's structured content carries an `index` field: inspect real
  results of the glossary and document tools. If one does, the snapshot's tool artifacts meet the
  chunk merge that D12 protects the data-query records from, so revise the plan before archiving.
  Record the outcome in the design's risk "The transcript's tool artifacts can still meet the
  `index` merge".

## Workflow follow-up

- Verify the implementation against the change with `/opsx:verify`.
- Sync the delta specs into the main specs with the `openspec-sync-specs` skill, then archive the
  change with `/opsx:archive`.
- Before a channel uses one of the two Claude deployments, test the mid-history system message on
  an environment that serves them (design, Open Questions).
- The resume through StatGPT needs the StatGPT backend companion change (proposal, Impact).
