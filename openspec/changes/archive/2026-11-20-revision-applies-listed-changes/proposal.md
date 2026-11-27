## Why

The report loop's last draft is delivered without a review. The revision request asks the writer to
rewrite the draft in full, so a revision can move, merge or drop correct passages that no review item
named, and when that revision is the last one, nothing catches it. In report-loop replays on fixed
research, a revision that a review asked to make small fixes also moved, merged or dropped correct
passages that no item named.

## What Changes

- The revision request asks the writer to apply each change that the review items list and to keep
  every other sentence, table row and citation of the draft as it is, in place of a rewrite in full.
- An item that asks to add a value is applied by adding the value with its citation where the item
  says; an item that asks to correct or remove a passage changes only that passage.
- The revision still outputs the whole revised report, and only the report.
- The report-composition spec states what the revision call receives and returns.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `report-composition`: a new requirement for the revision call — its inputs, and that it applies
  the listed changes and keeps the rest of the draft.

## Impact

- `src/dial_deep_research/app/research/prompts.py`: the text of `REPORT_REVISION_REQUEST`.
- Every channel's report loop: revisions change less of the draft. The length violation still asks
  to condense the whole report, so a revision for length can still touch every section.
- No configuration, API or dependency change.
