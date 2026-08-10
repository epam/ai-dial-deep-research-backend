## ADDED Requirements

### Requirement: Prefix-stable report revision assembly

A report revision's request SHALL extend the previous draft's request rather than replace any part
of it: the system prompt, the findings transcript, and the report request stay byte-identical, and
the revision inputs — the draft being revised, the review's instructions, and the measured word
count with the ceiling — are **appended after** them. Successive report calls within one research
run therefore share a byte prefix covering everything the first draft was written from, which is
the bulk of the request.

This is the same shape as research-review's prompt assembly, applied to a different call: content
that grows across calls goes after content that does not.

**report-review's user message SHALL follow the same rule**: the configured structure, the protected
sections, the ceiling, the research question and the approved plan first — all constant across the
review calls of one run — then the draft and its measured word count last.

#### Scenario: A revision extends the draft's prefix

- **WHEN** the report node writes revision N+1 after draft N in the same research run
- **THEN** revision N+1's request SHALL start with the same bytes as draft N's request up through
  the end of the report request section, with the draft, the instructions, and the counts following
  after that common prefix

#### Scenario: Revision inputs are never inserted before the transcript

- **WHEN** a revision's inputs are assembled
- **THEN** neither the review instructions nor the previous draft SHALL be placed ahead of the
  findings transcript or the system prompt, since doing so would invalidate the cached prefix for
  every subsequent call in the run

## MODIFIED Requirements

### Requirement: Prefix-stable reviewer prompt assembly

Research-review's user message SHALL be assembled so that content growing across iterations is
appended after earlier content, never inserted before it: first the research question
(stable for the run), then the findings log (append-only), then the plans list
(append-only). Successive research-review calls within one research run therefore share a byte
prefix covering the question and all previously rendered findings.

#### Scenario: A later research-review call extends the earlier one's prefix

- **WHEN** research-review runs on iteration N and again on iteration N+1 of the same research
  run, with new findings and a new plan added in between
- **THEN** the iteration-N+1 user message starts with the same bytes as the iteration-N
  user message up through the end of iteration N's findings section, and the new findings
  and the plans section follow after that common prefix
