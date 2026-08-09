## Purpose

Defines what a delivered research report looks like — the report structure it follows, the
word ceiling it respects, and the meta-annotations it must never carry — and the review ↔
revise loop that enforces those rules on a finished draft before it reaches the user.

## ADDED Requirements

### Requirement: Reports follow the configured report structure

The report SHALL be organized into the sections configured for the application instance
(`default_report_structure`, see the **application-config-schema** capability), in the
configured order, each rendered as a Markdown heading carrying the configured section name.

**Heading levels are fixed.** Every configured section SHALL be a `##` heading carrying exactly
its configured name — never `#`, never `###`, and never bold text standing in for a heading. A
report SHALL carry no `#` heading at all, and sub-headings within a section SHALL be `###` or
deeper. Both the report writer and the review step SHALL be given this rule, and the review step
SHALL report a violation for a section written at any other level. The level is not decoration:
the app finds the references section by its heading when measuring length, DIAL chat renders the
report from its heading structure, and a report whose sections sit at differing levels reads as
several documents.

A section's configured **description is the single home for that section's rules**. Everything
about what the section contains — its purpose, what to put in it, how to render it, any table
columns it carries — SHALL live in that description and SHALL be passed verbatim to both the
report writer and the review step. No prompt, model, or spec SHALL carry per-section content
instructions of its own, so there is exactly one place to change a section's behavior and exactly
one place a reader has to look.

Report-wide rules are not section rules and stay out of the descriptions: the word ceiling, the
prohibited meta-annotations, and the inline citation format (which applies to every section's
body, not to one section) are defined by this capability and by **research-execution**. The inline
citation format in particular SHALL remain non-configurable — DIAL chat will render citations
from it, so it is an interface every instance shares, not a per-deployment preference.

The references section's description SHALL carry the entry format for **every** source type a
report may cite — publications and datasets alike — so that one description is the whole answer
to how sources are listed.

The default structure, used by an instance that configures none, SHALL be **Overview → Key
Findings → Detailed Analysis → Conclusion → References**, with Overview and References protected
and the References description carrying the source-table rules.

The report SHALL open with the Overview, which answers "what was done, and what is the answer"
before the findings arrive: the research question restated, the sources and topics the research
covered and the approach taken to cover them, and the direct answer in a few sentences. It is a
section like any other — the report-wide inline citation rule applies to it, and its own rules
live in its description.

Every configured section SHALL be present in the report. A section SHALL NOT be filled with
text the findings do not support in order to make it appear; a section the findings leave
nothing to say about SHALL say that plainly instead of being dropped.

Where the configured structure includes a references section — as the default does — a report that
cites no source at all SHALL say so in that section rather than omit it, since that outcome is a
failure of the research to find citable evidence and hiding it as a missing section would
misrepresent the report as unsourced by choice. Where a deployment has configured a structure with
no references section, no such section SHALL be synthesized: inline citations still appear in the
body (their format being report-wide and non-configurable), and nothing decodes them. That is a
deliberate consequence of the configuration, and the requirements above bind only what the
configured structure declares.

#### Scenario: Default structure applies when nothing is configured

- **WHEN** a research turn runs on an instance that does not configure a report structure
- **THEN** the report SHALL carry the sections Overview, Key Findings, Detailed Analysis,
  Conclusion, and References, as Markdown headings, in that order

#### Scenario: Configured structure replaces the default

- **WHEN** an instance configures a structure of `Summary`, `Evidence`, `Outlook`, with `Evidence`
  marked protected (some section must be, so the structure validates — and protection is not tied to
  references)
- **THEN** the report SHALL carry exactly those three section headings in that order, no Key
  Findings or Detailed Analysis heading SHALL appear, and each section's content SHALL follow
  its configured description

#### Scenario: A section's rules come only from its description

- **WHEN** a deployment changes what belongs in a configured section
- **THEN** editing that section's `description` SHALL be sufficient, and no prompt text outside
  the configured structure SHALL have to change with it

#### Scenario: A report with nothing to cite still carries the section

- **WHEN** research ends without a single citable source
- **THEN** the references section SHALL still be present and SHALL state that no source was
  found, rather than being omitted or filled with invented entries

#### Scenario: A section written at the wrong heading level is a violation

- **WHEN** a draft writes a configured section as `# Conclusion` or as bold text instead of a
  `##` heading
- **THEN** the review step SHALL report it as a violation and a revision SHALL be required while
  the version budget allows

#### Scenario: A section the findings do not support is not padded

- **WHEN** the findings leave a configured section with nothing substantive to say
- **THEN** that section SHALL say so plainly and SHALL NOT be filled with text the findings do
  not support

### Requirement: Protected sections and their rules survive any user instruction

Some sections carry the report's integrity rather than its shape, and SHALL be **protected**:
neither removable nor alterable by anything the user asked for. Protection covers two things —
the section's **presence** in the report, and the **rules in its description** that generate its
content.

A section is protected iff its configuration marks it so (`ReportSection.protected`, see the
**application-config-schema** capability), and at least one section SHALL always be protected —
configuration cannot yield a report whose every section a user may remove. The shipped default
protects Overview and References. A deployment MAY protect further sections of its own, and
protection then means the same thing for them.

