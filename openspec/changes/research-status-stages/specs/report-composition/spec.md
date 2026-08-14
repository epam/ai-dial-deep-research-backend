## MODIFIED Requirements

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
`[TOOL]`, and SHALL carry the review's outcome and the elapsed time. The prefix SHALL name the report
review specifically: the research review emits a stage of its own in the same title shape, and the two
are told apart by their prefixes (see **research-execution**).

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

#### Scenario: The two review stages are told apart by their prefixes

- **WHEN** one turn emits both a research-review stage and a report-review stage
- **THEN** each SHALL carry its own prefix, so a reader can tell which review produced which stage
