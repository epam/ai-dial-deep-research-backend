## MODIFIED Requirements

### Requirement: Reports respect a configured word ceiling without abrupt truncation

The report SHALL respect a configured word ceiling (`max_report_words`, default 2750, see the
**application-config-schema** capability). A report's length SHALL be measured as the number of
whitespace-separated tokens in the draft's Markdown text **after removing the inline citations**,
and that one definition SHALL be used everywhere a length is stated — in prompts, in the review
stage and in logs alike.

The ceiling bounds what the writer chooses to say, and it is measured over the draft the writer
produced. A citation's length is not that — it follows from the source it names — so counting it
would let a well-sourced report be revised for its sourcing.

**The references section is outside the measure because it is outside the draft.** The application
writes it after the loop settles (see **report-citations**), so no draft carries it and no exemption
is needed; its length follows from how much the research cited and never consumes the writer's
budget. The report writer SHALL be told what the count leaves out, so a writer is never promised
room the count does not give.

A draft that writes a references section **anyway** SHALL lose nothing from the count: that heading
is a structure violation the review step reports, and a violation SHALL NOT also earn length budget.
Nothing removes it at delivery either — the app appends its own section and takes no text out (see
**report-citations**) — so the revision loop is the only thing that can, and a draft that spends its
last version still carrying one is delivered with that section followed by the built one.

Length is never a model's judgement: it is measured in Python and enforced deterministically (see
below). Where a model does need a length, it is supplied as a number rather than left for it to
count: the writer SHALL be told the ceiling, and a revision SHALL be told the draft's measured
count alongside the ceiling. The review step SHALL be told neither — it judges the content rules
only.

The ceiling SHALL NOT be enforced by truncation:

- No token cap SHALL be placed on the report model call. Measured behavior, not caution: a capped
  call returns `finish_reason="length"` and stops mid-sentence rather than wrapping up (see
  design.md).
- A revision that shortens an over-long draft SHALL rewrite it to fit by stating the same content
  more concisely — condensing sections, tightening prose, merging overlapping passages — and SHALL
  NOT cut a sentence, a list, a table, or a section short. It SHALL NOT drop a fact to fit: every
  value the draft reports, with its citation and its dates, stays in the revision, unless another
  item of the same revision instruction asks to change it (see **source-selection**, where
  omitting a relevant value costs more than including one). The length violation's text SHALL ask
  for exactly this and SHALL NOT ask to cut detail.
- The delivered report SHALL end at a clean boundary: a complete sentence closing a complete
  section, followed by the References section the app appends.

The ceiling is an upper bound, not a target. A draft already under the ceiling SHALL NOT be
expanded or padded to approach it. A draft whose measured count equals the ceiling exactly SHALL be
treated as within it.

**Exceeding the ceiling SHALL force a revision deterministically, in Python, not on the review
model's opinion.** While the version budget allows, a draft whose measured count is above the
ceiling SHALL be revised regardless of the review step's verdict — including when that verdict
approves the draft, and including when the review call failed and produced no verdict at all. The
count is app-owned and needs no model, so a model that approves an over-long draft SHALL NOT be
able to end the loop on it. The model's verdict governs the other criteria only.

A revision forced on the count alone SHALL still arrive with a concrete instruction: the app SHALL
render one from the draft, its measured count, and the ceiling, directing a rewrite that shortens to
fit rather than cutting. Where the review step also returned violations, the two SHALL be given
together as one instruction.

#### Scenario: Over-long draft is revised with the numbers stated

- **WHEN** a draft measures 3,910 words against a ceiling of 2,750
- **THEN** a revision SHALL be required regardless of the review step's output, and the
  revision instruction SHALL state the measured count and the ceiling

#### Scenario: Shortening rewrites rather than truncates

- **WHEN** an over-long draft is revised to fit the ceiling
- **THEN** the revised report SHALL contain every configured section that the original filled,
  each ending in a complete sentence, and SHALL NOT end mid-sentence or mid-table

#### Scenario: The length violation asks to condense without dropping a fact

- **WHEN** a draft measures above the ceiling and the app renders the length violation
- **THEN** the violation text SHALL ask to state the same content more concisely, SHALL say that
  every reported value stays with its citation and its dates, and SHALL NOT ask to cut detail

#### Scenario: No token cap on the report call

- **WHEN** the report model call is issued, for the first draft or any revision
- **THEN** it SHALL carry no maximum-token limit imposed by the app for the purpose of bounding
  report length

#### Scenario: Short draft is left alone

- **WHEN** a draft measures 900 words against a ceiling of 2,750 and satisfies the other report
  rules
- **THEN** the review step SHALL approve it, and no revision SHALL be requested on length
  grounds

#### Scenario: An approving verdict cannot pass an over-long draft

