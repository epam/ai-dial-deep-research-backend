## MODIFIED Requirements

### Requirement: Every report review is visible as a DIAL stage and summarized in the logs

Each report review of a draft SHALL emit one DIAL stage, so a user can see why a report was
revised, and one INFO log record, so the loop's behavior is measurable without reading anyone's
report. The blind review and the grounded review (see the loop requirement below) SHALL each emit
one INFO log record of their own besides, because every model call gets its own record (see
**logging-policy**, "LLM call logging").

**The stage** SHALL carry:

- the draft number being reviewed (1 for the first draft, incrementing per revision);
- the draft's measured word count and the configured ceiling, as numbers, together with what the
  count leaves out, which is the inline citations — a reader who counts the delivered report
  themselves gets a larger number, the appended References section included, and the stage SHALL
  say why;
- the violations, as a numbered markdown list — one entry per violation (stage content renders
  as markdown). The list is everything the next revision must fix: the app-checked violations, the
  app-rendered length violation among them when the measured count exceeds the ceiling, then the
  blind review's violations, then the grounded review's items.

Its title SHALL carry its own prefix rather than `[TOOL]`, the draft number, the review's outcome and
the elapsed time — the shape a result stage has, without the tool stages' start and end
timestamps, which a single call inside one node does not need. The prefix SHALL name the report
review specifically: the research review emits a stage of its own in the same title shape, and the two
are told apart by their prefixes (see **research-execution**).

A review that produced no violations SHALL still emit a stage, recording that the draft was approved.
A review whose **blind review failed** SHALL emit one too, recording the failure — alongside the
app-measured length violation when the draft is over the ceiling — the same principle as a tool
error stage: the user sees that a step ran and what came of it. A failed grounded review SHALL be
recorded in the same stage the same way, naming which of the two reviews failed, beside whatever the
other one found.

A draft delivered because the version budget ran out gets no review (see the loop requirement
below), and that delivery SHALL still emit one stage and one INFO record, so "review approved the
draft" and "the budget ran out, so the previous review's violations may remain" stay distinguishable.
Both are rendered from the state alone, with no model call. The stage SHALL carry the draft number,
the measured word count with the ceiling, and that the draft is delivered unreviewed, with the budget
stated; the log record SHALL carry the same numbers. A version budget of one makes no review
and exhausts nothing — review is off by configuration — so no stage SHALL be emitted at all. The
exception covers the stage only: the INFO record SHALL still fire, the delivery having gone
unreviewed whatever the reason, so the loop's behavior stays measurable at every configured budget.

**A revision whose own call fails SHALL be announced too.** When the report call for a revision
fails and the previous draft is delivered in its place (see **research-execution**), the app SHALL
emit one stage naming the draft that was not written, the draft delivered instead, and the kind of
failure, and stating that violations the last review recorded may remain unaddressed. Its title SHALL
carry its own prefix — this is the report step reporting, not a review — and the error mark. The
stage SHALL NOT contain any draft text: a draft the loop did not settle on stays out of the response
(see **research-execution**). No review ran, so the stage carries neither violations nor an elapsed
review time.

**The log record** SHALL carry the draft number, the review's duration, its outcome, the measured
word count, the configured ceiling, and the **number** of violations — counts and identifiers only.
**Each review's own record** SHALL carry the draft number, the call's duration, the number of
messages, the number of items it returned, the failure kind when it failed, and its token usage with
the input tokens served from the prompt cache — counts and identifiers only, under the same content
allowlist.

**The two channels carry deliberately different amounts, and this asymmetry is the requirement, not an
oversight.** Violations are LLM response text, which the **logging-policy** capability's content
allowlist forbids in a log record at any level. A DIAL stage is not a log record: it is part of the
response, shown to the user who asked for the report, and stage bodies already carry retrieved content
today. So the violation text SHALL appear in the stage and SHALL NOT appear in any log record — not
truncated, not summarized, not at DEBUG.

Showing violations does not show drafts: the rejected draft itself SHALL still stay out of the
response (see **research-execution**), and a violation SHALL NOT be padded out into a reproduction of
the draft it judges.

#### Scenario: A revision-triggering review is visible

- **WHEN** report-review returns violations on a draft measuring 3,910 words against a ceiling of
  2,750
- **THEN** a stage SHALL appear carrying draft number 1, both numbers, and the violations as a list;
  and one INFO record SHALL carry the draft number, 3910, 2750, and the violation count — with no
  violation text

#### Scenario: An approving review is visible too

