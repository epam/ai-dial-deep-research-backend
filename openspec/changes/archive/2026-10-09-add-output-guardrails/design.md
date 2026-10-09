## Context

See proposal.md for the motivation. Today `QualityRule` has four parts, keyed by `RuleStep`, whose
values are the field names that `QualityRule.part` reads with `getattr`. The blind review renders
every rule's `report_review` part; the grounded review is hard-coded in
`render_grounded_review_prompt` to render `FAITHFUL_RELAY_RULES`' writer parts, the
`SOURCE_SELECTION_TERMS` and the writer's "No calculations" rule. Each policy's terms are its first
`QualityRule` ("Terms", "Faithful-relay terms"), with longer terms for the two research steps.

The faithful-relay texts were evaluated as they ship, with both reviews checking them, so none of
them changes except the blind part of "Gaps in the evidence". The source-selection texts change
only where rules 4 and 5 add to them.

## Goals / Non-Goals

**Goals:**

- Each rule says which review judges it, through its own field, for generic and client rules alike.
- The rendered text of the research agent's, research review's and writer's prompts changes only
  by the new policies' blocks and the source-selection edits.
- New rule texts are written in simplified technical English: short sentences, one idea per
  sentence, a list instead of a chained sentence.

**Non-Goals:**

- No change to how the reviews are called, their models, their effort or their message layout.
- No removal of the duplicated faithful-relay or source-selection checks. That waits for an eval.
- No grounded notes for the source-selection rules now (see Risks).

## Decisions

### 1. One `RuleStep` member per field

`RuleStep` gets five members whose values are the field names: `research_agent`,
`research_review`, `report_writer`, `report_review_blind`, `report_review_grounded`.
`QualityRule.part` stays a plain field read, and a new model validator rejects a rule that sets
both review fields. Its error names the rule.

*Alternative rejected:* a writer-part fallback inside `QualityRule.part` for the grounded step. It
would hide a policy decision in a field accessor, and client rules would inherit it: every client
writer part would silently become a grounded check.

*Alternative rejected:* keeping a `report_review` alias. The field is renamed outright; the channel
configurations are migrated in the same release (see Migration).

### 2. A per-policy flag routes the grounded review to the writer parts

`GenericPolicy` gets `grounded_by_writer_parts: bool`, set on the source-selection and
faithful-relay policies, and a method that maps a step to the field whose parts render in that
step's prompt:

```python
def rule_step(self, step: RuleStep) -> RuleStep:
    if step is RuleStep.REPORT_REVIEW_GROUNDED and self.grounded_by_writer_parts:
        return RuleStep.REPORT_WRITER
    return step
```

The import-time `__post_init__` check uses `rule_step`: every step for which some rule, in `rules`
or in `glossary_rules`, has a part needs a heading and, when the policy has terms, a terms entry;
and a writer-parts policy whose rule sets `report_review_grounded` is rejected, since that part
would never render. Checking at import keeps a gap from surfacing only on a glossary channel or in
the first turn.

*Alternative rejected:* the faithful-relay and source-selection rules set `report_review_grounded`
to a copy of their writer text. They already set blind parts, so this breaks the "never both"
validator, and it duplicates evaluated texts.

### 3. Terms are a policy attribute keyed by step

`GenericPolicy` gets `terms_name: str | None` and `terms: Mapping[RuleStep, str]`. `render_policy`
renders the rule parts first and returns `""` when there are none, so terms alone never make a
block. Otherwise it puts `### {terms_name}\n\n{terms[step]}` before the parts, which is
byte-identical to today's leading terms rule. The source-selection policy maps the two research
steps to the terms plus "Reasonable attempt", and the writer and both reviews to the terms alone.
`_TERMS` in `faithful_relay.py` is exported as `FAITHFUL_RELAY_TERMS`.

The language-and-style policy uses the same mechanism for the definition of a verbatim name, under
the name "Verbatim names", so that the grounded review, which judges "Names, not codes", receives
the exemption too. A rule cannot carry it there: a rule with a blind part may not also set a
grounded part.

### 4. Glossary-only rules are a second tuple on the policy