- **WHEN** the review step approves a draft measuring 3,100 words against a ceiling of 2,750 and
  the version budget is not exhausted
- **THEN** a revision SHALL still be written, on the measured count alone

#### Scenario: A draft exactly at the ceiling is within it

- **WHEN** a draft measures exactly 2,750 words against a ceiling of 2,750
- **THEN** no revision SHALL be forced on length grounds

#### Scenario: Citations do not consume the budget

- **WHEN** a draft's Markdown holds 2,950 whitespace-separated tokens, of which 200 are inline
  citations, against a ceiling of 2,750
- **THEN** its measured length SHALL be 2,750 and no revision SHALL be forced on length grounds

#### Scenario: The app's References section never consumes the budget

- **WHEN** a draft measuring 2,600 words is delivered and the app appends a References section of
  400 words, against a ceiling of 2,750
- **THEN** the measured length SHALL remain 2,600, no revision SHALL be forced on length grounds,
  and the delivered report SHALL carry both

#### Scenario: A references section the writer wrote is measured with the rest

- **WHEN** a draft carries a `## References` section of 400 words, and the configured structure's
  references section is named `References`
- **THEN** those words SHALL count toward the ceiling like any other, and the heading SHALL be
  judged by the review step as a section-structure violation

### Requirement: A review ↔ revise loop enforces the report rules before delivery

A finished draft SHALL be judged by an independent review step before it is delivered. That
step SHALL read the draft, the configured report structure, the protected sections, and the
research question and plan — the last two because they are where a user's formatting instruction
lives, and without them the step cannot tell a legitimately-followed instruction from an
override of a protected rule. It SHALL judge the draft against the section content rules, the
protected sections and their rules, the prohibited meta-annotations, well-formed Markdown, the
citation format rules the **research-execution** capability defines, and the report-review part of
every quality rule: the generic source-selection rules and the channel's client rules (see
**source-selection**). The source-selection parts judge only what the draft shows — how two values
for one fact are presented, whether a value states its dates, whether a near match says how it
differs — because the step never sees the sources. The section structure, the word
ceiling and the absence of hyperlinks are not its to judge — the app checks those itself (see the
requirement above). The citation-format check becomes load-bearing with this change: the app parses
those markers out of the delivered report (see **report-citations**), so a draft that adopted
numbered footnotes would yield no pills at all, and this step is what pushes it back to the defined
form. It SHALL NOT be given the measured word
count or the ceiling: length needs no model — the app measures it and adds the length violation
itself (see the ceiling requirement).

The review step's structured output SHALL be the violations alone, one entry per rule the draft
breaks and naming what to change. There SHALL be no separate approval field: an empty list SHALL
mean the draft is approved, so a remark that is not meant to block delivery cannot be expressed —
every returned violation forces a revision.

The step SHALL NOT receive the research findings: every criterion above is decidable from the
draft, the configuration, and the query and plan.

**A failing review SHALL NOT cost the report.** If the review call fails — an unparseable
structured response, a provider error, exhausted transient-drop retries — the turn SHALL NOT fail
and the failure SHALL be logged as a warning. This departs deliberately from research-review,
which is fail-loud because a broken verdict there means research of unknown completeness; here the
report already exists, and discarding a finished multi-minute run over a formatting check is the
worse outcome.

A failed review leaves the app with no verdict, so the two rules compose in one order, which SHALL
be: the measured count still applies. An over-ceiling draft whose review failed SHALL be revised on
the app-rendered length instruction alone; a draft within the ceiling SHALL be delivered as the
answer. A reviewed draft always has a rewrite in budget — the review is gated on the budget below —
so a failed review never has to reason about an exhausted budget.

**A swallowed revision failure ends the loop, overriding the count gate.** It is the third delivery
case beside "within the ceiling" and "budget exhausted": an over-ceiling draft MAY therefore ship with
version budget still remaining, and that unresolved length SHALL be recorded in the logs exactly as
an exhausted budget is. The count gate above applies while revisions are still being written
successfully, not after one has failed.

**A failed revision SHALL NOT cost the report either.** Once a draft exists, no later failure in the
loop may discard it: if a revision's own model call fails — after its transient-drop retries, or on a
non-retryable error such as an exceeded context length, which a revision is likelier to hit than the
first draft was because its request is strictly larger — the **previous** draft SHALL be delivered
and the failure logged as a warning. The turn SHALL NOT fail. Before this loop existed the report was
written once and a failure had nothing to discard; adding revisions must not turn a finished report
into a failed turn.

