## MODIFIED Requirements

### Requirement: Reports carry no meta-annotations about the research process

The report SHALL NOT contain annotations about the research process or the model's own
certainty: confidence scores or ratings, certainty or reliability labels, complexity or
difficulty ratings, processing or elapsed times, iteration counts, or token usage. This covers
both explicit fields (`Confidence: High`, `Complexity: moderate`, `Processing time: 4m 12s`)
and equivalent prose or table cells.

Honest qualification of the evidence in prose remains required, not banned: stating that a
figure comes from a single source, that sources disagree, or that a statement is the report's
own inference is content about the findings, not a rating of the research.

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