- **WHEN** report-review approves a draft with no violations
- **THEN** a stage SHALL still be emitted recording the approval, and the log record SHALL carry a
  violation count of zero

#### Scenario: A failed blind review is visible as such

- **WHEN** the blind review fails and the loop absorbs it
- **THEN** its stage SHALL record the failure, marked with an error cross in both the title and
  the body, and the failure SHALL also be logged as a warning naming the failure kind

#### Scenario: Violations never reach a log record

- **WHEN** a review returns violations quoting sentences from the draft, at any configured log level
  including DEBUG
- **THEN** no log record SHALL contain any of that text; only the count of violations SHALL be logged

#### Scenario: A budget-exhausted delivery is visible as such

- **WHEN** every review demanded a rewrite and the last permitted version has been written
- **THEN** the delivered draft SHALL emit a stage recording that it is delivered without review,
  and an INFO record with the draft number, the measured count and the ceiling — with no review
  made for it

#### Scenario: No review, no stage

- **WHEN** an instance configures a version budget of one
- **THEN** no report-review stage SHALL be emitted — not the unreviewed-delivery one either —
  because no review is made and nothing is exhausted, while the report-delivered-without-review
  INFO record SHALL still fire

#### Scenario: Each review's record carries its timing and cache use

- **WHEN** report review judges draft 2 and the provider served part of the grounded review's input
  from the prompt cache
- **THEN** the blind review and the grounded review SHALL each emit one INFO record carrying draft
  number 2, the call's duration, its item count and its token usage, the grounded review's
  including the cached input tokens, and neither SHALL carry item text

#### Scenario: A failed grounded review is visible in the stage

- **WHEN** the grounded review fails and the blind review reports one violation
- **THEN** the stage SHALL list that violation and record that the grounded review failed, with the
  failure kind

#### Scenario: The two review stages are told apart by their prefixes

- **WHEN** one turn emits both a research-review stage and a report-review stage
- **THEN** each SHALL carry its own prefix, so a reader can tell which review produced which stage

#### Scenario: A failed revision is visible as such

- **WHEN** report-review asks for a revision of draft 1 and the report call writing draft 2 fails
- **THEN** a stage SHALL be emitted naming draft 2 as unwritten, draft 1 as delivered and the failure
  kind, marked with the error cross, and it SHALL contain no draft text

### Requirement: Reports carry no meta-annotations about the research process

The report SHALL NOT contain annotations about the research process or the model's own
certainty: confidence scores or ratings, certainty or reliability labels, complexity or
difficulty ratings, processing or elapsed times, iteration counts, or token usage. This covers
both explicit fields (`Confidence: High`, `Complexity: moderate`, `Processing time: 4m 12s`)
and equivalent prose or table cells.

Honest qualification of the evidence in prose remains required, not banned: stating that a
figure comes from a single source or that sources disagree is content about the findings, not a
rating of the research. A statement labelled as the report's own inference is not qualification
of the evidence: the report infers nothing (see **faithful-relay**).

Evidence the run could not obtain falls on the permitted side of that line, and important
evidence must be reported. When evidence that the answer or a plan item depends on could not be
retrieved — a tool failed for it, per the **tool-call-fault-tolerance** capability, and no other
result supplies it — the report SHALL state that it could not be retrieved and what therefore
cannot be concluded, because a reader who is not told would take the report as complete. It SHALL
NOT name the tool, give the error or its status, or say how many attempts were made: those are
facts about the run, which this requirement bans, and the reader can act on none of them.

The review step SHALL enforce this boundary as it enforces the rest of this requirement. Its
checklist is closed — it reports only the violations it is given — so a draft naming the failed
tool or counting the attempts is caught only if the list says so. The review step cannot enforce
the obligation to state missing evidence: it does not receive the findings, so it cannot tell
that evidence is missing. That obligation rests on the report writer, which sees the failed
results among its findings.

#### Scenario: A draft naming the failed tool is sent back

- **WHEN** a draft states that a tool failed, names it, or says how many attempts were made
- **THEN** the review step SHALL require its removal, as it does for any other annotation about the research process

#### Scenario: Confidence annotation forces a revision

- **WHEN** a draft ends a section with `Confidence: High (3 sources)`
- **THEN** the review step SHALL require its removal, and the delivered report SHALL NOT
  contain it

#### Scenario: Prose qualification of evidence is kept

- **WHEN** a draft states that only one publication reports a figure and that a second source
  gives a different number
