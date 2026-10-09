## Why

The output-quality policies define what a good report is, and an audit of the backend found that
policies 1 (language and style), 2 (terminology) and 4 (prohibited content) have generic rules that
nothing implements: the register is not checked, emojis and dataset codes pass, a synonym can
change a source's meaning, and a removed topic is still mentioned. The audit also found gaps in the
shipped source-selection rules: a dataset value can still replace a publication's value, only the
methodology of a value is retrieved and not its other qualifying context, and no review can see
that a figure carrying two citations merges two different values. Rules that compare the report
with its sources need the grounded review, and today a rule has no way to say that the grounded
review, not the blind one, judges it.

## What Changes

- **BREAKING** — a quality rule's `report_review` part is renamed `report_review_blind`, and a new
  optional part `report_review_grounded` holds a check that only the grounded review, which sees
  the research findings, can judge. A rule sets at most one of the two; validation rejects a rule
  that sets both. Client rules have the same shape, so every channel configuration that sets
  `report_review` must rename it in the same release.
- The grounded review renders every rule's `report_review_grounded` part, the generic rules' and
  the client rules', in addition to what it receives today.
- The grounded review also judges the draft against the **source-selection** rules' writer parts,
  as it already does for the faithful-relay rules. The source-selection and faithful-relay rules
  keep every shipped text, and both reviews keep checking them: the blind review by their blind
  parts, the grounded review by their writer parts.
- A policy's terms (the source-selection terms and the faithful-relay terms) stop being a quality
  rule and become an attribute of the policy, rendered at the top of the policy's block in every
  step, so the rendered text of the existing steps stays the same.
- **Language and style (new generic policy):** verbatim names defined; a neutral register; no
  exclamation marks or slang; no emojis, checked by a new app rule `ReportEmojiRule`; and every
  codelist value and dataset named by its name, never by its code or id, outside a citation marker.
  The last one is judged by the grounded review.
- **Terminology (new generic policy):** on a glossary channel, research searches under both a
  glossary term's name and a phrase from its definition; every channel keeps each source's term,
  replaces it with a glossary term only when both name exactly the same concept, and uses one term
  per concept. The terminology check is judged by the grounded review.
- **Removal (new generic policy):** a rule that excludes content holds even when the question or
  the plan asks for it; a removed passage takes every reference to it along; and the report never
  mentions an excluded topic, not even to say that it does not cover it.
- **Faithful relay, rule 8 ("Gaps in the evidence"):** its blind part also checks the approved
  plan, and exempts a part of the question or the plan that a rule excludes. This is the only
  change to an evaluated faithful-relay text.
- **Source selection:** rule 4 says that a dataset value never supersedes a publication's value
  either; rule 5 is renamed "Qualifying context" and covers assumptions, scenario conditions,
  limitations and caveats as well as methodology.
- The grounded review's answer format states the numbered-list layout the parser reads, with a
  short example, and its list of what it does not judge is narrowed so that the new grounded
  checks are its to judge.
- Code comments state why the faithful-relay and source-selection rules are checked by both
  reviews, and the known risk that the grounded review lacks the blind parts' guards against
  false positives.

## Capabilities

### New Capabilities

- `language-and-style`: the generic language-and-style policy: verbatim names, neutral register, no
  exclamation marks or slang, no emojis (an app check), and names instead of codelist codes and dataset ids.
- `terminology`: the generic terminology policy: the glossary search under both phrasings, and
  accurate and consistent terms, with the boundary between a glossary term and a source's term.
- `prohibited-content`: the generic removal rule that governs every removal a rule asks for.

### Modified Capabilities

- `source-selection`: a quality rule's two review parts and the "never both" validation; a policy's
  terms as an attribute; the policy order with the three new policies; the grounded review judging
  the source-selection writer parts; rules 4 and 5.
- `faithful-relay`: rule 8's blind part; the grounded review's instructions: what they carry (the
  source-selection writer parts, every rule's grounded part, the client rules' grounded parts), the
  narrowed "not your job" list, and the answer format.
- `research-execution`: the inputs of the blind review and the grounded review calls.
- `application-config-schema`: a client rule's fields `report_review_blind` and
  `report_review_grounded`, and the validation that rejects both.
- `report-composition`: the emoji check joins the rules the app checks itself, and the review loop
  says what each review now judges.

## Impact

- Code: `app_properties.py` (`RuleStep`, `QualityRule`), `app/research/prompts.py` (policies,
  rendering, both review prompts), `app/research/source_selection.py`,
  `app/research/faithful_relay.py`, new modules for the three policies,
  `app/research/report_rules.py`
  (`ReportEmojiRule`), `app/research/nodes.py` and `app/research/graph.py` (the glossary flag to the
  rule renderers and
the research agent's builder).
- Dependencies: `regex` becomes a direct dependency (already installed transitively), and
  `types-regex` a dev dependency.
- Generated: `docs/generated-app-schema.json`.
- Docs: `docs/architecture.md`, report review's two calls.
- Configuration: every channel configuration that sets a client rule's `report_review` must rename
  it to `report_review_blind` when this ships; a configuration with the old name fails validation.
- Evals: the grounded review receives more rules, so its recall and its false positives on the
  source-selection rules need an eval run.