`GenericPolicy` gets `glossary_rules: tuple[QualityRule, ...] = ()`, rendered after `rules` only
when the channel configures a glossary. `render_policy` and `render_generic_rules` take
`glossary: bool`, and every caller passes `glossary is not None`. A flag on `QualityRule` was
rejected because it would leak into the client JSON schema.

### 5. The grounded review's instructions

`render_grounded_review_prompt(*, today_date, data_sources, source_kinds, glossary, client_rules)`
composes, in this order:

1. the existing opening and the claim-by-claim paragraph, unchanged;
2. `## Rules, judged against the findings`, with the sentence moved out of the faithful-relay block
   (text in the appendix);
3. `render_generic_rules(RuleStep.REPORT_REVIEW_GROUNDED, ...)`: the source-selection block with
   the source-kinds statement, its terms and its writer parts; the faithful-relay block with its
   terms and its writer parts; the terminology and language-and-style blocks with their grounded
   parts. The standalone `## Source-selection terms` section goes, because the source-selection
   block now carries the terms;
4. `## No calculations` with `NO_CALCULATIONS_WRITER_RULE`, a section of its own: as a `###` inside
   the faithful-relay block it would land under the last policy's heading;
5. `render_client_rules(client_rules, RuleStep.REPORT_REVIEW_GROUNDED)`, after "No calculations",
   since the client block says no client rule overrides it;
6. `render_client_writer_rules_context(client_rules)`: every client rule's writer part in a
   `<client_writer_rules>` block, introduced as context, not checks. It lets the grounded review ask
   for a missing value without asking for content a client rule excludes, and tells it which terms
   a client rule sets. All writer parts go, not only the content bans: the app cannot tell which
   client rule excludes content without a new field, and the block grows with the number of client
   rules and is read from the cache after the first round. The generic writer parts of the
   blind-judged rules are not passed: they hold nothing the grounded review needs against
   the findings, and would invite it to repeat the blind review's checks;
7. the data sources, the findings, "Not your job" and "Your answer", with the edits in the
   appendix.

The prompt is still rendered once per node build: the glossary flag and the client rules are fixed
for the channel.

`render_client_rules` uses a set of the two review steps to pick the "Client-specific checks"
heading.

### 6. The new policies live in their own modules

`app/research/language_style.py`, `terminology.py` and `prohibited_content.py` each hold their
rules, like `source_selection.py` and `faithful_relay.py`; the policies are defined in `prompts.py`
next to the existing two. The order is source selection, faithful relay, terminology, language and
style, removal. `ReportEmojiRule` joins `build_report_rules` in `report_rules.py`, after the
hyperlink rule. Its regular expression matches a pictograph with the variation selectors,
skin-tone modifiers and tag characters that follow it and any zero-width-joined pictographs, a
lone skin-tone modifier, a flag and a keycap (see **report-composition**).

### 7. Comments

