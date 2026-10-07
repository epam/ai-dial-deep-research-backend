## Context

`QualityRule` bundles up to four step parts, and `render_source_selection` renders
`SOURCE_SELECTION_RULES` into each step's prompt through a `{source_selection}` placeholder,
followed by the client rules. The report-review node (`make_report_review_node` in
`app/research/nodes.py`) runs one structured call, `review_call()`, in an `asyncio.gather` with
`lookups.prefetch(draft)`, then prepends the app-checked violations to the call's list and builds
one `ReportReviewOutcome`, whose `revision_instruction` routes the loop. The report node sends the
writer `_strip_status_calls(state["messages"])`, the transcript with images and without status
calls.

The grounded review's layout was measured offline before this change, as variant V9 of an evaluation
harness outside this repository: a neutral system message, the writer's transcript, the rules as a
trailing `developer` message, and the request with the draft as a second one. This change ports
that layout, with plain system messages in place of the two `developer` ones (decision 6).

## Goals / Non-Goals

**Goals:**

- One renderer for every generic policy, so faithful relay renders exactly as source selection
  does, and a later policy adds a module and a registry entry.
- The grounded review as a second call in the existing review node, with no change to the
  loop's routing, its budget or the revision request.
- The prompt text the steps already carry stops contradicting the new rules.

**Non-Goals:**

- The other output-quality policies (terminology beyond the glossary fixes, language and style,
  prohibited content, qualifying context), the emoji check and the `regex` dependency.
- Source-selection checks against the transcript. The grounded review carries the source-selection
  terms, so the faithful-relay rules that use them resolve, but not the source-selection rules.
- Filtering the transcript to the sources the draft cites. It needs a contract between a citation
  and a tool result, and parsers.
- Any change to reasoning efforts. Research review and the blind review stay at `medium`.
- Further edits to the blind review's prompt, such as asking it to name every offending passage.
  Its prompt gains only the faithful-relay review parts and the sentences that must agree with them.

## Decisions

### 1. A `GenericPolicy` groups a policy's rules with its per-step headings

`prompts.py` gains a frozen dataclass `GenericPolicy`: per-step heading and opening sentence, the
rules, and a flag saying whether the block opens with the statement of the channel's kinds of
source. `GENERIC_POLICIES` holds source selection, then faithful relay.
`render_generic_rules(step, source_kinds)` renders every policy with a part for the step as its own
`## <heading>` block and replaces `render_source_selection` in all four prompts, through the
placeholder renamed `{generic_rules}`. `GenericPolicy` checks at import that every step one of its
rules has a part for has a heading, so a missing heading fails every test run rather than a turn.

- *Why source selection first:* the faithful-relay terms refer to the source-selection terms (value,
  stated date, described period).
- *Alternative considered:* appending the faithful-relay rules to `SOURCE_SELECTION_RULES` under one
  heading. Rejected: each policy's opening sentence tells the step how to read its rules, and the
  two policies' terms are separate lists.
- *Alternative considered:* the local prototype's glossary-only rules on `GenericPolicy`. Left out:
  no shipping policy has a glossary-only rule.

### 2. The rules live in `app/research/faithful_relay.py`

One tuple, `FAITHFUL_RELAY_RULES`, beside `source_selection.py`, ported from the local prototype
with the three approved additions (Certainty, No distortion, Forecasts and estimates), the
search-answer warning in the "Source" term and in "Only the sources", and the review part of
Forecasts and estimates for a draft that states a dataset's last update. The rule texts name no
client, dataset, publication or tool; the research agent's tools guidance in `prompts.py` is where
`rag_search` and `get_pages` are named.

### 3. The grounded review's prompt is built from the same rule texts as every step's

`prompts.py` gains the grounded review's neutral system message, its instructions template and a
renderer. The renderer takes the writer part of each faithful-relay rule through `render_rules(...,
step=REPORT_WRITER)` and the source-selection terms from the source-selection module's terms
constant, so a rule edit reaches the writer and the grounded review together. The review request is
the existing `REPORT_REVIEW_REQUEST`, filled exactly as for the blind review, sent as a system
message.

The instructions follow V9's rendered text: the report-check intro with the instruction to name
every passage, the rules "judged against the findings", the data sources, the note that the
transcript is the findings and that a search answer is not support, the "Not your job" section
adapted to a reviewer who sees the findings, and the numbered-list answer format.

Four deliberate differences from V9:

- **The source-selection terms are added.** V9 sent "the source-selection terms above apply here
  too" without the terms. The offline measurement of this change measures the fix.
- **No client rules.** V9 included one client rule that the harness mapped to faithful relay by
  name. A client rule carries no policy, so the app cannot tell which client rules are about
  faithful relay, and giving the grounded review all of them dilutes it with rules it cannot judge
  better than the blind review. The blind review keeps every client rule's review part. A client
  rule can change what the writer does, such as replacing a source's term for a concept, so the
  grounded review's "Not your job" list says that the term a report uses for a concept is not its to
  judge. Any other conflict between a client rule and the grounded review shows as a false item in
  the measured precision.
