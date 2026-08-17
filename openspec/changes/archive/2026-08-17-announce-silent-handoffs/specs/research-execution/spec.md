## MODIFIED Requirements

### Requirement: Every research review's findings are visible as a DIAL stage

Each research-review call SHALL emit one DIAL stage, so a user can see why research ran another
iteration or stopped. The stage SHALL carry:

- the number of the iteration just reviewed, counting from 1;
- the reviewer's assessment of which plan items the findings cover and which they do not;
- the next-iteration steps, as a numbered markdown list — one entry per step (stage content renders
  as markdown). An empty list is the verdict that research is complete, and the stage SHALL say so
  in words rather than render an empty list.

Its title SHALL follow the shape the report-review stage uses (see **report-composition**): its own
prefix rather than `[TOOL]`, the review's outcome, and the elapsed time. The outcome names which way
the loop went from here — another iteration, or the report.

This stage records a decision already taken, which is what separates it from the activity stage the
same node opens on entry: the activity stage is open while the review call runs and says what is
happening now, and this one is closed the moment it appears and says what came of it.

A review that ran SHALL be visible whichever verdict it reached. A failed review call is not caught —
the turn ends as an error and the open activity stage closes as failed — so no findings stage is
emitted for it.

**An iteration the cap left unreviewed SHALL be announced too**, so that "the review found no gaps"
and "nothing reviewed this" stay distinguishable, exactly as they do for a report the version budget
left unreviewed (see **report-composition**). When the just-finished iteration is the last one the
cap permits, the app SHALL emit one stage stating that the review budget is exhausted and the
findings go to the report unreviewed, carrying the iteration number and the configured cap. It is
rendered from the state alone, with no model call, and carries no elapsed time, no assessment and no
next steps, there being no review to report. Because it announces a decision taken while research is
still running, it SHALL be emitted at the moment the routing decision is made, so it appears among
the stages of the run it belongs to rather than after the report's.

A cap of **one** makes no review call and exhausts nothing — a coverage review could never be acted
on, so review is off by configuration — and SHALL emit no stage at all, the same rule a version
budget of one follows in the report loop. The exception covers the stage only: the INFO record SHALL
still fire, the hand-off to the report having happened whatever the reason.

The assessment and the next steps are LLM response text: they SHALL appear in the stage and SHALL NOT
appear in any log record, where the research-review event carries the step count only. This is the
same asymmetry the report-review stage rests on, under **logging-policy**'s content allowlist.

#### Scenario: A review that demands another iteration is visible

- **WHEN** research-review judges iteration 1 short of the plan and returns three next steps
- **THEN** a stage SHALL appear carrying iteration number 1, the assessment, and the three steps as a
  numbered list, and its title SHALL state that another iteration follows, with the elapsed time

#### Scenario: A review that completes research is visible too

- **WHEN** research-review finds every plan item covered and returns no next steps
- **THEN** a stage SHALL still be emitted, carrying the assessment and stating in words that research
  is complete, and its title SHALL state that the report follows

#### Scenario: An unreviewed last iteration is announced as such

- **WHEN** an instance permits 10 iterations and the tenth finishes, so the router routes to the
  report node without a review call
- **THEN** a stage SHALL be emitted stating that the review budget is exhausted and that the run
  proceeds to the report, carrying iteration 10 and the cap of 10, with no elapsed time and no
  assessment

#### Scenario: The announcement precedes the report's own stages

- **WHEN** the iteration cap is reached and the report is then written and reviewed
- **THEN** the exhausted-budget stage SHALL appear before the stages of the report and its review,
  in the order the work happened

#### Scenario: A cap of one emits no stage

- **WHEN** an instance configures a cap of one iteration and that iteration finishes
- **THEN** no research-review stage SHALL be emitted — not the exhausted-budget one either — because
  no review call is made and nothing is exhausted, while the research-iteration-budget-exhausted INFO
  record SHALL still fire

#### Scenario: The assessment never reaches a log record

- **WHEN** a research review records an assessment and next steps, at any configured log level
  including DEBUG
- **THEN** no log record SHALL contain any of that text; only the number of next-plan steps SHALL be
  logged