`render_grounded_review_prompt` carries the comment on why both reviews check the faithful-relay and
source-selection rules, and on the known false-positive risk: the blind parts' guarding sentences
(the Dates rule's year column, the Missing evidence rule's "a statement that the sources do not give
it satisfies the check", the disagreements rule's "a figure computed from values of different facts
merges no values for one fact") do not reach the grounded review.

## Risks / Trade-offs

- [The grounded review flags correct drafts under the source-selection rules, lacking the guarding
  sentences of their blind parts.] → No grounded notes now. The eval of this change checks the
  grounded review's source-selection items for such mistakes; if they appear, the sentences are
  added as grounded notes in a change evaluated on its own. The code comment states the risk.
- [The grounded review's recall drops as it carries more rules.] → The eval watches its recall;
  splitting it into several calls is the fallback.
- [A failed grounded call loses every grounded-only check for that round: names, terms, the client
  grounded parts.] → Accepted. The blind review keeps the faithful-relay and source-selection checks
  as a backstop.
- [The grounded review asks for a value that a client rule excludes.] → It asks for a value the
  findings hold when a rule asks the report to give it, unless a rule keeps that content out, and
  it reads the client rules' writer parts as context to know what they keep out. If it asks anyway,
  the removal rule tells the writer that an exclusion holds even when a review asks for the
  content, so the cost is a revision round, not a leak.
- [The grounded review starts re-checking the client content bans, which the blind review judges.]
  → The context section says the rules are context, not checks, unless a client check names them.
- [The blind glossary check 8 asks for the glossary term where the writer kept a source's term
  because it was not sure the two name the same concept.] → Accepted for now: check 8 and the
  glossary rule already apply only to "a concept that a glossary term names", and both are shipped
  texts this change does not touch. The eval watches for such revisions.
- [The emoji check flags pictographic arrows and symbols, such as ↗ and ⚠, that a writer may use
  for trends or warnings.] → The writer instruction names them as emojis.
- [An admin writes a client exclusion rule as a grounded part.] → The `report_review_grounded`
  field description says that a check that excludes content belongs in `report_review_blind`,
  because only there does the removal rule govern it and does "Gaps in the evidence" exempt it.
- [A plan item names a source whose value the report correctly leaves out, and the blind review
  reads the item as unanswered.] → "Gaps in the evidence" judges the facts the plan asks for, and
  says that a plan item naming a source is answered when its fact is.
- [A configured section name or description carries an emoji, so no draft can pass both the
  structure check and the emoji check.] → Not handled for now. Rejecting emojis in section names at
  validation is left for when a configuration needs it.
- [A channel configuration still using `report_review` fails validation.] → Migrate every
  configuration in the same release; the error names the unknown field.

## Migration Plan

1. Ship the backend change.
2. In the private client-configuration repository, rename every client rule's `report_review` to
   `report_review_blind`, apply that repository's client-rule edits, and regenerate the configs
   against the new backend (its generator validates against `ApplicationProperties`).
3. Deploy both together. Rollback is the previous backend with the previous configs.

## Appendix: agreed prompt texts

These texts were agreed word for word. Code uses them as written; line breaks may move to fit the
100-column limit.

**Language and style — writer heading:** "Language and style" / "These rules govern the report's
wording." **Blind heading:** "Language-and-style checks" / "Check the draft's wording against each
rule below. The part "Verbatim names" defines the words the checks use. These checks are rules, not
wording preferences." **Grounded heading:**
"Language and style, judged against the findings" / "Check the draft against the rule below."

Verbatim names (the policy's terms, rendered in the writer, blind and grounded blocks):

```text
A verbatim name is a publication title, a dataset or series name, an organisation's name, or a
quotation from a source. Write a verbatim name exactly as its source writes it. The rules of this
section do not apply inside a verbatim name. One exception: emojis. The application rejects an emoji
everywhere, also inside a quotation.
```

Glossary-only rule "Glossary terms are verbatim names". Writer: `A glossary term is also a verbatim
name. Write it in one of the forms that the glossary-terminology rule allows.` Blind: `A glossary
term is also a verbatim name. Its allowed forms are not violations: any one name of a term that
lists several names separated by a slash, the abbreviation after the full form's first use, and a
lower-case first letter in mid-sentence.` The blind part names the forms itself, because the blind
prompt carries the glossary-terminology rule only when the glossary check runs.

("The rules of this section" rather than "the rules below": in the writer's prompt the removal rule
and the client rules also come below, and a client exclusion must apply inside a quotation too.)

Neutral register — writer:

```text
Describe what the sources say in precise, neutral terms. Do not use informal wording. Do not use
wording that sells, persuades or dramatises, such as "remarkable", "game-changing" or "a must". Do
not speculate.
```

Neutral register — blind:

```text
Informal, persuasive, promotional or speculative wording is a violation. Name the passage. These
are correct wording, not speculation:
- a forecast that the draft names as a forecast;
- a source's own hedging, such as "the publication expects".
```

No exclamation marks or slang — writer: `Do not write exclamation marks. Do not use slang. A
verbatim name keeps its own punctuation.` Blind: `An exclamation mark outside a verbatim name is a
violation. Slang is a violation.`

`ReportEmojiRule` — writer instruction: `## No emojis` / `Do not use emojis anywhere in the report:
not in prose, headings, lists or tables. Pictographic arrows and symbols, such as ↗, ⬆, ✔ and ⚠,
count as emojis.` Violation: `The draft contains these emojis: {emojis}.
Remove each one. If an emoji stands for a word, such as a check mark for "yes", write the word.`

Names, not codes — writer (narrowed on review to codelist codes and dataset ids, where codes
actually reach a report):

```text
Refer to a codelist value, such as a country or an indicator, by its name, not by its code: "United
States", not `USA`; "Gross domestic product, constant prices, percent change", not `NGDP_RPCH`.
Refer to a dataset by its name, not by its id: "World Economic Outlook", not `IMF:WEO(1.0.0)`. Do
not write a code next to its name. Use a dataset id only inside a citation marker, such as
`[dataset IMF:WEO(1.0.0)]`.
```

Names, not codes — grounded:

```text
A codelist code or a dataset id outside a citation marker is a violation. Name the code or the id,
and give its name from the findings or the data sources.
```

**Terminology — research agent heading:** "Terminology" / "This rule says how you search for a
concept that the glossary names." **Writer heading:** "Terminology" / "These rules say which term
the report uses for each concept." **Grounded heading:** "Terminology, judged against the
findings" / "Check the draft against the rule below."

Glossary terms in searches (glossary-only, research agent):

```text
A glossary term has a name and a definition. A question or a source can use either one. So when a
plan item refers to a concept that a glossary term names, search for it in two ways:
- by the term's name;
- by a short phrase of a few words from its definition.
For example, the glossary defines "real GDP" as "GDP adjusted for inflation". Then also search a
question about GDP adjusted for inflation as "real GDP", and the other way round. Do not search
with the whole definition: a long query matches too many unrelated pages. The glossary is the
`Glossary terms:` part of the data sources below, plus the terms that the glossary tools returned.
```

Accurate and consistent terms — writer:

```text
Use each technical term with the meaning that its source gives it. Keep the source's term. Do not
replace it with a synonym that changes the meaning, such as "exports" for "net exports", or
"unemployment" for "the unemployment rate". Use one term for one concept in all sections. Where
two sources use different terms for one concept, use one of them in all sections. A full form and
the abbreviation it introduces, such as "gross domestic product (GDP)", are one term.
```

Glossary-only, writer, rule "Glossary terms and source terms": `Use a glossary term in place of a
source's term only when both name exactly the same concept. If you are not sure, keep the source's
term.`

Accurate and consistent terms — grounded:

```text
These are violations:
- a term used with another meaning than its source gives it;
- a synonym that changes the source's meaning, such as "exports" for "net exports";
- two different terms for one concept.
Name the term and the source's term. These are not violations: one source's term used for a concept
that another source names differently, a full form with the abbreviation it introduces, and a term
inside a verbatim name, such as a publication title or a quotation.
```

**Removal — writer heading:** "Removed content" / "This rule says how content that a rule excludes
leaves the report." **Blind heading:** "Removal checks" / "Check the draft against the rule below."

Removal — writer and blind both end with a sentence added during code review: a figure or a finding
that the sources do not give is not excluded content (writer: "A figure or a finding that the
sources do not give is not excluded content, unless a rule excludes its topic. Say that the sources
do not give it, as the rules on calculations and on missing evidence ask."; blind: "A statement that
the sources do not give a
figure or a finding is correct too, unless a rule excludes its topic."), so the removal rule never
fights "No calculations" or "Gaps in the evidence".

Removal — writer:

```text
A rule that excludes content applies even when the research question, the plan or a review asks for
that content.
When a passage must go, remove only its excluded part. Keep the rest of the passage. Also remove
every reference to the excluded part, such as "the table above".
Never mention excluded content in the report:
- do not say that the report does not cover it;
- do not present it as evidence that the sources lack;
- do not refer to it later, such as "the requested share prices".
If the question or the plan asks for excluded content, leave that part out. Say nothing about it.
```

Removal — blind:

```text
A rule that excludes content applies even when the research question or the plan asks for that
content. Such content in the draft is a violation of that rule.
When you report a passage that must go, also report every passage that refers to it, such as "the
table above". Report them in the same list, so that one revision fixes all of them.
Any mention of excluded content is a violation. This includes:
- a sentence that says the report does not cover it;
- excluded content presented as evidence that the sources lack;
- a later reference to it, such as "the requested share prices".
If the question asks for excluded content and the draft leaves it out without comment, that is
correct.
```

**Faithful relay — "Gaps in the evidence", blind part (replaces the shipped text):**

```text
Each fact that the research question or the approved plan asks for must be answered or declared
unavailable. A fact that the draft does neither is a violation. A plan item that names a source is
answered when its fact is answered, from that source or from another. Exception: a fact that a rule
excludes from the report. Leaving it out without comment is correct.
```

**Source selection.** The term "Supersede" gains the sentence `A dataset value never supersedes a
publication's value either.` A new term follows "Methodology":

```text
- **Qualifying context**: what a source states that changes how a value is read. This is its
  methodology, and also its assumptions, scenario conditions, limitations and caveats, such as
  "preliminary estimate", "the baseline assumes unchanged policies" or "excludes financial
  services".
```

"The dataset value" — writer, after "…its value is never superseded.": `A dataset value never
replaces a publication's value either. Give both, each with its citation and its stated date,
unless the publication's value is obviously outdated or irrelevant.`

"Methodology" is renamed "Qualifying context". Research agent: the shipped text with "the
methodology that affects how it is read, wherever the sources document one" replaced by "its
qualifying context, wherever the sources document it". Research review: the shipped text with "a
methodology that the findings show is documented" replaced by "qualifying context that the findings
show is documented". Writer: `Give a value's qualifying context with the value, where it
materially affects how the value is read.`

The source-selection grounded heading: "Source selection, judged against the findings" / "These
rules say which values the report gives for each fact, and how it presents them." The
faithful-relay grounded heading: "Faithful relay, judged against the findings" / "These rules keep
the report to what the sources say: it invents, infers and computes nothing."

**Grounded review prompt.** The rules preamble, moved out of the faithful-relay block:

```text
## Rules, judged against the findings

Each rule below says what the report must do, or what counts as a violation. The research
transcript before these instructions is the findings: judge the draft against it, and report every
passage that breaks a rule.

Some rules ask the report to give a value or its context, such as both a dataset value and a
publication value for one fact. When the findings hold such a value and the draft leaves it out,
report it and ask for it to be added, unless a rule keeps that content out of the report.
```

The client writer rules section, after the client checks and before the data sources:

```text
## This deployment's writer rules

The writer follows the rules below, which come from this deployment's configuration. They are
context, not checks: do not report a passage under them, unless a client-specific check above names
it. Use them to know which content the report must leave out and which terms it must use. Never ask
for content that they keep out of the report.

<client_writer_rules>
{rules}
</client_writer_rules>
```

"Not your job": the bullet "which term or name the report uses for a concept: this deployment's own
rules may set it, and you are not shown them" becomes "which of two terms with the same meaning the
report uses for a concept: this deployment's own rules may set it"; a new bullet: "whether the draft
answers every part of the question and the plan: another check judges this, and this deployment's
own rules may keep a part out of the report".

**Writer prompt.** The list in "These rules outrank the request" gains "the rules that exclude
content", placed after the "No calculations" rule and before the two colon-introduced lists, so it
cannot read as one of the faithful-relay rules, so that `REPORT_REQUEST`'s "covering every item of
the plans" never reads as an order to
cover an excluded topic.

"Your answer":

```text
## Your answer

Answer with a numbered list, one item per violation. Start each item on a new line with its number,
a full stop and a space, such as `1. `, with nothing before the number. Indent every further line of
an item. Each item names the rule it breaks, quotes the passage exactly, says what the source says
instead, and says what to change. A violation that the draft repeats in several places is one item
that quotes every place. For example:

1. No inference: "Higher interest rates caused the slowdown." No source states a cause. The source
   says only that growth fell from 3.1% to 2.4%. Remove the cause.
2. Names, not codes: "`USA`" in the table of growth by country. The findings name it "United
   States". Write the name.

If the draft breaks none of the rules above, answer with exactly `No violations.` and nothing else.
Do not call any tool.
```

**Blind review prompt.** "Not your job" gains "whether the draft carries an emoji" among the things
the app checks, and "The app checks the last four itself" becomes "the last five".