The inline citation format is protected report-wide rather than per section, because it applies
to every section's body: no user instruction SHALL change it, and it is not configurable at all.

The user's wording reaches the report writer already: the research question and the plan steps
are part of its prompt, and either may carry an instruction about structure or formatting. The
app SHALL therefore state the protection explicitly to **both** the report writer and the review
step, alongside the configured sections and the query and plan those instructions may hide in,
naming which sections may not be dropped or restyled.

**Protection SHALL be stated as a rule of its own and SHALL NOT be rendered as a marker on a
section's name.** The report writer is told to use the configured names as the report's headings,
so anything attached to a name can be copied into the delivered report. Protection is a fact about
the app's rules rather than part of what the report says, and it SHALL appear in no text a user
sees.

Precedence SHALL be: a user instruction applies to everything except the protected sections, their
rules, and the report-wide rules of this capability — the word ceiling, the prohibited
meta-annotations, and the inline citation format. None of those SHALL yield to an instruction; an
instruction to ignore the length limit, to add confidence ratings, or to restyle citations SHALL
be refused exactly as an instruction to drop a protected section is. Where an instruction conflicts
with any of them, the rule wins and the rest of the instruction is still honoured as far as it can
be. A report SHALL NOT carry
commentary explaining that an instruction was declined — the report contains the report.

Nothing in this requirement obliges the writer to *follow* a user's format request: routing a
requested format to the report is deliberately not part of this change (issue #45). This
requirement bounds what such a request can ever do, whenever it arrives.

#### Scenario: An instruction to drop the references is refused

- **WHEN** the research question or a plan step asks for a report with no references or sources
  section
- **THEN** the delivered report SHALL still carry its references section with the source tables,
  and the review step SHALL require a revision of any draft that dropped it

#### Scenario: An instruction to restyle citations is refused

- **WHEN** a user instruction asks for citations as numbered footnotes instead of the defined
  `[doc <id>, page <ix>]` form
- **THEN** the delivered report SHALL keep the defined citation format, and the review step SHALL
  treat a draft that adopted the requested format as needing a revision

#### Scenario: A protected section survives a conflicting instruction

- **WHEN** a user asks for an answer in two sentences, which cannot coexist with the configured
  sections and a full references section
- **THEN** the references section SHALL still be present however brief the rest becomes, and the
  report SHALL NOT explain the conflict to the user. Whether the body itself gets shorter is not
  guaranteed by this change — following a requested format is issue #45's — but nothing about the
  brevity request may remove a protected section.

#### Scenario: A reader never learns which sections are protected

- **WHEN** a report is delivered from a structure whose References section is protected
- **THEN** neither the section's heading nor any other text in the response SHALL mark it as
  protected, and the protection SHALL be visible only in the rules the app gives its own models

#### Scenario: A harmless format instruction is not treated as an override

- **WHEN** a user asks for the analysis as a comparison table, touching no protected section
- **THEN** the review step SHALL NOT flag that as an override attempt on protected-section
  grounds

#### Scenario: An instruction to lift the length ceiling is refused

- **WHEN** a user instruction asks for an exhaustive report with no length limit
- **THEN** the ceiling SHALL still apply, and the review step SHALL require a revision of a draft
  that exceeded it on the instruction's authority

### Requirement: Every report review is visible as a DIAL stage and summarized in the logs

Each report-review call SHALL emit one DIAL stage, so a user can see why a report was revised, and
one INFO log record, so the loop's behavior is measurable without reading anyone's report.

**The stage** SHALL carry:

- the draft number being reviewed (1 for the first draft, incrementing per revision);
- the draft's measured word count and the configured ceiling, as numbers, together with what the
  count leaves out, named from the configured structure — a reader who counts the delivered report
  themselves gets a larger number, and the stage SHALL say why;
- the violations, as a numbered markdown list — one entry per violation (stage content renders
  as markdown). The list is everything the next revision must fix: the review model's violations,
  with the app-rendered length violation prepended when the measured count exceeds the ceiling.

Its title SHALL follow the normalized shape the tool stages use, with its own prefix rather than
`[TOOL]`, and SHALL carry the review's outcome and the elapsed time. The stage exists for the report
review only; research review SHALL NOT emit one (out of scope here, and it MAY be added later).

A review that produced no violations SHALL still emit a stage, recording that the draft was approved.
A review whose **call failed** SHALL emit one too, recording the failure — alongside the app-measured
length violation when the draft is over the ceiling — the same principle as a tool error stage: the
user sees that a step ran and what came of it.

A draft delivered because the version budget ran out gets no review call (see the loop requirement
below), and that delivery SHALL still emit one stage and one INFO record, so "review approved the
draft" and "the budget ran out, so the previous review's violations may remain" stay distinguishable.
Both are rendered from the state alone, with no model call. The stage SHALL carry the draft number,
the measured word count with the ceiling, and that the draft is delivered unreviewed, with the budget
stated; the log record SHALL carry the same numbers. A version budget of one makes no review call
and exhausts nothing — review is off by configuration — so no stage SHALL be emitted at all.

**The log record** SHALL carry the draft number, the measured word count, the configured ceiling, and
the **number** of violations — counts and identifiers only.

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

#### Scenario: A failed review call is visible as such

- **WHEN** the report-review call fails and the loop absorbs it
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
  call made for it

#### Scenario: No review, no stage

- **WHEN** an instance configures a version budget of one
- **THEN** no report-review stage SHALL be emitted — not the unreviewed-delivery one either —
  because no review call is made and nothing is exhausted

### Requirement: Reports respect a configured word ceiling without abrupt truncation

The report SHALL respect a configured word ceiling (`max_report_words`, default 2750, see the
**application-config-schema** capability). A report's length SHALL be measured as the number of
whitespace-separated tokens in its Markdown text **after removing the inline citations and the
references section**, and that one definition SHALL be used everywhere a length is stated — in
prompts, in the review stage and in logs alike.

The ceiling bounds what the writer chooses to say. Neither removed part is that: a citation's
length follows from the source it names, and the references section is as long as the research
cited, so counting either would let a well-sourced report be revised for its sourcing.

**The exemption follows the configuration, never the position alone.** The references section is
the one the structure marks `references_section: true`, which only its last section may be, and a
structure MAY declare none — a report whose closing section is prose has nothing exempt but its
citations. The report writer SHALL be told what the count leaves out, rendered from the structure
it was given, so a writer is never promised room the count does not give.

Removing it SHALL require all of: the structure declares a references section; the draft carries a
`##` heading — the level every section must use — whose text is that section's configured name.
Everything from that heading to the end of the draft is then the section. A draft that renamed the
section, omitted it, or wrote its heading at another level SHALL lose nothing from the count: each
of those is a structure violation the review step reports, and a violation SHALL NOT also earn
length budget.

Length is never a model's judgement: it is measured in Python and enforced deterministically (see
below). Where a model does need a length, it is supplied as a number rather than left for it to
count: the writer SHALL be told the ceiling, and a revision SHALL be told the draft's measured
count alongside the ceiling. The review step SHALL be told neither — it judges the content rules
only.

