## MODIFIED Requirements

### Requirement: Reports follow the configured report structure

The report SHALL be organized into the sections configured for the application instance
(`default_report_structure`, see the **application-config-schema** capability), in the
configured order, each rendered as a Markdown heading carrying the configured section name.

**The references section is the one section the writer does not write.** The application builds it
after the report loop settles and appends it to every report (see **report-citations**, which owns
what it contains), and no configured section is ever that section. So nothing has to be subtracted
from the structure the writer is given, from the structure the review step is given, or from the
list of headings the app's own structure check expects: all three are the configured structure
itself. Everything below about sections applies to the sections the writer writes; a delivered
report still carries the references section, and still
carries it last.

**Heading levels are fixed.** Every configured section SHALL be a `##` heading carrying exactly
its configured name — never `#`, never `###`, and never bold text standing in for a heading. A
report SHALL carry no `##` heading that is not a configured section, and sub-headings within a
section SHALL be `###` or deeper. The report writer SHALL be given this rule, and the app SHALL
check it itself over the finished draft (see the app-checked-rules requirement below). The level
is not decoration: DIAL chat renders the report from its heading structure, and a report whose
sections sit at differing levels reads as several documents. The app's own References section is
written to the same levels — its heading at `##`, its per-server tables at `###`.

A section's configured **description is the single home for that section's rules**. Everything
about what the section contains — its purpose, what to put in it, how to render it, any table
columns it carries — SHALL live in that description and SHALL be passed verbatim to both the
report writer and the review step. No prompt, model, or spec SHALL carry per-section content
instructions of its own, so there is exactly one place to change a section's behavior and exactly
one place a reader has to look. A references section is the exception that proves it: nothing about
its content is instructions to anyone, so its description carries the text the section itself
shows when the report cited no source (see **application-config-schema**).

Report-wide rules are not section rules and stay out of the descriptions: the word ceiling, the
prohibited meta-annotations, and the inline citation format (which applies to every section's
body, not to one section) are defined by this capability and by **research-execution**. The inline
citation format in particular SHALL remain non-configurable — DIAL chat will render citations
from it, so it is an interface every instance shares, not a per-deployment preference.

The default structure, used by an instance that configures none, SHALL be **Overview → Key
Findings → Detailed Analysis → Conclusion**, with Overview protected. The References section is not
part of any configured structure: the application appends it to every report after the loop settles
(**report-citations**).

The report SHALL open with the Overview, which answers "what was done, and what is the answer"
before the findings arrive: the research question restated, the sources and topics the research
covered and the approach taken to cover them, and the direct answer in a few sentences. It is a
section like any other — the report-wide inline citation rule applies to it, and its own rules
live in its description.

Every configured section the writer writes SHALL be present in the report. A section SHALL NOT be
filled with text the findings do not support in order to make it appear; a section the findings
leave nothing to say about SHALL say that plainly instead of being dropped.

A report that cites no source at all SHALL still carry the References section, saying so, rather
than omitting it: that outcome is a failure of the research to find citable evidence, and hiding it
as a missing section would misrepresent the report as unsourced by choice. The application writes
that statement, from `references_section_empty_text`. No configuration SHALL be able to switch the
section off, and no section of a configured structure SHALL be a references section.

#### Scenario: Default structure applies when nothing is configured

- **WHEN** a research turn runs on an instance that does not configure a report structure
- **THEN** the delivered report SHALL carry the sections Overview, Key Findings, Detailed Analysis
  and Conclusion as Markdown headings in that order, written by the report writer, followed by the
  References section the app appends

#### Scenario: Configured structure replaces the default

- **WHEN** an instance configures a structure of `Summary`, `Evidence`, `Outlook`, with `Evidence`
  marked protected (some section must be, so the structure validates)
- **THEN** the report SHALL carry exactly those three section headings in that order followed by the
  appended References section, no Key Findings or Detailed Analysis heading SHALL appear, and each
  written section's content SHALL follow its configured description

#### Scenario: A section's rules come only from its description

- **WHEN** a deployment changes what belongs in a configured section
- **THEN** editing that section's `description` SHALL be sufficient, and no prompt text outside
  the configured structure SHALL have to change with it

#### Scenario: Neither prompt offers a references section to write

- **WHEN** the report writer's prompt and the review step's prompt are rendered from the configured
  structure
- **THEN** the rendered structure SHALL be exactly that structure, with no section subtracted from
  it, and both prompts SHALL state that the application appends the References section itself and
  that neither the writer nor the reviewer may write or ask for one

#### Scenario: A report with nothing to cite still carries the section

- **WHEN** research ends without a single citable source
- **THEN** the delivered report SHALL still carry the references section, carrying the configured
  text that states no source was cited, rather than being omitted or filled with invented entries

#### Scenario: A references heading the writer wrote is a violation

- **WHEN** a draft writes `## References` while no configured section carries that name
- **THEN** the app's own structure check SHALL report it as a `##` heading that is not one of the
  configured sections, and a revision SHALL be required while the version budget allows

