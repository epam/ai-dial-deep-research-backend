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

Evidence the run could not obtain falls on the permitted side of that line, but only when it is
stated as a property of the evidence. When a source could not be reached — a tool failed, per the
**tool-call-fault-tolerance** capability — the report MAY say that the evidence is absent and
what therefore cannot be concluded; omitting an unreachable source entirely breaks nothing. It SHALL NOT name the tool, describe the failure, give its
status or error text, or say how many attempts were made: those are facts about the run, which
this requirement bans, and the reader can act on none of them.

The review step SHALL enforce this boundary as it enforces the rest of this requirement. Its
checklist is closed — it reports only the violations it is given — so a draft naming the failed
tool or counting the attempts is caught only if the list says so.

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

#### Scenario: An unreachable source is reported as missing evidence

- **WHEN** a tool the run needed failed and the evidence it would have produced is absent from the
  findings
- **THEN** the report MAY state that the evidence is unavailable and what cannot be concluded from
  its absence, and SHALL NOT state which tool failed, how it failed, or how many attempts were made
