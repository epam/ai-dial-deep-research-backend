## 1. Policy mechanism

- [x] 1.1 Add `GenericPolicy` and `GENERIC_POLICIES` (source selection, then faithful relay) to `prompts.py`, with per-step headings and the source-kinds statement for source selection; replace `render_source_selection` with `render_generic_rules(step, source_kinds)` and rename the `{source_selection}` placeholder to `{generic_rules}` in the four prompts and at its call sites (`prompts.py`, and `nodes.py` for the research agent and research review).
- [x] 1.2 Reword every text that names only "the source-selection rules": research review's task sentence, gap bullet, `ResearchReview` docstring and field descriptions; the research agent's checklist item and failed-tool exception; report review's "Check exactly these".
- [x] 1.3 Tests: the block order, a policy with no part for a step adds no block, the source-kinds statement opens only the source-selection block, a policy rule whose step has no heading fails at import; update the existing prompt tests that import `render_source_selection`, format a prompt with the `source_selection=` keyword (`tests/test_data_sources_prompts.py`, `tests/test_status_tool.py`), or assert the reworded sentences.

## 2. Faithful-relay rules

- [x] 2.1 Create `app/research/faithful_relay.py` with `FAITHFUL_RELAY_RULES`, ported from the local prototype, with the "Source" term's search-answer warning, the "Only the sources" research-agent and report-writer reasons, the three additions (Certainty, No distortion, Forecasts and estimates) and the Forecasts and estimates review part for a stated dataset update.
- [x] 2.2 Rewrite the research agent's tools guidance: why a `rag_search` summary is not evidence, every figure from `get_pages`, and `retrieve_text_chunks` as word-for-word evidence.
- [x] 2.3 Amend the writer prompt (citations bullet, "never include" bullet, the publication-series sentence, the outrank list with the sentence that a section description does not override the faithful-relay rules), source selection's "Other sources and disagreements" review part (it points at "No calculations"), report review's check 1, and research review's sentences on summaries, comparisons, calculations and the search-summary gap.
- [x] 2.4 Preparation prompt: keep the user's formatting requests in the restated query.
- [x] 2.5 Reword the default "Detailed Analysis" and "Conclusion" descriptions in `app_properties.py`, and regenerate `docs/generated-app-schema.json`.
- [x] 2.6 Tests: each step's prompt carries its faithful-relay part and the terms after the source-selection block; report review's prompt carries no "No distortion" text; no prompt allows own inference or synthesis; research review names no calculation as the writer's; the outrank list carries the new prohibitions; the preparation prompt carries the formatting sentence; the defaults ask for no inference.

## 3. Glossary fixes

- [x] 3.1 Extend `GLOSSARY_TERMINOLOGY_RULE` with the slash term, the abbreviation form with its first use spelled out, and the lower-case first letter in mid-sentence.
- [x] 3.2 Test that the writer's rule and report review's check both carry the three sentences.

## 4. The grounded review

- [x] 4.1 Add the grounded review's neutral system message, instructions template and renderer to `prompts.py`, built from `render_rules(FAITHFUL_RELAY_RULES, step=REPORT_WRITER)` and a public source-selection terms constant exported from `source_selection.py`.
- [x] 4.2 Add the module-level `grounded_review_messages(...)` and `parse_review_items(text)` to `nodes.py`, and `grounded_review_call()` to `make_report_review_node`: the messages and roles of design decision 4, the default model at `medium` behind the stream-drop retry, the item parser, the warning on failure, and the `Report grounded-reviewed` log record; run it in the node's `gather` and merge its items after the blind review's.
- [x] 4.3 Add `grounded_review_error` to `ReportReviewOutcome`, and render a failed grounded review in the review stage's title and body (`runner.py`, `utils/dial_stages.py`).
- [x] 4.4 Tests: the grounded review's message order and roles; its instructions carry the terms and the writer parts and no client rule, source-selection rule or glossary rule; its transcript is the writer's; the merge order; `No violations.` adds nothing, an answer opening with "No violations of …" keeps its numbered item, and a non-empty answer with no numbered line is one item; the "Not your job" list names the term a report uses; a failed check leaves the other violations and the turn standing; a failed blind review leaves the grounded review's items; the log record carries no item text.

## 5. Docs and checks

- [x] 5.1 Update `docs/architecture.md`: the report-review node's two calls and what each prompt's rule blocks are.
- [x] 5.2 Run `make format`, `make lint` and `make test`.
- [x] 5.3 Grep the working tree and the diff for client names, endpoints and private paths.

## 6. Measurement (outside this repository)

- [x] 6.1 Offline: run today's review with its new review parts plus the grounded review, built from this branch's prompt functions, twice on the judged test drafts; grade the lists blind; report severe recall (threshold 70%) and the grounded review's precision (threshold 70%), with the missed violations.
- [x] 6.2 Live: run the evaluation cases on the local stack with a channel configuration kept outside this repository, on this branch and on the base commit; report the severe violations per draft, the grounded review's recall on draft 1, the time per turn, per research and per review round with both calls' durations, and the grounded review's cached tokens on later rounds.
- [x] 6.3 Record both measurements outside this repository, and fold any prompt fix they lead to into this change's specs.

## 7. Reconcile with the change `2026-10-02-no-calculations`

- [x] 7.1 Restore the work onto a branch from `development` and merge the three prompt files that both changes edit, keeping that change's wording where the two conflict: research review's next-steps paragraph, Rule 6's "Other sources and disagreements" review part, and the writer's outrank sentence, which gains only the two faithful-relay rules and the section-description paragraph.
- [x] 7.2 Remove the faithful-relay rule "No calculations"; give the grounded review the writer's section through `NO_CALCULATIONS_WRITER_RULE`, shared with the writer prompt; align the "Calculation" term with `CALCULATION_DEFINITION`; and replace the rounding example with `0.0473918265` written as 4.74%.
- [x] 7.3 Name the two report-review calls the blind review and the grounded review in code, the stage text, the tests and `docs/architecture.md`, and give each its own INFO record, `Report blind-reviewed` and `Report grounded-reviewed`, with `Report reviewed` as the node's summary.
- [x] 7.4 Tests: the grounded review and the writer share the "No calculations" wording; each review logs its own record and the node its summary; the updated assertions follow that change's wording.
- [x] 7.5 Rebase the delta specs on the main specs as that change left them, drop the duplicated calculation requirements and scenarios, and drop the allowance for flagged inference from "Reports contain no calculations".
- [x] 7.6 Send the grounded review's instructions and request as plain system messages instead of `developer` messages, and state in the faithful-relay spec why the messages come in this order and what keeps a cache hit likely.