When the review returns revision instructions, the report SHALL be rewritten against them and
judged again. The loop SHALL be bounded by a configured version budget (`max_report_versions`,
default 3, counting the first draft and every rewrite as one version each): a draft SHALL be
reviewed only while another version may still be written, so the last permitted version is
delivered as the answer without a further review call. That final review is deliberately not run
because its verdict would be non-actionable — no rewrite may follow it — so the call would spend
a review's time and cost only to log problems the loop can no longer fix. An imperfect report is
delivered, the turn is never failed and the work is never discarded over a formatting verdict,
and the unreviewed delivery SHALL be announced (see the stage requirement above). A budget of one
SHALL mean the first draft is delivered with no review at all.

The review step SHALL judge the report as written. It SHALL NOT re-open evidence coverage or
request further research — that judgement belongs to research-review — and it SHALL NOT be able to
route control back to research-agent. Its prompt SHALL still list, among what it does not judge,
whether a claim is true and whether the research was thorough, and SHALL NOT list whether a source
was the right one to use: how the draft presents the values of several sources is a source-selection
check it does judge.

Once the loop has settled on the draft to deliver, that draft's wording is final: no later step may
rewrite, shorten, reorder, or reformat it. The one permitted exception is the citation step, which
replaces each citation marker it converts into an inline citation annotation with that citation's
marker tag and changes nothing else (see the **report-citations** capability). The review step judges
the draft with its markers in place, which is the form the citation rules are written against.

#### Scenario: Approved first draft is delivered as judged

- **WHEN** the review step approves the first draft
- **THEN** that draft SHALL be delivered as the answer with no revision written and no rewording,
  its only permitted difference from the judged text being the citation markers the citation step
  replaced with marker tags

#### Scenario: Rejected draft is revised and judged again

- **WHEN** the review step returns revision instructions for the first draft and the version
  budget is 3
- **THEN** a revision SHALL be written against those instructions and SHALL itself be judged by
  the review step before delivery

#### Scenario: A violation always forces a revision, with no way to leave it merely informative

- **WHEN** the review step returns one violation on a draft it would otherwise consider fine to
  ship
- **THEN** the draft SHALL still be treated as not approved and a revision SHALL be written
  against that violation, because the schema has no field to mark a violation non-actionable

#### Scenario: Exhausted budget delivers the latest draft

- **WHEN** every review demanded a rewrite and the last permitted version has been written
- **THEN** the latest draft SHALL be delivered as the answer without a further review call, the
  turn SHALL complete successfully, and the unreviewed delivery SHALL be recorded in the logs

#### Scenario: A failed review call delivers a draft that is within the ceiling

- **WHEN** the review call raises, or returns output that cannot be parsed into its verdict schema,
  after its transient-drop retries are exhausted, and the draft is within the word ceiling
- **THEN** the current draft SHALL be delivered as the answer, the turn SHALL complete
  successfully, and the failure SHALL be logged as a warning

#### Scenario: A failed review call still shortens an over-long draft

- **WHEN** the review call fails on a draft measuring 3,900 words against a ceiling of 2,750 and the
  version budget is not exhausted
- **THEN** a revision SHALL be written against the app-rendered length instruction alone, and the
  failure SHALL be logged as a warning

#### Scenario: A failed revision call delivers the previous draft

- **WHEN** a revision's model call fails — its transient-drop retries exhausted, or a non-retryable
  error such as an exceeded context length — after a first draft was already written
- **THEN** the previous draft SHALL be delivered as the answer, the turn SHALL complete successfully,
  and the failure SHALL be logged as a warning

#### Scenario: An over-long draft ships when the budget runs out

- **WHEN** the version budget is exhausted and the latest draft still measures above the ceiling
- **THEN** that draft SHALL be delivered as the answer, the turn SHALL complete successfully, and the
  unresolved length SHALL be recorded in the logs

#### Scenario: A forced revision carries an instruction even with nothing from the model

- **WHEN** the review step approves an over-long draft, so Python forces the revision
- **THEN** the report node SHALL receive the previous draft, its measured count, the ceiling, and a
  direction to shorten by rewriting, and SHALL NOT be invoked as if writing a first draft

#### Scenario: Version budget of one skips the review

- **WHEN** an instance configures a version budget of one
- **THEN** the first draft SHALL be delivered as the answer and no review call SHALL be made

#### Scenario: Review cannot reopen research

- **WHEN** the review step judges a draft whose Detailed Analysis rests on thin evidence
- **THEN** it SHALL confine its instructions to the report text and SHALL NOT cause another
  research iteration

#### Scenario: Review reports two differing values merged into a range

- **WHEN** a draft states "global GDP is forecast to grow by 3.3% to 3.5% in 2026" and cites two
  sources, each of which gives one end of the range
- **THEN** the review step SHALL report a violation asking for each value to be stated on its own,
  with its citation, its stated date and the reason for the difference, or the statement that the
  sources do not explain it
