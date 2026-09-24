## Why

The change `demo-pdf-titles-in-citations` labels the demo's citations with the attachment titles
and shortens each pill's title to the default `max_pill_title_chars` budget of 20 characters. A
demo reader then sees `Market Outlook 2025…, page 2` on the pill and cannot check from the pill
which attached file it stands for. The demo exists to show how a client renders a citation, so its
pills carry the whole title.

## What Changes

- The demo does not shorten pill titles. Every pill reads the whole attachment title followed by
  the cited page, the same as the popup card: `Market Outlook 2025.pdf, page 2`.
- This is how a channel's pills read when it sets `max_pill_title_chars` to null. The demo still
  reads no application properties.
- A research turn is unchanged: it shortens pill titles to its channel's budget as before.

This change builds on `demo-pdf-titles-in-citations` and is archived after it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `report-citations`: the requirement "A flag-gated demo completion exercises the citation
  mechanism" says the demo's pills carry the title whole, instead of shortening it to the default
  pill-title budget.

## Impact

- `src/dial_deep_research/app/annotations_demo/completion.py`: passes `pill_title_max_chars=None`
  to `convert_citations`.
- `tests/test_annotations_demo.py`: asserts that the pill titles equal the popup-card titles.
- `README.md`: the demo's "What to look for" list says the title is whole on the pill.
- No change to the shared citation code, to any research turn, or to any application property.