The ceiling SHALL NOT be enforced by truncation:

- No token cap SHALL be placed on the report model call. Measured behavior, not caution: a capped
  call returns `finish_reason="length"` and stops mid-sentence rather than wrapping up (see
  design.md).
- A revision that shortens an over-long draft SHALL rewrite it to fit — condensing sections,
  cutting detail — and SHALL NOT cut a sentence, a list, a table, or a section short.
- The delivered report SHALL end at a clean boundary: a complete sentence closing a complete
  section.

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

#### Scenario: Citations and the references section do not consume the budget

- **WHEN** a draft's Markdown holds 3,000 whitespace-separated tokens, of which 200 are inline
  citations and 400 are its `## References` section, marked `references_section: true` in the
  configured structure, against a ceiling of 2,750
- **THEN** its measured length SHALL be 2,400 and no revision SHALL be forced on length grounds

#### Scenario: A structure with no references section exempts only the citations

- **WHEN** an instance configures a structure whose closing section is prose and whose every
  section leaves `references_section` unset
- **THEN** that closing section's words SHALL count toward the ceiling like any other, and the
  report writer SHALL be told that only the inline citations are left out

#### Scenario: A renamed or mis-levelled references section is measured with the rest

- **WHEN** a draft heads its sources section `Bibliography`, or writes `# References` instead of
  `## References`, while the configured references section is named `References`
- **THEN** that section's words SHALL count toward the ceiling like any other, and the heading
  SHALL be judged by the review step as a section-structure violation

### Requirement: Reports carry no meta-annotations about the research process

The report SHALL NOT contain annotations about the research process or the model's own
certainty: confidence scores or ratings, certainty or reliability labels, complexity or
difficulty ratings, processing or elapsed times, iteration counts, or token usage. This covers
both explicit fields (`Confidence: High`, `Complexity: moderate`, `Processing time: 4m 12s`)
and equivalent prose or table cells.

Honest qualification of the evidence in prose remains required, not banned: stating that a
figure comes from a single source, that sources disagree, or that a statement is the report's
own inference is content about the findings, not a rating of the research.

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

### Requirement: A review ↔ revise loop enforces the report rules before delivery

A finished draft SHALL be judged by an independent review step before it is delivered. That
step SHALL read the draft, the configured report structure, the protected sections, and the
research question and plan — the last two because they are where a user's formatting instruction
lives, and without them the step cannot tell a legitimately-followed instruction from an
override of a protected rule. It SHALL judge the draft against the configured structure, the
protected sections and their rules, the prohibited meta-annotations, and the citation format
rules the **research-execution** capability defines. It SHALL NOT be given the measured word
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
route control back to research-agent.

#### Scenario: Approved first draft is delivered unchanged

- **WHEN** the review step approves the first draft
- **THEN** that draft SHALL be delivered verbatim as the answer, and no revision SHALL be
  written

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
