## Why

Deep Research relays facts wrongly: a report can state a number no source gives, reverse a
comparison, state a forecast as an observed value, or draw a conclusion no source draws. The writer
is not told the rules that would prevent it, and report review cannot catch it, because report
review does not see the sources. In internal tests on a few first drafts, report review found about
a quarter of the drafts' severe relay errors.

## What Changes

- **The faithful-relay rules, a new generic policy.** Terms (source, claim, summary, comparison,
  calculation, inference, forecast and estimate, certainty, statement about the evidence) and seven
  rules: only the sources, no inference, figures as the source gives them, forecasts and estimates
  named as such, certainty kept, no distortion, and missing evidence stated. Each rule is a
  `QualityRule` with one part per step, rendered into the research agent, research review, the
  writer and report review, as the source-selection rules are. The rule that nobody calculates
  already ships as plain prompt text, from the change `2026-10-02-no-calculations`; this change
  does not restate it, and its "Calculation" term uses that change's definition.
- **A search tool's answer is not a source.** The rules and the research agent's tools guidance say
  that a search answer summarises pages and can change, distort or invent a value, a sum or a
  characterisation that no page states, so every value is taken from a page that was read or a
  chunk returned word for word.
- **Report review gains a second call.** Its two calls are named by what they see. The **blind
  review** is today's review call: it sees the draft, the configured sections, the question and the
  plan, but not the findings. The **grounded review** is new: it sees the research transcript, as
  the writer does, and judges the draft against the rules' writer parts, the writer's "No
  calculations" section and the source-selection terms. It runs beside the blind review, at
  reasoning effort `medium`, and returns a plain numbered list. Its items join the blind review's
  violations, so the loop routes as before. A failed grounded review logs a warning and adds
  nothing; the turn does not fail.
- **The generic rules are grouped into policies.** Each policy renders as its own block with a
  heading and an opening sentence per step: source selection first, because it defines the terms
  faithful relay uses, then faithful relay, then the client rules.
- **The prompts stop permitting the writer's own inference.** The citations section, the "never
  include" list and report review's section-content check accept an uncited sentence only as a
  summary or a comparison of cited claims, a fact that names a publication series as its source,
  or a statement about the evidence. "Infer nothing, keep every figure as its source gives it"
  joins the rules that outrank the request, after the "No calculations" rule. The default
  "Detailed Analysis" and "Conclusion" descriptions stop asking for what follows from the sources.
  The "No calculations" requirement's allowance for an uncited sentence flagged as the report's own
  inference is removed.
- **The preparation agent keeps the user's formatting requests,** such as rounding, in the
  restated query, because the writer and report review see the request only through it.
- **Three fixes to the glossary rule.** A slash term may be written as any one of its names, a term
  with an abbreviation in parentheses in either form, with the full form at the abbreviation's first
  use, and a term's first letter may be lower case in mid-sentence. These remove false review items.
- **Each review logs its own record.** `Report blind-reviewed` and `Report grounded-reviewed` carry
  each call's duration, message count, item count, error and token usage; `Report reviewed` becomes
  the node's summary.
- Reasoning efforts do not change: research review and the blind review stay at `medium`.

## Capabilities

### New Capabilities

- `faithful-relay`: the faithful-relay terms and rules, each step's part of them, the grounded
  review in report review, and the prompt text and default sections that must agree with the
  rules.

### Modified Capabilities

- `source-selection`: the generic rules are grouped into policies, each rendered as a block of its
  own; the sentences that name the rules a step follows name every rule section.
- `research-execution`: research review's gaps include the faithful-relay ones, and the list of
  each research call's inputs gains the faithful-relay blocks and the grounded review.
- `report-composition`: the writer's own inference is no longer permitted, a fact from a
  publication series description names the series in words, the review loop merges the grounded
  review's items, each review logs its own record, the glossary rule accepts the three forms, and
  "Reports contain no calculations" loses its allowance for flagged inference.
- `clarification-and-plan-alignment`: the restated query keeps the user's formatting requests.
- `logging-policy`: the INFO skeleton gains the two review records, and the report-reviewed event
  becomes the node's summary, whose violation count includes the grounded review's items.

## Impact

- `src/dial_deep_research/app/research/`: new module `faithful_relay.py`; `prompts.py` (the policy
  renderer, the grounded review's prompt, `NO_CALCULATIONS_WRITER_RULE`, the prompt amendments, the
  research agent's tools guidance, `GLOSSARY_TERMINOLOGY_RULE`); `nodes.py` (the renamed rule
  placeholder in the research agent's and research review's prompts, the two review calls in
  `make_report_review_node` with their log records, and the module-level functions that build the
  grounded review's messages and read its answer); `source_selection.py` (a public terms
  constant); `runner.py` and `utils/dial_stages.py` (the review stage records which review
  failed).
- `src/dial_deep_research/app/preparation/prompts.py`: the formatting-request sentence.
- `src/dial_deep_research/app_properties.py`: the default section descriptions, and
  `docs/generated-app-schema.json`, regenerated from them.
- `docs/architecture.md`: the report-review node's two calls.
- `tests/`: each step's prompt carries its part, the grounded review's messages and their roles, the
  merge of its items, its failure path, the review records, and the glossary rule.
- Cost and time: the grounded review reads the whole transcript, so it adds about USD 0.25 and
  about a minute of model time per review round; it runs concurrently with the blind review, so the
  node takes as long as the slower call. A transcript past the model's long-context threshold
  doubles the grounded review's input price.
- No configuration change and no feature flag. Rollback is reverting the change.
- Out of scope: the other output-quality policies, source-selection checks against the transcript,
  filtering the transcript to the cited sources, and any change to reasoning efforts.