- **THEN** the review step SHALL NOT treat that as a prohibited annotation and SHALL NOT
  require its removal

#### Scenario: No processing time in the report

- **WHEN** a research run takes several minutes across many iterations
- **THEN** the report SHALL state neither the elapsed time nor the number of iterations or tool
  calls it took

#### Scenario: Important evidence that could not be retrieved is stated

- **WHEN** a tool the run needed failed and the evidence it would have produced is absent from the
  findings
- **THEN** the report SHALL state, when the answer or a plan item depends on that evidence, that
  it could not be retrieved and what cannot be concluded from its absence, and SHALL NOT state which
  tool failed, how it failed, or how many attempts were made

### Requirement: A review ↔ revise loop enforces the report rules before delivery

A finished draft SHALL be judged by an independent review step before it is delivered. That step's
first call, the **blind review**, SHALL read the draft, the configured report structure, the
protected sections, and the research question and plan — the last two because they are where a
user's formatting instruction lives, and without them the step cannot tell a legitimately-followed
instruction from an override of a protected rule. It SHALL judge the draft against the section
content rules, the protected sections and their rules, the prohibited meta-annotations, well-formed
Markdown, the citation format rules the **research-execution** capability defines, and the
report-review part of every quality rule: the generic source-selection and faithful-relay rules and
the channel's client rules (see **source-selection** and **faithful-relay**). These parts judge only
what the draft shows — how two values for one fact are presented, whether a value states its dates,
whether a near match says how it differs, whether a claim carries a citation — because the blind
review never sees the sources.

The review step SHALL make a second call beside it, the **grounded review**, which sees the
research transcript and judges the draft against the faithful-relay rules' writer parts and the
writer's "No calculations" rule (see **faithful-relay**). The two calls SHALL run concurrently, and
the grounded review's items SHALL be appended to the blind review's violations, so the loop below
treats every item alike.

The section structure, the word ceiling and the absence of hyperlinks are not the review step's to
judge — the app checks those itself (see the
requirement above). The citation-format check becomes load-bearing with this change: the app parses
those markers out of the delivered report (see **report-citations**), so a draft that adopted
numbered footnotes would yield no pills at all, and this step is what pushes it back to the defined
form. It SHALL NOT be given the measured word
count or the ceiling: length needs no model — the app measures it and adds the length violation
itself (see the ceiling requirement).

The blind review's structured output SHALL be the violations alone, one entry per rule the draft
breaks and naming what to change; the grounded review answers with a numbered list of the same
kind. There SHALL be no separate approval field: an empty list SHALL
mean the draft is approved, so a remark that is not meant to block delivery cannot be expressed —
every returned violation forces a revision.

The blind review SHALL NOT receive the research findings: every criterion it judges is decidable
from the draft, the configuration, and the query and plan. Only the grounded review receives them.

**A failing review SHALL NOT cost the report.** If the blind review fails — an unparseable
structured response, a provider error, exhausted transient-drop retries — the turn SHALL NOT fail
and the failure SHALL be logged as a warning. The same holds for the grounded review: a failed
grounded review adds no item, and the blind review's violations still stand, as the grounded
review's items still stand when the blind review fails. This departs deliberately from
research-review, which is fail-loud because a broken verdict there means research of unknown
completeness; here the report already exists, and discarding a finished multi-minute run over a
formatting check is the worse outcome.

When both calls fail, the app has no verdict, so the two rules compose in one order, which SHALL
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
delivered as the answer without a further review. That final review is deliberately not run
because its verdict would be non-actionable — no rewrite may follow it — so the review would spend
a review's time and cost only to log problems the loop can no longer fix. An imperfect report is
delivered, the turn is never failed and the work is never discarded over a formatting verdict,
and the unreviewed delivery SHALL be announced (see the stage requirement above). A budget of one
SHALL mean the first draft is delivered with no review at all.

The review step SHALL judge the report as written. It SHALL NOT re-open evidence coverage or
request further research — that judgement belongs to research-review — and it SHALL NOT be able to
route control back to research-agent. The blind review's prompt SHALL still list, among what it does
not judge, whether a claim is true and whether the research was thorough, and SHALL NOT list whether
a source was the right one to use: how the draft presents the values of several sources is a
source-selection check it does judge. The grounded review's instructions SHALL list whether
the research was thorough among what it does not judge, and SHALL NOT list whether a claim is true
to its source, which is what it judges.

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
- **THEN** the latest draft SHALL be delivered as the answer without a further review, the
  turn SHALL complete successfully, and the unreviewed delivery SHALL be recorded in the logs