- **No glossary tool results.** V9's instructions carried them because it reused the blind review's
  prompt tail. The grounded review carries no terminology rule, and the transcript already holds
  those results.
- **Claim by claim, one item per wrong claim, and no citation checks.** Measured as built first (the
  V9 instructions with the terms and the rule additions), the grounded review reported one item per
  rule: a rule broken by several wrong facts got one item naming one of them, and items about
  uncited summaries, which the blind review already reports, took the place of severe misrelays. The
  grounded review is therefore told to compare every claim that states a figure, a forecast or
  estimate, a comparison, a cause or a characterisation with the source passage it relays, with the
  four kinds of severe misrelay named, then to check the rest of the rules; to answer with one item
  per wrong claim, quoting the passage and what the source says instead; and that citation presence
  is not its job. A further variant that added a concrete trigger to each kind of severe misrelay
  was measured and dropped: it found no more.

- *Alternative considered:* a JSON schema for the answer. Rejected: a schema is part of the cached
  prefix and the plain list was what was measured.
- *Alternative considered:* the review parts of the rules. Rejected: they tell a reviewer that
  cannot see the sources what not to judge, which is exactly what this call judges.

### 4. The grounded review is a second coroutine in the review node's `gather`

`review_call()` becomes `blind_review_call()`, and `make_report_review_node` gains
`grounded_review_call()`, built like it. Its messages come from a module-level function in
`nodes.py`, `grounded_review_messages(...)`, and its answer is read by another,
`parse_review_items(text)`, so the offline evaluation harness imports both rather than copying them.
The messages are `SystemMessage(neutral)`, `*_strip_status_calls(state["messages"])`, then the
instructions and the request as two more plain `SystemMessage`s, which `langchain_openai` sends with
the `system` role. It calls `get_chat_model(LLMModelConfig(reasoning_effort= MEDIUM))` behind
`with_stream_drop_retry`, with no tools and no structured output. The three coroutines run in one
`asyncio.gather`; the violations become `[*rule_violations, *review_items, *grounded_items]`.

The answer is parsed into items by its numbered lines, with the other lines after an item joined to
it. A line opens an item only when it starts, unindented, with the next number in sequence, so an
indented sub-list or a line starting with a year stays in its item. An answer that is "No
violations", ignoring case, Markdown wrapping (backticks, asterisks, underscores, quotes) and
trailing `.`, `!`, `;` or `:`, gives no item; any other answer goes through the numbered-line parse,
so an answer such as "No violations of the other rules. 1. …" keeps its item. A non-empty answer
with no numbered line becomes one item, so a violation is never dropped silently. An empty answer
raises `EmptyReviewAnswerError`, so it is a failed grounded review and never an approval: a model
can spend all its output on reasoning and return no text.

Each review call returns its items and its failure kind; on a failure it returns no items and
logs a warning. `ReportReviewOutcome` renames `error` to `blind_review_error` and gains
`grounded_review_error`, so the stage can record which review failed; the stage title carries the
error mark when either failed.

Each review call logs one INFO record, `Report blind-reviewed` or `Report grounded-reviewed`, with
the draft number, its duration, its message count, its item count, its failure kind and
`format_token_usage(...)`, which includes `cache_read`. `Report reviewed` becomes the node's
summary: the draft number, the node's duration, the outcome, the word count, the ceiling and the
merged list's violation count. It no longer carries the blind review's message count, error and
token usage, which its own record holds.

### 5. Measured offline: below the recall threshold, at reasoning `medium`

The blind review and the grounded review, built from this branch's own prompt functions, were run
twice on a small internal set of judged drafts and graded blind against their severe faithful-relay
violations. The claim-by-claim instructions that ship found more of them than the first build and
than the variant with a concrete trigger per kind, at a similar precision; the figures are recorded
outside this repository.

The acceptance threshold of 70% severe recall is not met: the grounded review that ships finds a
little over half of the severe violations, while its precision clears the 70% threshold. The blind
review alone finds about a quarter. The reasoning effort was not raised, by the user's decision. The
violations no variant finds are one-word or one-scope shifts inside a cited claim, such as an
estimate stated as observed, a hedged view turned into an outcome, a verdict relayed with a word of
the opposite weight, a figure for a part stated for the whole, and a cause given for one part
attributed to the whole. On live runs the delivered reports carried far fewer severe violations than
the base commit's.

### 6. Reasoning effort `medium`, and a cache nothing depends on

The grounded review runs at `medium`, as the blind review does, for the turn-time target: in the
offline measurement it took about a minute per call against about a minute and a half at `high`, at
a lower recall and precision. Its prompt cache can hold across review rounds because the transcript
is the last part of the prefix every round shares and the trailing system messages do not end a
cacheable prompt; a trailing user message would. The faithful-relay spec, "The grounded review
checks the draft against the sources", gives the reason for each message's position, the measured
provider behaviour and the conditions the layout keeps. It also records why the grounded review
does not open with the research agent's system prompt and tools to reuse that call's cache entry,
with the premises under which that choice should be reconsidered: the reasoning efforts differ, a
hit is uncertain even on an exact prefix, and the research agent's instructions would precede the
review's. The differing tool lists are not a premise: the tools can be bound and their calls
forbidden through `tool_choice`, which keeps the tool list the cache needs.