#### Scenario: A section written at the wrong heading level is a violation

- **WHEN** a draft writes a configured section as `# Conclusion`, or as `## **Conclusion**`
- **THEN** the app's own structure check SHALL report it, naming the heading the section must
  carry, and a revision SHALL be required while the version budget allows

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
protects Overview. A deployment MAY protect further sections of its own, and
protection then means the same thing for them.

**The References section is beyond an instruction's reach without being a protected section.** It
is no part of any configured structure: the application appends it to every report it delivers
(**report-citations**), so an instruction to leave the sources out has nothing to act on. The writer
SHALL be told not to write such a section and not to list its sources anywhere else, and the review
step SHALL be told never to instruct a revision to write one, whatever the research question or the
approved plan asked for. Neither is asked to *check* for one: the heading check is the app's, in
Python, as this capability's own requirement states.

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
meta-annotations, the inline citation format, and the appended References section. None of those SHALL yield to an instruction; an
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
- **THEN** the delivered report SHALL still carry the appended References section with its source
  tables, and the review step SHALL NOT act on the request — there is no draft section to drop, the
  application writing the section after the loop settles

#### Scenario: An instruction to restyle citations is refused

- **WHEN** a user instruction asks for citations as numbered footnotes instead of the defined
  `[doc <id>, page <ix>]` form
- **THEN** the delivered report SHALL keep the defined citation format, and the review step SHALL
  treat a draft that adopted the requested format as needing a revision

#### Scenario: A protected section survives a conflicting instruction

- **WHEN** a user asks for an answer in two sentences, which cannot coexist with the configured
  sections and a full References section
- **THEN** the References section SHALL still be present however brief the rest becomes, and the
  report SHALL NOT explain the conflict to the user. Whether the body itself gets shorter is not
  guaranteed by this change — following a requested format is issue #45's — but nothing about the
  brevity request may remove a protected section.

#### Scenario: A reader never learns which sections are protected

- **WHEN** a report is delivered from a structure whose Overview section is protected
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
It is removed at delivery rather than at measurement (see **report-citations**), so the writer is
judged on what it wrote and the reader is not shown the section twice.

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

### Requirement: The rules the app can check itself are checked in Python, not by a model

Some report rules are decidable from the draft text alone. Those SHALL be owned by the app: the
**section structure** (every section the writer writes present, named exactly as configured, in the
configured order, as a `##` heading, and no other `##` heading), the **word ceiling**, and the
**absence of hyperlinks** (see the requirement above). They SHALL be checked in Python on every
reviewed draft, and their violations SHALL join the review model's violations as one list, so a
revision acts on all of them together.

Each such rule SHALL keep three things in one place: the instruction given to the report writer,
the check over the finished draft, and the wording of the violation a revision acts on. A rule is
configured once from the instance's configuration and used at both points, so the writer can never
be told something different from what its draft is judged against.

**The structure check and the writer see the same list.** The sections the writer is told to write,
the sections the check expects, and the sections the structure rule's violation names SHALL all be
the configured structure itself, with nothing added and nothing subtracted anywhere — the
References section is no part of it, so no derivation stands between the instruction and the check.

**The review model SHALL NOT be asked to judge any of them.** It is told that the app checks the
headings, the length and the hyperlinks, and its own checks are the ones that need a reader: a
padded section, a section that should admit it has nothing to say, the protected-section rules, the
prohibited annotations, valid Markdown, and the citation format. A model verdict SHALL NOT be able to pass a draft that breaks an app-checked
rule, and a review call that fails SHALL NOT suppress one.

#### Scenario: An approving verdict cannot pass a mis-headed draft

- **WHEN** the review model returns no violations for a draft whose `Conclusion` section is written
  as `# Conclusion`
- **THEN** the app's structure rule SHALL report it, a revision SHALL be required while the budget
  allows, and the violation SHALL name the section and the heading it must carry

#### Scenario: A failed review call still reports the app-checked rules

- **WHEN** the review call fails on a draft that is over the ceiling and missing a configured
  section
- **THEN** both violations SHALL still be reported, and the turn SHALL NOT fail

#### Scenario: The review model is not asked about headings, length or hyperlinks

- **WHEN** the report-review call is issued
- **THEN** its prompt SHALL state that the app checks the headings, the length and the hyperlinks
  itself, and SHALL NOT ask it to verify any of them

#### Scenario: The expected headings are the configured structure itself

- **WHEN** the structure check runs on a draft written from a configured structure
- **THEN** the headings it expects SHALL be exactly that structure's sections, with nothing
  subtracted, and a draft carrying exactly those SHALL pass the check

#### Scenario: The review model is told never to ask for a references section

- **WHEN** the report-review call is issued
- **THEN** its prompt SHALL state that the application appends the References section itself after
  the loop settles, and SHALL forbid it to instruct a revision to write one or to list the report's
  sources anywhere, whatever the research question or the approved plan asked for
