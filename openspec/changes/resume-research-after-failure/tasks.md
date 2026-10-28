# Tasks

Decision numbers (D1–D23) refer to this change's `design.md`.

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

- [x] 2.1 Add `plan_id: str | None = None` to `PrepState` (`app/history.py`), and name in its
  docstring the three tools that write it. Verify in `tests/test_history_persistence.py` that a
  `preparation` dict without `plan_id` still validates and that one with it round-trips through
  `DialState`.
- [x] 2.2 In `app/preparation/tools.py`, set a fresh `uuid4().hex` in `update_plan` on every call,
  clear `plan_id` together with the plan in `update_query`, and give a plan without an id a fresh
  one in `start_research` before it sets `research_started` (D7). Verify in
  `tests/test_preparation_tools.py`: recording the same steps twice gives two different ids;
  `update_query` after a recorded plan leaves `plan_id` empty; `start_research` on an approved plan
  without an id sets one, and keeps an existing id unchanged.

## 3. Failure flag and the failed-turn note

- [x] 3.1 Add the snapshot and failure-flag state key constants to `app/history.py`, next to
  `DialState` (D6, D21). The flag lives at the top level of the state, never in `PrepState`, and
  `DialState.from_dict` keeps reading only `messages` and `preparation`. Verify in
  `tests/test_history_persistence.py` that `load_last_prep_state` reads the `PrepState` of a state
  that also carries both keys, including one whose snapshot value is not a valid snapshot.
- [x] 3.2 Add the failed-turn note to `app/preparation/prompts.py` as a triple-quoted constant with
  the starting wording of D14. In `reconstruct_history`, append it as a `SystemMessage` after every
  assistant message whose state carries the failure flag: after its decoded `messages`, or after
  the fallback `AIMessage` of its native `content` when `messages` is empty. Reconstruction reads
  nothing of the snapshot. Update the function's docstring. Verify in
  `tests/test_history_persistence.py`: a flagged state with preparation messages and a snapshot
  gives the messages, then the note, then the next user message, with nothing of the snapshot's
  transcript and no download of its images; a flagged state with an empty `messages` gives the
  native-content `AIMessage`, then the note; an unflagged state gets no note; with several turns
  after the failed one, the note stays directly after the failed turn.
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
  first mode, and raises in the second.
- [x] 4.2 Add the snapshot image download to `utils/image_attachments.py` (D16). It turns every
  URL-form image block of the given messages back into base64, tries each download up to
  `STREAM_DROP_MAX_ATTEMPTS` times with exponential backoff from the initial delay `utils/llm.py`
  uses, does not retry `aidial_client`'s `ResourceNotFoundError` and raises
  `SnapshotUnreadableError` for it, and raises `SnapshotImageUnavailableError` after the last
  failed attempt. Each failed attempt that another attempt follows logs one WARNING with the
  attempt number, the exception class and the URL stripped by `_strip_url_query`. Verify in
  `tests/test_image_attachments.py` with a fake `AsyncDial` and a patched sleep: a failure then a
  success restores the base64 and logs one WARNING; a 404 makes one request and raises
  `SnapshotUnreadableError`; three failures raise `SnapshotImageUnavailableError` after two
  WARNINGs; no record carries a query string.
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
  (D11): the completed agent turns (the `AIMessage`s after the last `HumanMessage`) for resume
  point research, and the report-review round (`report_version`) for report review. Verify that
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
  starts: download its images with the helper of 4.2; restore its data-query records into
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
  snapshot whose transcript holds the seed instruction and two completed agent turns, one tool
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
  state. Revised by 13.2: a failed build or encoding saves the closing state.

## 10. Coordinator: persisting a failed turn

- [x] 10.1 In `DeepResearchCompletion._run_turn`, wrap everything after the 409 check in
  `try/except Exception` and, on a failure, persist in the order of D4, then re-raise the same
  exception object: a snapshot refusal (`SnapshotVersionUnsupportedError`,
  `SnapshotUnreadableError`) → the failure record; research not started → the failure record;
  research started but the graph streamed no state → the failure record; anything else → the
  snapshot. The failure record is an empty `messages`, the `PrepState` read again with
  `load_last_prep_state(request)`, and the failure flag (D21). `BaseException` is not caught.
  Verify at the turn level: a failed properties fetch persists no state; a preparation failure
  after `update_plan` persists the failure record without the new plan; a failure while the
  research tools load persists the failure record; a cancellation persists nothing.
- [x] 10.2 Persist a failed research turn's snapshot (D6, D20, D21): in one `set_state`, the
  turn's preparation messages under `messages`, a copy of `PrepState` with `plan_approved` and
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
  back to the failure record too.
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
  encoded, save the closing state (D22, D23): an empty `messages`, the turn's `PrepState` with
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

## Workflow follow-up

- Verify the implementation against the change with `/opsx:verify`.
- Sync the delta specs into the main specs with the `openspec-sync-specs` skill, then archive the
  change with `/opsx:archive`.
- Before a channel uses one of the two Claude deployments, test the mid-history system message on
  an environment that serves them (design, Open Questions).
- The resume through StatGPT needs the StatGPT backend companion change (proposal, Impact).
