## MODIFIED Requirements

### Requirement: The list of datasets is requested with at most three attempts

The app SHALL call the list-datasets tool with no arguments, and SHALL make at most **three
attempts** in total. An attempt SHALL count as failed when the call raises, when the result is
marked as an MCP error, when it does not return by its deadline, or when its structured content
does not carry a `datasets` array, the shape the **report-citations** contract of the tool requires.
Any failed attempt SHALL be retried while attempts remain, whatever the kind of failure. The
attempts SHALL be separated by a growing delay with jitter, on the order of one second before the
second attempt and two seconds before the third.

When all three attempts fail, the datasets section SHALL carry the failure text described in **The
datasets section is rendered as one string**, no structure call SHALL be made, and the turn SHALL
continue.

A list with no datasets SHALL be a successful result, and no structure call SHALL be made.

The successful attempt's result SHALL also be read for the explorer links the list-datasets tool
MAY carry in its `_meta` (the **report-citations** contract of the tool states the payload and what
a missing or unreadable one costs), so the catalogue the turn's citations resolve against carries
them. Only the structured content decides whether an attempt failed: a missing or unreadable
payload SHALL NOT fail an attempt and SHALL NOT be retried. The payload SHALL NOT reach the
datasets section, so no model reads it.

A cancelled turn SHALL NOT be retried or converted into the failure text: cancellation SHALL
propagate.

#### Scenario: A transient failure is retried

- **WHEN** the first list-datasets attempt fails with HTTP 502 and the second succeeds
- **THEN** the app SHALL use the second attempt's answer, and SHALL make no third attempt

#### Scenario: Three failures give the failure text

- **WHEN** all three list-datasets attempts fail
- **THEN** the datasets section SHALL carry the failure text, no structure call SHALL be made, and
  the turn SHALL continue to the preparation agent

#### Scenario: The explorer links reach the catalogue and not the models

- **WHEN** the first list-datasets attempt succeeds and its result carries explorer links under the
  configured `_meta` key
- **THEN** the catalogue the turn's citations resolve against SHALL carry those links, the datasets
  section SHALL carry the structured result alone, and no second attempt SHALL be made

#### Scenario: A result without explorer links is not retried

- **WHEN** the first list-datasets attempt returns a structured result with a `datasets` array and
  no `_meta` payload
- **THEN** the app SHALL use that answer and SHALL make no second attempt
