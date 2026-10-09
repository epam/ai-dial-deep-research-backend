## 1. Rule model

- [x] 1.1 Split `RuleStep.REPORT_REVIEW` into `REPORT_REVIEW_BLIND` ("report_review_blind") and `REPORT_REVIEW_GROUNDED` ("report_review_grounded"); rename the `QualityRule` field and add the new one, with field descriptions that say which review reads each and what it sees
- [x] 1.2 Add the `QualityRule` validator that rejects a rule setting both review parts, naming the rule; update the "set at least one part" message and the `Prompts.client_rules` description (five parts)
- [x] 1.3 Tests in `tests/test_app_properties.py`: both parts rejected, old `report_review` rejected as unknown, one-part rule validates with four `null` parts

## 2. Policy rendering

- [x] 2.1 `GenericPolicy`: add `terms_name`, `terms` (keyed by step), `glossary_rules`, `grounded_by_writer_parts` and `rule_step`; rewrite the import-time check per design decision 2, covering `glossary_rules` and requiring a terms entry for every step whose block renders
- [x] 2.2 Move the source-selection and faithful-relay terms out of their rule tuples into the policies (export `FAITHFUL_RELAY_TERMS`); keep the rendered text of the existing steps byte-identical
- [x] 2.3 `render_policy` / `render_generic_rules` take `glossary`; terms render only when the block has parts; pass `glossary` from every caller (research agent, research review, writer, blind review), including `build_research_agent`, its caller in `graph.py`, and the tests that build it (`test_iteration_counter.py`, `test_tool_failure_harness.py`)
- [x] 2.4 `render_client_rules` picks "Client-specific checks" for both review steps
- [x] 2.5 Rename every generic `report_review=` to `report_review_blind=` in `source_selection.py` and `faithful_relay.py`

## 3. Source selection and faithful relay texts

- [x] 3.1 Add the "Supersede" sentence and the "Qualifying context" term to `SOURCE_SELECTION_TERMS`
- [x] 3.2 Add the two sentences to "The dataset value" writer part
- [x] 3.3 Rename "Methodology" to "Qualifying context" and apply the agreed research-agent, research-review and writer texts
- [x] 3.4 Replace the blind part of "Gaps in the evidence" with the agreed text
- [x] 3.5 Update tests that pin these texts (`test_source_selection_prompts.py`, `test_faithful_relay.py`, `test_no_calculations_prompts.py`)

## 4. New policies

- [x] 4.1 `language_style.py`: verbatim names, neutral register, names not codes (grounded), no exclamation marks or slang, and the glossary-only verbatim rule, with the agreed texts
- [x] 4.2 `terminology.py`: the glossary search rule (glossary-only), accurate and consistent terms (writer and grounded), and the glossary-only "Glossary terms and source terms" writer rule
- [x] 4.3 `prohibited_content.py`: the removal rule (writer and blind)
- [x] 4.4 Define the three policies with the agreed headings and add them to `GENERIC_POLICIES` in the order source selection, faithful relay, terminology, language and style, removal
- [x] 4.5 `ReportEmojiRule` in `report_rules.py`, added to `build_report_rules`; add `regex` as a direct dependency and `types-regex` as a dev dependency, and update the lock file
- [x] 4.6 Tests: each policy reaches only its steps; glossary-only rules and the word "glossary" absent on a channel without a glossary; the emoji check (emoji, flag, keycap, ™ and ®, clean draft)

## 5. Review prompts

- [x] 5.1 Grounded prompt per design decision 5: rules preamble, generic blocks via `REPORT_REVIEW_GROUNDED`, `## No calculations`, client grounded block, narrowed "Not your job", new "Your answer"; new signature and caller in `nodes.py`
- [x] 5.2 The code comment in `render_grounded_review_prompt` on the duplicated checks and the source-selection false-positive risk; update the docstrings and comments that describe what the grounded review receives (`source_selection.py`, `faithful_relay.py`, the `GenericPolicy` docstring, the comment on `_GROUNDED_REVIEW_PROMPT`, `make_report_review_node`)
- [x] 5.5 Writer prompt: "These rules outrank the request" names the rules that exclude content
- [x] 5.3 Blind prompt: "Not your job" names emojis among the app checks
- [x] 5.4 Tests: the grounded prompt carries the source-selection writer parts and terms, the faithful-relay writer parts, the new grounded parts, a client grounded part, and no blind part; the example in "Your answer" parses into two items with `parse_review_items`

## 6. Docs and checks

- [x] 6.1 `docs/architecture.md`: the two reviews' inputs and the new policies
- [x] 6.2 Run `make format` (regenerates `docs/generated-app-schema.json`), `make lint` and the test suite
- [x] 6.3 Check the diff against `no_sensitive_info.md`: no client names, client rule texts or deployment facts

## 7. Client configuration and local validation

- [x] 7.1 In the private client-configuration repository, rename `report_review` to `report_review_blind` in the client rules and apply the agreed client-rule edits; regenerate its configs against the local backend; copy the local `applications.json` into `dial_conf/core/`
- [x] 7.2 Start the local stack and app, send a test question with `scripts/send_conversation.py`, and confirm in the logs and stages that both reviews run and the report carries no emoji, code or removed topic
- [x] 7.3 Update the implementation statuses in the internal policy documents