The two trailing messages use the plain system role. V9 used `developer`, but in the internal cache
ablations a trailing `developer` message and a trailing system message both left the transcript
cached, with hit rates within the noise of the measurement, so nothing favours the `developer`
role. The switch is not measured for recall or precision; the role of two messages that already
follow a system message is not expected to change what the model reports, but this is
unverified. The log record's `cache_read` measures the cache, and no behavior depends on it.

### 7. The edits that ship with the rules

From the local prototype, only what keeps the prompts consistent with faithful relay:

- Writer citations bullet: an uncitable sentence stays only where "Only the sources" allows it;
  the "flag it as your own synthesis/inference" branch goes.
- Writer "never include": the honest-qualification bullet drops "when a statement is your own
  inference".
- Writer data sources: a fact from a publication series description names the series in words.
- Writer outrank list: after the "No calculations" rule and the source-selection prohibitions, two
  faithful-relay rules, infer nothing and keep every figure as its source gives it; saying that the
  sources do not give a figure or an explanation is about the evidence. The single exception for
  declined requests stays the one for differing values. The paragraph also says that a section's
  description does not override the "No calculations" rule or these two rules: a channel's own
  description that asks for implications or a computed figure would otherwise send the grounded
  review and the writer round the loop until the version budget ran out.
- Report review check 1: uncited text is accepted only where the "Only the sources" check accepts
  it. Its "Check exactly these" sentence names every rule section below.
- Research review: its search-summary gap covers findings and characterisations and accepts a chunk
  returned word for word; its task sentence, gap bullet and output schema descriptions name every
  rule section.
- Research agent: the tools guidance says why a `rag_search` summary is not evidence and that every
  figure comes from `get_pages`, and that `retrieve_text_chunks` returns the documents' own text;
  its checklist item and its failed-tool exception name every rule section.
- Preparation: the restated query keeps the user's formatting requests.
- Default sections: "Detailed Analysis" asks for what the sources say and how their findings
  compare; "Conclusion" for a summary of what the findings answer and cannot answer.
- `GLOSSARY_TERMINOLOGY_RULE`: the three glossary fixes.

### 8. The rule that nobody calculates comes from the change `2026-10-02-no-calculations`

That change, merged before this one, ships the rule as plain prompt text at every step: a bullet
in the research agent's strategy, a paragraph in research review's next-steps text, a `## No
calculations` section in the writer prompt built from `CALCULATION_DEFINITION`, and check 7 of the
blind review. Its wording wins wherever the two changes overlap, so this change keeps no
faithful-relay rule "No calculations" and restates none of it. Three things remain this change's:

- **The grounded review judges it too.** `NO_CALCULATIONS_WRITER_RULE` holds the writer's section,
  and both the writer prompt and the grounded review's instructions render it, the latter as
  `### No calculations` after the faithful-relay writer parts. The blind review sees only a number
  the draft presents as computed; the grounded review also sees a computed number the draft
  presents as stated.
- **The "Calculation" term** in the faithful-relay terms uses that change's definition, so the
  terms and the rule cannot disagree about what a calculation is.
- **Flagged inference is not allowed.** That change's requirement "Reports contain no calculations"
  allowed an uncited sentence flagged as the report's own inference, which rule 1 of this change
  forbids; this change modifies the requirement to drop the allowance.

Where the two changes edit the same prompt sentence, the other change's wording is kept: research
review's next-steps paragraph, and the "Other sources and disagreements" review part, which says
that report review's "No calculations" check covers a figure computed from two facts.

### 9. The two review calls are named by what they see

The **blind review** sees the draft, the configuration, the question and the plan, but not the
findings; the **grounded review** also sees the research transcript. The names say why the two can
judge different things, and they replace "the review call" and "the faithful-relay check" in code,
log records, the stage text, the specs and the architecture page. The prompts the model reads keep
their own wording: the grounded review's instructions still call it "the report check", because the
model does not need the name.

## Risks / Trade-offs

- [The grounded review reports a fault the blind review also reports, so the writer gets two items
  for one fault] → The offline and live measurements count duplicates; the grounded review's
  instructions are trimmed only if they are frequent.
- [At `medium` the grounded review misses more severe violations than at `high` and is less precise]
  → The user chose `medium` for time. The rule additions target the misses, and the offline
  measurement reports the result against the 70% thresholds without changing the effort.
- [A false item forces a revision, and a revision can introduce new faults] → The grounded review's
  precision is measured; the version budget still bounds the loop.
- [A long transcript passes the model's long-context threshold, where input costs twice as much] →
  Accepted: the writer already reads the same transcript. The cost per review round is reported.
- [The grounded review adds wall time when it is slower than the blind review] → Both run
  concurrently, so the node takes as long as the slower call; the live runs report each call's
  duration.
- [Source-selection violations that need the transcript stay uncaught, such as an ignored newer
  value] → A known gap, out of this change's scope.

## Migration Plan

No configuration migration: the change is in the generic prompts, the report-review node and the
default section descriptions. A channel that configures its own report structure keeps its own
descriptions. Rollback is reverting the change.
