## ADDED Requirements

### Requirement: A revision applies the listed changes and keeps the rest of the draft

When the review returns items, the revision call SHALL change the draft only where an item asks
for a change, and SHALL keep every other sentence, table row and citation of the draft as it is. The
loop's last draft is delivered without a review, so a passage that a revision changes without an
item asking for it reaches the user unchecked.

The revision call SHALL receive the report writer's system prompt, the research transcript with the
image content it holds and without the status calls, and the first draft's report request — the
same prefix as the first draft's call — followed by one revision request. The revision request
SHALL carry:

- the instruction to apply each listed change and to change nothing else;
- that an item asking to add a value is applied by adding the value with its citation where the
  item says;
- that an item asking to correct or remove a passage changes only that passage;
- the previous draft's measured word count, the count's exemptions and the word ceiling;
- the review items, inside a `<revision_instruction>` tag;
- the previous draft, inside a `<draft>` tag.

The revision call SHALL bind no tools and SHALL return free text: the whole revised report, and
only the report. It does not receive the review's reasoning, only its items.

A length violation is one of the listed changes, and it asks to condense the whole report (see the
ceiling requirement), so a revision for length MAY restate every section.

#### Scenario: A review asks for two small fixes

- **WHEN** a review returns two items, each naming one passage to correct
- **THEN** the revision request SHALL tell the writer to change only those passages and to keep
  every other sentence, table row and citation of the draft as it is

#### Scenario: An item asks to add a value

- **WHEN** a review item asks to add a value that the draft leaves out
- **THEN** the revision request SHALL tell the writer to add that value with its citation, where
  the item says

#### Scenario: The revision still outputs the whole report

- **WHEN** a revision is written
- **THEN** its output SHALL be the whole revised report, not a list of edits, so the loop can review
  it or deliver it as the answer

#### Scenario: A revision for length condenses the report

- **WHEN** the only item is the app's length violation
- **THEN** the revision SHALL condense the report as the length violation asks, which MAY change
  every section, and SHALL still drop no value to fit
