## Why

The annotations demo labels every citation with its marker text, `doc 1, page 2`, because it
resolves no titles. A real report labels a cited document with its publication title, so the
demo does not show the pill and the popup card as a reader of a real report sees them: a title
that fits the pill, a title the pill shortens, and the card carrying the title whole.

## What Changes

- The demo labels each citation of an attached document with the attachment's title, which is the
  name the chat shows for the attached file, followed by the cited page:
  `Market Outlook 2025.pdf, page 2`.
- The title stored in the PDF's own metadata is not used. It is often missing, or filled with a
  value the authoring tool generated, while the attachment title is the name the caller already
  sees in the chat.
- When the attachment carries no title, the label keeps its marker text, as a research turn's
  label does when no title resolved.
- The pill shortens the title to the default `max_pill_title_chars` budget, because the demo reads
  no application properties. The popup card carries the title whole.
- The demo's `citations resolved` log event counts the titles it found, instead of always
  reporting zero.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `report-citations`: the requirement "A flag-gated demo completion exercises the citation
  mechanism" permits a second difference from a research turn — where the document titles come
  from — and states how the demo obtains them and which pill budget it applies.
- `logging-policy`: the requirement that defines the `citations resolved` event says what the
  titled count means in the demo, instead of saying it is always zero there.

## Impact

- `src/dial_deep_research/app/annotations_demo/attachments.py`: returns each attachment's title
  alongside its URL.
- `src/dial_deep_research/app/annotations_demo/completion.py`: passes the titles and the default
  pill budget to `convert_citations`, and logs the titled count.
- `tests/test_annotations_demo.py`: covers the attachment-title label, the marker-text fallback
  and the shortened pill.
- `README.md`: the demo's "What to look for" list describes the labels.
- No change to the shared citation code, to any research turn, or to any application property.