#### Scenario: A failed blind review delivers a draft that is within the ceiling

- **WHEN** the blind review raises, or returns output that cannot be parsed into its verdict schema,
  after its transient-drop retries are exhausted, the draft is within the word ceiling, and the
  grounded review reports no item or fails too
- **THEN** the current draft SHALL be delivered as the answer, the turn SHALL complete
  successfully, and the failure SHALL be logged as a warning

#### Scenario: A failed blind review still shortens an over-long draft

- **WHEN** the blind review fails on a draft measuring 3,900 words against a ceiling of 2,750 and
  the version budget is not exhausted
- **THEN** a revision SHALL be written against the app-rendered length instruction, together with
  any item the grounded review reports, and the failure SHALL be logged as a warning

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
- **THEN** the first draft SHALL be delivered as the answer and no review SHALL be made

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

#### Scenario: A failed blind review leaves the grounded review's items standing

- **WHEN** the blind review fails and the grounded review reports two violations
- **THEN** the draft SHALL be revised against those two violations, and the blind review's failure
  SHALL be logged as a warning

#### Scenario: The grounded review's item forces a revision the blind review would not

- **WHEN** the blind review approves a draft and the grounded review reports that a figure is
  not on the page cited for it
- **THEN** the draft SHALL be revised against that item

### Requirement: A report uses the glossary's terminology

On a channel that configures a glossary (see **data-sources-discovery**), the report SHALL use the
glossary's terminology: where the report refers to a concept that a glossary term names, it SHALL
use that term, spelled as the glossary spells it, rather than a synonym or a paraphrase. A glossary
term that the report has no reason to mention is not required.

**A glossary term may be written in any of the forms the glossary gives it.** A term that lists
several names separated by a slash, such as "Workforce/Labour force", MAY be written as any one of
those names, and the whole slash form SHALL NOT be required. A term that gives a full form with its
abbreviation in parentheses, such as "Harmonised Index of Consumer Prices (HICP)", MAY be written in
either form; where the report uses the abbreviation, its first use SHALL be written as the full form
followed by the abbreviation in parentheses. In mid-sentence, a glossary term's first letter MAY
be written in lower case. A `[glossary <term>]` citation still writes the whole term, as the
glossary spells it. Both calls receive this in the rule's shared wording.

**The glossary is the only source of glossary terms and definitions.** A phrase counts as a
glossary term only when it is a term of the glossary: a `term` in the data-sources string's
`Glossary terms:` list, or a term in the research agent's glossary tool results. A phrase found
anywhere else, such as a dataset description or structure, a document, a data-query result or
the knowledge-base descriptions, is not a glossary term, however much it reads like one. The rule
governs only the concepts the glossary names: a term the glossary does not list, such as "trade
balance" taken from a document or a dataset description, may be used freely, unless it names a
concept that a glossary term names, in which case the glossary term applies. The writer SHALL NOT
present such a phrase as a glossary term or cite it with `[glossary <term>]`, and the reviewer
SHALL NOT ask for it as a glossary term. The same holds for definitions: a definition cited as a
glossary definition comes from the glossary. Both calls receive this in the rule's shared wording.

The rule SHALL be given to two calls, in the same wording of what it requires:

- **The report writer**, on every turn of such a channel. Its system prompt SHALL carry the rule
  next to the other report-wide rules. The glossary reaches the writer in two ways: the app's fetch
  through its data-sources string, and whatever terms and definitions the research agent obtained
  with its own tool calls through the transcript (see **research-execution**). The writer's rule
  SHALL say that the glossary in the data-sources string may lack terms or definitions, because the
  app's fetch may have failed in part or in whole, and that the terms and definitions in the
  research's tool results count as glossary terms too.
- **The report reviewer**, on a turn whose glossary fetch listed at least one term, or whose
  research agent obtained at least one successful result from a configured glossary tool. Its
  system prompt SHALL carry the check as one of the review model's own checks. The glossary reaches
  the reviewer in two ways: the app's fetch through its data-sources string, and the research
  agent's successful glossary tool results, which the app selects from the transcript by the
  configured tool names (see **research-execution**). A draft that names a glossary concept by
  another word SHALL be reported as a violation naming the passage and the glossary term to use.

