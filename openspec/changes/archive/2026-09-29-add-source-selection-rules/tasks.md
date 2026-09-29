## 1. Configuration model

- [x] 1.1 Add `QualityRule` to `app_properties.py`: `name` and the four optional non-empty parts, `extra="forbid"`, a validator that at least one part is set, and field descriptions.
- [x] 1.2 Add `Prompts.client_rules: list[QualityRule]` (default empty) with the unique-name validator and a field description that says what a client rule is for, that it follows the generic rules and takes precedence where more specific.
- [x] 1.3 Tests in `tests/test_app_properties.py` for every scenario of "Prompts carry the channel's client rules", and confirm the template test still passes unchanged.
- [x] 1.4 Reject a blank client-rule name or part, and a name with a line break; tests for each.

## 2. Generic rules and rendering

- [x] 2.1 Add `RuleStep` to `app_properties.py`, and create `app/research/source_selection.py` with `SOURCE_SELECTION_RULES`: "Terms" (per-step texts from one constant, "Reasonable attempt" only for the research agent and research review) and rules 1 to 8, each part per the source-selection spec, with domain-neutral wording, no tool names in the generic text, and research-agent parts that only ask for retrievals.
- [x] 2.2 Add `render_rules(rules, step)` and the client-block renderer (heading, precedence sentence, `<client_rules>` tag; empty string when no rule has a part for the step).
- [x] 2.3 Unit tests: a part reaches only its step; a rule with no part for a step adds nothing; the client block is absent without client rules and present with one; Terms carry "Reasonable attempt" only for the two research steps.

## 3. Prompt templates

- [x] 3.1 Research agent: add the two blocks after "Research strategy"; amend the checklist date item to exempt a publication's stated date; add the source-selection checklist item; make the failed-tool exception name its items.
- [x] 3.2 Research review: amend the task sentence, the gap list (comparison-data wording, metadata-date exemption, a bullet for the rules' gaps), the empty-plan sentence, the scope paragraph and "prefer to finish"; add the retrieval-only sentence; add the two blocks; rewrite the `ResearchReview` docstring and field descriptions as model-facing text naming the rules' gaps.
- [x] 3.3 Report writer: add the two blocks after the report rules and glossary rule; add the source-selection prohibitions to "These rules outrank the request", with the one-sentence exception to "do not explain a declined request".
- [x] 3.4 Report review: add "Source-selection checks" and "Client-specific checks" after the numbered checks, before "Data sources" and "Not your job"; change "Check exactly these"; remove "whether a source was the right one to use" from "Not your job".
- [x] 3.5 `report_rules.py`: reword `_LENGTH_VIOLATION` to condense without dropping a value, unless another item asks to change it.
- [x] 3.6 `utils/dial_stages.py`: the empty-next-plan stage text names the rules.

## 4. Wiring

- [x] 4.1 Pass `client_rules` from `ResearchRunner` through `build_research_graph` to the four node builders, and render each system prompt with its step's generic and client blocks.
- [x] 4.2 Tests that each of the four system prompts carries its step's generic block, and the client block when configured; update existing prompt tests that the amended texts break.
- [x] 4.3 State the channel's kinds of source in every step's generic block: `ApplicationProperties.source_kinds` from the configured servers, passed from `ResearchRunner` through `build_research_graph` to the four node builders and the two render functions as a required argument; tests for each combination of kinds.

## 5. Docs and checks

- [x] 5.1 Update `docs/architecture.md` (what each node's system prompt carries) and the README core-config snippet if it shows `prompts`.
- [x] 5.2 Run `make format` (regenerates `docs/generated-app-schema.json`), `make lint` and `make test`.

## 6. Client configuration (outside the repository, not committed)

- [x] 6.1 Write the channel's client rules into the local git-ignored `dial_conf/core/applications.json`, and into the private configuration repository's source properties.
- [x] 6.2 Restart DIAL Core and the app, and confirm the channel's prompts carry the client block.

## 7. Evaluation and tuning

- [x] 7.1 Run simple local questions (for example how a forecast evolved, the current forecast of an indicator) and read the findings and the report against each rule; fix prompt conflicts found.
- [x] 7.2 Run two or three eval cases, several runs each, against the local stack; score each run against its ground truth where one exists; correct stale ground truth. (No ground-truth mistake was found.)
- [x] 7.3 Tune the rules from what the runs show, and re-run the affected cases. (Rules 2, 3, 6, 7 and 8 reworded, and reasoning for the two review calls, per design decisions 6, 7, 8, 11 and 12.)
