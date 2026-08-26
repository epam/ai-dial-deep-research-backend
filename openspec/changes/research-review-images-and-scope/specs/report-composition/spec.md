## MODIFIED Requirements

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

Nothing in this requirement obliges the writer to *follow* a user's format request on its own —
that pressure comes from report-review's own check (see "Report-review checks a compatible
user-specified format request" below). This requirement only bounds what such a request can ever
do, however it arrives or whichever step judges it.

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
  report SHALL NOT explain the conflict to the user. Whether the body itself gets shorter is
  governed by report-review's own format check (see "Report-review checks a compatible
  user-specified format request" below), not by this requirement — but nothing about the brevity
  request may remove a protected section.

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

## ADDED Requirements

### Requirement: Report-review checks a compatible user-specified format request

When the research question or the approved plan asks for a report property — its length, tone,
structure, or how the answer is presented — and honoring it would not conflict with the protected
sections, the word ceiling, the prohibited meta-annotations, or the citation format, report-review
SHALL check whether the delivered draft honors it, and SHALL report a violation naming the unmet
request when it does not. Where the request does conflict with any of those, keeping the rule
SHALL NOT be reported as a violation of the request, whatever the request asked for.

This is a judgment the review model makes, not a check the app runs in Python: unlike the length
ceiling or a section heading, no separate machine check exists for an arbitrary format request, so
this requirement is carried entirely by report-review's own prompt.

#### Scenario: An honored, compatible format request is not flagged

- **WHEN** a user asks for the answer as a two-sentence summary, and the delivered draft includes
  such a summary inside the required section structure
- **THEN** report-review SHALL NOT report a violation for that request

#### Scenario: An ignored, compatible format request is flagged

- **WHEN** a user asks for a comparison table and the draft presents the same content as prose
  paragraphs with no table
- **THEN** report-review SHALL report a violation naming the unmet request, and the report loop
  SHALL revise the draft to address it, subject to the version budget

#### Scenario: A request that conflicts with a protected section is never flagged as unmet

- **WHEN** a user asks for no headings at all, which conflicts with the configured section
  structure
- **THEN** report-review SHALL NOT report a violation for keeping the required headings, even
  though the literal "no headings" request went unmet