**Both calls know the glossary citation form.** The writer's instructions state the form
`[glossary <term>]` and when to use it (see **research-execution**). The reviewer's instructions
state the same form, so the review model treats a glossary marker as a well-formed citation and
reports a malformed one, such as a different keyword or a term written in parentheses, under the
citation-format check. The readable form the delivery produces never reaches the reviewer. Both hear of the form only on a channel that configures a glossary.

This is a check for the review model, not for Python: whether a phrase in the draft refers to the
concept a glossary term names needs a reader, so no app-owned rule decides it.

A term whose definition is `null` SHALL still count for the rule, judged by its name.

On a channel without a glossary, neither call SHALL carry the rule. On a turn whose list-terms call
failed, the writer SHALL carry the rule, and the reviewer SHALL carry the check only when the
research agent obtained a successful glossary tool result, because otherwise the reviewer has no
terms to judge against. Both still receive the data-sources string, which on a
failed list ends in the failure text.

#### Scenario: The writer is told to use the glossary's terms

- **WHEN** the report writer runs on a turn whose glossary listed terms
- **THEN** its system prompt SHALL carry the glossary-terminology rule, and its data-sources string
  SHALL carry the glossary

#### Scenario: The reviewer reports a synonym

- **WHEN** the glossary lists `Primary Commodity Prices`, and a draft refers to the same concept as
  "raw material price levels"
- **THEN** the review model SHALL report a violation that names the passage and the glossary term

#### Scenario: A term found only outside the glossary is not demanded

- **WHEN** the `Datasets:` part describes `IMF:WEO` as covering the "unemployment rate", no glossary
  term is "unemployment rate", and a draft writes "the share of the labour force without a job"
- **THEN** the review model SHALL NOT report a glossary-terminology violation for that passage

#### Scenario: A term the glossary does not list may be used

- **WHEN** a document page the research read uses the term "trade balance", and no glossary term
  names that concept
- **THEN** the report writer MAY use "trade balance", and the review model SHALL NOT report its use
  as a violation

#### Scenario: The reviewer accepts a glossary citation and reports a malformed one

- **WHEN** a draft on a glossary channel cites `[glossary World Economic Outlook]` in one place and
  `(World Economic Outlook - glossary term)` in another
- **THEN** the review model SHALL NOT report the first, and SHALL report the second as a citation
  that does not follow the glossary form

#### Scenario: A failed list still gives the writer the rule

- **WHEN** the list-terms call failed three times, and the research agent obtained the terms with
  its own list-terms call
- **THEN** the report writer's prompt SHALL carry the glossary-terminology rule, saying that the
  data-sources glossary may lack terms and that the terms in the research's tool results count,
  and the report reviewer's prompt SHALL carry the check and the research agent's list-terms
  result

#### Scenario: A failed list and no agent result give the reviewer no check

- **WHEN** the list-terms call failed three times, and the research agent obtained no successful
  result from either glossary tool
- **THEN** the report reviewer's prompt SHALL NOT carry the glossary-terminology check

#### Scenario: One name of a slash term is enough

- **WHEN** the glossary lists `Workforce/Labour force`, and a draft uses only the name "labour
  force", in mid-sentence
- **THEN** the review model SHALL NOT report a glossary-terminology violation for it

#### Scenario: A glossary abbreviation is spelled out at its first use

- **WHEN** the glossary lists `Harmonised Index of Consumer Prices (HICP)`, and a draft writes
  "HICP" at its first mention and at every later one
- **THEN** the review model SHALL report a violation for the first mention, which SHALL give the
  full form "Harmonised Index of Consumer Prices (HICP)", and SHALL NOT report the later mentions

### Requirement: The data sources in the system prompt count as retrieved sources

The report writer's system prompt SHALL state that the report may draw on two kinds of source: the
research findings in the transcript, and the data-sources string in its `<data_sources>` block,
which holds the channel's hand-written descriptions and what the app fetched from the dataset
server — the list of datasets, their structures and the glossary. A fact taken from the
data-sources string SHALL count as grounded in a retrieved source, and SHALL be cited with the
citation form of the source it describes, such as `[dataset <urn>]` for a dataset's name,
description, coverage or last-update date.

A fact taken from a glossary definition SHALL be cited `[glossary <term>]` (see
**research-execution**). A fact from the hand-written description of a publication series SHALL NOT
be cited at all, and SHALL NOT be given an invented citation such as a `[doc <id>, page <ix>]`: only
a publication itself is cited, by its document and page. Such a fact names the publication series
as its source in words, which the faithful-relay rule "Only the sources" allows (see
**faithful-relay**).

