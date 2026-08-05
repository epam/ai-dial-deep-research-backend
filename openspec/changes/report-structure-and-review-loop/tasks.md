## 1. Configuration model

- [x] 1.1 Add `ReportSection` to `app_properties.py`: `name` and `description` (both `min_length=1`), `protected: bool = False`, with `Field(description=...)` on each — descriptions live in the schema, not in comments
- [x] 1.2 Add `default_report_structure: list[ReportSection]` (`min_length=1`) with the four default sections — Key Findings, Detailed Analysis, Conclusion, References — References carrying `protected=True`
- [x] 1.3 Write the default References description so it owns the source-entry rules for **every** cited type (documents and datasets): what each entry decodes and its columns. Move that text out of `REPORT_SYSTEM_PROMPT` rather than duplicating it. Until the final format arrives (design.md — Open Questions) reuse today's column definitions, but **not** its omission clause: `prompts.py` currently says "omit a table entirely when nothing of that type was cited", which would render a zero-citation report's section empty. The section is always written; a type with nothing cited drops only its own table, and a report with nothing cited at all says so plainly
- [x] 1.4 Add `max_report_words: int = 2750` (`ge=1`) and `max_report_revisions: int = 2` (`ge=0`)
- [x] 1.5 Add a model validator requiring at least one section with `protected=True`, and one requiring unique section `name`s — mirror `_validate_unique_server_names`'s error shape
- [x] 1.6 Fix the `max_research_iterations` description: it reads "researcher → reviewer loops", which is deployment-visible through the generated schema
- [x] 1.7 Run `make format` to regenerate `docs/generated-app-schema.json`; confirm `default_report_structure`'s `items` inlines the `ReportSection` fields with no `$ref` left, and that `make lint` passes the drift check
- [x] 1.8 Add the new properties to the **research** instance in `dial_conf/core/applications-template.json` only — the playground instance carries neither existing research property, since it runs no research graph and no report node
- [x] 1.9 Thread the three new properties from `ResearchRunner.run` through `build_research_graph` into the node factories. Its signature is `(tools, today_date, max_iterations, client_name)` today and must also carry the configured structure, the word ceiling and the revision budget — every group below reads them, so this plumbing exists first
- [x] 1.10 Decide and act on the README: its core-config snippet elides `applicationProperties`, so either add prose for `default_report_structure` beside the `mcp_servers` paragraph or record that the template plus the generated schema suffice. No env vars are added, so the env table is unaffected

## 2. Node rename sweep (do before the new code, so it lands on final names)