The report reviewer SHALL judge such a fact the same way: citing a dataset for a fact the datasets
section states about it SHALL NOT be reported as a violation.

The statement SHALL NOT tell the writer to cite datasets the research did not query, nor forbid
it. A report may cite such a dataset when it uses it, and an instruction either way would bias the
writer.

#### Scenario: A dataset's metadata is cited from the datasets section

- **WHEN** a draft states the last-update date of a dataset that no tool call of the turn queried,
  taken from the datasets section, and cites it as `[dataset <urn>]`
- **THEN** the report writer's instructions SHALL allow it, and the report reviewer SHALL NOT report
  it as a fact without a retrieved source

#### Scenario: A fact from a series description names the series

- **WHEN** a draft states a fact that only the description of a publication series gives
- **THEN** the sentence SHALL name the series as its source in words and carry no citation, and
  report review SHALL NOT report it as an uncited claim

### Requirement: Reports contain no calculations

The report SHALL give every figure as a source states it, and SHALL compute nothing. A calculation
is arithmetic or modelling that produces a number no source gives: a growth rate derived from two
levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as large", a
share, a sum, an average, an elasticity or a regression estimate. Three things are not
calculations and stay allowed: a comparison that produces no new number, such as which value is
larger, a rank, or the direction of a change; writing a value in another notation, such as a
fraction as a percentage; and rounding a value given with more digits than a reader can use, such
as 0.0473918265 written as 4.74%. The writer and report review SHALL be given this definition in
one wording, so the two cannot drift apart.

- **Report writer.** Its prompt SHALL carry this rule as a section of its own. Flagging a computed
  number as the report's own inference SHALL NOT make it allowed. Where the question or the plan
  asks for a figure that no source states and only a calculation would give, the report SHALL
  present the figures it would be computed from, each with its citation, and SHALL say that the
  sources do not give the computed figure.
- **Precedence.** This rule SHALL have the highest priority of all the rules: neither the research
  question, the plan, a section's description nor a client-specific rule SHALL override it, and both
  the writer and report review SHALL be told so in those words. The writer's list of rules that
  outrank the research question and the plan SHALL include this rule. Saying that the sources do not
  give a figure is a statement about the evidence, and SHALL NOT be read as the commentary on a
  declined instruction that **Protected sections and their rules survive any user instruction**
  forbids.
- **Report review.** The blind review's prompt SHALL carry a "No calculations" check among its
  numbered checks: a
  number the draft presents as computed from other figures is a violation, even when the draft flags
  it as its own inference or a section's description or a client-specific rule asked for it. The
  three allowed things above are not violations. A number that carries its own citation, and that
  the draft does not present as computed, is not report review's to judge, because report review
  cannot see the sources. A figure computed from values of different facts, which the
  source-selection check on disagreements leaves out, falls within this check, and that
  source-selection part SHALL say so. The grounded review SHALL receive the writer's section in the
  same wording, so it also finds a computed number the draft presents as stated (see
  **faithful-relay**, "Rule 3 — the grounded review judges the "No calculations" rule").

#### Scenario: The question asks for an elasticity no source states

- **WHEN** the question asks for the elasticity of import growth to GDP growth, and the findings
  hold both growth series but no source that states the elasticity
- **THEN** the report SHALL present both series with their citations, SHALL say that the sources do
  not give the elasticity, and SHALL NOT give an elasticity or a regression estimate of its own

#### Scenario: A gap in percentage points between two cited values

- **WHEN** a draft states that one cited growth rate is 1.2 percentage points above another cited
  growth rate, and no source gives that gap
- **THEN** report review SHALL report a "No calculations" violation

#### Scenario: A comparison is not a calculation

- **WHEN** a draft states that one cited growth rate is higher than another, without giving a new
  number
- **THEN** report review SHALL NOT report a "No calculations" violation

#### Scenario: Rounding is not a calculation

- **WHEN** a data query returned 0.0473918265 and the draft gives it as 4.74% with the query's
  citation
- **THEN** report review SHALL NOT report a "No calculations" violation

#### Scenario: A client rule asks for a computed figure

- **WHEN** a channel's client rule asks the writer to give the year-on-year change of each series,
  and no source states those changes
- **THEN** the report SHALL give the cited values for each year, SHALL NOT compute the changes, and
  report review SHALL report a "No calculations" violation for a draft that computed them

#### Scenario: A computed figure flagged as inference

- **WHEN** a draft gives the average of three cited yearly values and labels it as its own
  estimate
- **THEN** report review SHALL report a "No calculations" violation