- [x] 2.1 `graph.py`: node ids `researcher` → `research-agent`, `reviewer` → `research-review`
- [x] 2.2 `nodes.py`: `build_researcher_agent` → `build_research_agent`, `make_reviewer_node` → `make_research_review_node`, `route_after_review` → `route_after_research_review`, the `ReviewerNode` type alias, and the `agent_logging_middleware("researcher")` label → `research-agent`
- [x] 2.3 `prompts.py`: `RESEARCHER_SYSTEM_PROMPT` / `REVIEWER_SYSTEM_PROMPT` constant names, and the **model-visible** sentence in `render_next_instruction` ("A reviewer checked the findings so far…")
- [x] 2.4 `research/tools.py`: `FINISH_ITERATION_RESULT` is **model-visible** and reads "handing off to the reviewer" — ambiguous with two reviewers; also its module docstring and tool docstring
- [x] 2.5 `research/__init__.py` docstring ("researcher → reviewer → report")
- [x] 2.6 `tests/test_agent_logging.py` (the `agent=researcher` assertions) and `tests/test_research_routing.py` (it imports `route_after_review`, so the suite fails to import until it is renamed — task 2.8's grep does not catch an import)
- [x] 2.7 `docs/architecture.md` — **names only** in this group: the researcher/reviewer role prose and the quoted spec sentence. Its behavior claims are updated later, in 11.6. (The file is untracked in the working tree, so check for conflicting edits first)
- [x] 2.8 Grep `src`, `tests`, `docs` for surviving `researcher`/`reviewer` and confirm each remaining hit is intentional role prose, not a node id

## 3. Report content rules

- [x] 3.1 Rewrite `REPORT_SYSTEM_PROMPT`: render the configured sections (name + description verbatim, in order) instead of the generic structure paragraph
- [x] 3.2 Add the word ceiling to the prompt as a number, and the rule that shortening means rewriting, never cutting
- [x] 3.3 Add the ban on confidence scores, complexity ratings, processing times and equivalent prose — while keeping honest qualification of evidence explicitly allowed
- [x] 3.4 State the protected sections by name, next to the query and plan text they outrank, and the precedence rule (protected sections, their rules, and the report-wide rules win; everything else in an instruction still applies)
- [x] 3.5 Keep the inline citation format in the prompt as a report-wide, non-configurable rule — it is an interface a DIAL chat renderer parses, not a section rule
- [x] 3.6 Add **no** rule instructing the writer to follow a user-supplied format request — that is issue #45, and adding it here implements a deferred criterion
- [x] 3.7 Add the rules for a section the findings cannot support: every configured section stays present, a section with nothing substantive to say says so plainly, it is never padded with unsupported text, and the report never explains that it declined an instruction

## 4. Word count and revision instruction

- [x] 4.1 Add a word-count helper: `len(text.split())` over the report Markdown, used by every caller so prompts, stage and log never disagree
- [x] 4.2 Add the revision-instruction renderer: previous draft, measured count, ceiling, and a direction to shorten by rewriting
- [x] 4.3 Make it merge the review's findings with the app-rendered length direction when both apply, and produce the length direction alone when the count forced the revision with no findings

## 5. report-review node

- [x] 5.1 Add the report-review system prompt: what to check (configured structure, protected sections, ceiling given the count, banned annotations, citation format, no padded sections, no commentary about a declined instruction) and what not to — no evidence coverage, no further research
- [x] 5.2 Add its structured-output schema with findings **before** the verdict, per the repo's verdict-last convention
- [x] 5.3 Add `make_report_review_node`, assembling its user message **stable content first** (structure, protected sections, ceiling, query, approved preparation plan) with the draft and its measured count **last**, for prefix stability
- [x] 5.4 Pass only the approved preparation plan (`plans[0]`), not the whole plan list — later entries are research-review's own and cannot carry a user instruction
- [x] 5.5 Do **not** pass the findings/transcript: no tool results, no images
- [x] 5.6 Wrap the call in `with_stream_drop_retry` — retry coverage is opt-in per call site
- [x] 5.7 Absorb failures: a raise, an unparseable verdict, or exhausted retries must not fail the turn — record the outcome and let the loop continue to its delivery decision

## 6. Graph state and routing

- [x] 6.1 Add state fields: the revision instruction, `revisions_used`, and a flag recording that a revision's own model call failed. Decide where the current draft's measured word count comes from for the router — a state field, or one shared accessor over `state["report"]` — and use that one source for the router, the stage and the log so the three cannot disagree. Seed every new channel in `build_initial_state` — an unwritten channel is absent from the state a node reads, not defaulted. Do the same for the loop's outcome: one helper derives the action (`deliver` / `revise` / `revise_over_ceiling` / `budget_exhausted`) from the count, the findings and the budget, the router maps its result to an edge, and the node logs that same value — the pattern `_should_continue` already sets for the research loop
- [x] 6.2 Make the report node branch on **whether a previous draft exists** (`state["report"]` is set) — *not* on `revisions_used > 0`, which is still 0 while the first revision is being written
- [x] 6.3 Make the report node write no `AIMessage` into `state["messages"]`, so drafts stay out of the transcript and out of the persisted slice. **Land this together with 7.3**: between the two, the persisted slice loses the report `AIMessage` that `dial-agent-with-mcp` contracts, and no existing test asserts it — so a half-done split breaks that contract silently
- [x] 6.4 Increment `revisions_used` only when the node runs with a previous draft present, so the counter equals revisions written and the loop allows `max_report_revisions + 1` report calls
- [x] 6.5 Absorb a failed revision in the report node: keep the previous draft and set the failure flag
- [x] 6.6 On a revision, append **one** `HumanMessage` carrying the previous draft, the revision instruction and the measured count with the ceiling **after** the unchanged `[system, *state["messages"], REPORT_REQUEST]` list — never inserted before the transcript, or the cached prefix is lost for every later call in the run
- [x] 6.7 Wire the edge out of `report`: END when this call was a revision whose own call failed, else `report-review` when the revision budget is non-zero, else END. **Land 6.7 and 6.8 together with 7.1 and 7.2**: the runner forwards report tokens until 7.1 drops the `messages` stream mode, so a revision loop landing first appends draft 1 *and* draft 2 to the same assistant message — the opposite of the contracted "no draft reaches the choice"
- [x] 6.8 Wire `route_after_report_review`: back to `report` when the measured count exceeds the ceiling **or** the review asked for a revision, and the budget allows; else END. An approving verdict must not pass an over-ceiling draft
- [x] 6.9 Keep the report node non-streaming internally via `astream` (preserving the existing drop-retry loop) but forward no tokens

## 7. Runner, DIAL output, and the review stage

- [x] 7.1 Drop the `messages` stream mode and `_handle_message_chunk` from `ResearchRunner`; take the settled report from the graph's final `values` state
- [x] 7.2 Append the delivered report to the choice in one call
- [x] 7.3 Build the persisted assistant message in the runner from the final `report`, so `custom_content.state` still ends with the report `AIMessage`
- [x] 7.4 Make the leading `"\n\n"` conditional: have `PrepAgentRunner` expose whether it appended any content, thread it through `completion.py`, and prepend only then
- [x] 7.5 Add a report-review stage formatter to `utils/dial_stages.py` — its own title form (not the tool-shaped `[TOOL] "<name>"`), carrying outcome and elapsed time, with the body listing findings so multi-line entries stay readable
- [x] 7.6 Add the stage-emitting callback: a bound method on `ResearchRunner` that closes over `self._choice`, passed through `build_research_graph` into `make_report_review_node`. `nodes.py` must gain no DIAL import; the callback takes one pydantic value (draft number, count, ceiling, findings, outcome, duration) and is sync
- [x] 7.7 Emit the stage for every review: findings when there are some, the approval when there are none, the failure when the call failed. No stage at all when the revision budget is zero

## 8. Preparation silent hand-off

- [x] 8.1 Add the middleware under `preparation/` (not shared `app/middleware.py`, whose docstring reserves it for middleware any agent may need): a `before_model` hook returning `{"jump_to": "end"}` once `PrepState.research_started` is set
- [x] 8.2 Decorate the hook `@before_model(can_jump_to=["end"])` — without it the jump is silently ignored, because the conditional edge gets no END destination
- [x] 8.3 Register it on the preparation agent, and confirm a gate-rejected `start_research` still reaches the model so the agent replies to the user
- [x] 8.4 Edit the preparation prompt's launch step to drop "tell the user that research is starting", and update the `RESEARCH_READY` tool message (it still says execution is not wired up) to state that the hand-off is automatic and no message is needed

## 9. Logging

- [x] 9.1 Extend the report-generated event: draft ordinal (`revisions_used + 1`), duration, length in characters **and** measured words, token usage
- [x] 9.2 Add the report-reviewed event: draft ordinal, duration, the model's `verdict` and separately the app's `action`, the measured count, the ceiling, the **number** of findings, token usage
- [x] 9.3 Log a WARNING when a review call fails, and one when a revision fails — the latter naming the failure kind, the failed revision's ordinal, and the ordinal of the draft delivered instead
- [x] 9.4 Verify no finding text, draft text or report text reaches any record at any level, including DEBUG — the content allowlist forbids LLM response bodies outright

## 10. Tests

- [x] 10.1 `ReportSection` and the three properties: defaults resolve (four sections, References protected, 2750, 2); empty list, empty `name`/`description`, no protected section, and duplicate names each rejected
- [x] 10.2 Word count: whitespace-token definition, and that prompt, stage and log all use it
- [x] 10.3 Routing: approval delivers the first draft; findings drive a revision; an approving verdict does **not** pass an over-ceiling draft; a draft exactly at the ceiling is within it; the budget caps report calls at `max_report_revisions + 1`; a zero budget makes no review call
- [x] 10.4 Failure paths: a failed review delivers a within-ceiling draft; a failed review still shortens an over-ceiling draft; a failed revision delivers the previous draft and leaves the loop; none of the three fails the turn
- [x] 10.5 A forced revision with no model findings still receives an instruction, and is not invoked as a first draft
- [x] 10.6 Structure rendering: configured sections replace the defaults in the prompt; a section's rules come only from its description
- [x] 10.7 Report delivery: no draft token reaches the choice; the delivered report is appended once; no leading blank line when preparation streamed nothing
- [x] 10.8 The review stage: emitted per review with the counts and findings; emitted on approval and on failure; absent at a zero budget
- [x] 10.9 Silent hand-off: a passing `start_research` produces no further model call; a gate-rejected one still answers the user
- [x] 10.10 Update `tests/test_stream_drop_retry.py` for the report node's new signature and state, keeping the "partial text is not persisted" assertion (now also "never visible")
- [x] 10.11 The persisted slice: given a final graph state carrying only `report` text and no report `AIMessage`, the slice the runner returns still ends with an `AIMessage` holding the delivered report. This is the assertion that makes the 6.3/7.3 pairing verifiable — today's `test_persisted_slice_comes_from_the_last_root_values` hand-builds that message, so it cannot catch its absence
- [x] 10.12 report-review's inputs: no `ToolMessage`, no transcript message and no image block reach the call; it receives `plans[0]` only; the draft and its measured count are the last content in the user message

## 11. Verification and docs

- [x] 11.1 Confirm the CLAUDE.md convention on stating each LLM call's inputs and outputs is present (already applied in the working tree)
- [x] 11.2 `make format` and `make lint` clean, including the schema drift check
- [x] 11.3 `make test` green
- [ ] 11.4 Run a real turn with `scripts/send_conversation.py` and check by eye: the answer is the report alone, sections match the configuration, the references section is present, no meta-annotations, and the review stage shows the counts and findings
- [ ] 11.5 Read the INFO log of that run against the skeleton: report-generated and report-reviewed present with their counts, and no report or finding text anywhere
- [x] 11.6 Update `docs/architecture.md` for the behavior this change alters: four nodes instead of three, the report ↔ report-review loop and its edges, the report-review stage, the report appended once rather than streamed (two places say "streamed"), and the revised outer step-budget bound
