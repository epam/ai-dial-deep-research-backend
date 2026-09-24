## Context

The citation step in `src/dial_deep_research/app/research/runner.py` (`_run_citation_step`) makes three
passes over the settled draft: link removal, then the citation conversion
(`citations.convert_citations`), then the References build (`_with_references_section`, which calls
`references.build_references_section`). Each pass keeps what the earlier ones finished when it fails.

Today the three modules divide the work like this:

- `citations.py` owns everything about an annotation: the conversion condition
  (`_convertible_citation`, which checks `is_pdf_url` for a document and `is_web_url` for a dataset),
  the annotation bodies (`_document_body`, `_dataset_body`, `_dataset_quote`), the pill shortening
  (`_shorten_for_pill`) and the tag id (`uuid.uuid4().hex[:12]`).
- `references.py` owns the Markdown of the section and knows nothing about annotations. A row is
  `ReferenceRow(identifier, fields)`, and `_render_value` escapes each value for the table while it
  renders it.
- `runner.py` holds the resolved data — `document_urls`, `document_metadata`, `dataset_sources` — and
  appends `converted.annotations` to the delivery. The (8c) log event counts
  `len(delivery.annotations)`.

The budget `max_pill_title_chars` is a field of `ApplicationProperties` in
`src/dial_deep_research/app_properties.py` with `default=20` and `ge=10`.

## Goals / Non-Goals

**Goals:**

- A row is openable on exactly the condition its inline citations are converted, decided by the same
  code, so the two cannot disagree.
- A row's annotation reuses the inline annotation bodies, so the attachment type, the URL handling
  and the dataset quote cannot drift between a row pill and an inline pill.
- `references.py` stays a pure function over data, testable without a server.

**Non-Goals:**

- No count of row pills in the (8c) log event. Its `annotations` field keeps meaning the citations
  the conversion annotated, which is how **logging-policy** defines it. A separate row count can be
  added later if a channel needs it.
- No pill in any column other than the first, and no change to inline pill labels.
- No change to what a pill does on click. Clicking a pill opens its card, and that is the client's
  behavior.
- No References section in the annotations demo.

## Decisions

### D1. `citations.py` builds the row annotation, and `references.py` asks it to

`references.py` gets the row's target and a way to build an annotation for it, and writes the tag
into the first cell. `build_references_section` returns the section text and the row annotations
together, as one result model. The annotation itself is built by a new public function in
`citations.py`, which calls the same `_document_body` and `_dataset_body` the inline conversion
calls. Those two functions take the card label and the pill label as arguments, so an inline
citation passes labels ending in `, page <ix>` or ` dataset` and a row passes its bare name.

*Alternatives considered:*

- **`references.py` builds the annotation itself.** Rejected, because it would copy the attachment
  type, the dataset quote and the shortening rule out of `citations.py`, and the spec says a row's
  annotation carries exactly what a citation's does apart from its labels and page.
- **The runner builds row annotations after the section is built, by finding the tags in it.**
  Rejected, because it parses text the app has just written, and the row that owns each tag is
  already known while the section is written.
- **Build the rows as extra "citations" and run them through `convert_citations`.** Rejected: the
  conversion reads markers from text, folds runs and appends trailing parts, none of which applies to
  a row.

### D2. One pair of predicates decides both conditions

`_convertible_citation` is split into two public functions: one returns the convertible document
citation for a document id and page, given `document_urls`; the other returns the convertible dataset
citation for a URN, given `dataset_sources`. Both return `None` when the source cannot be opened.
`_convertible_citation` calls them, and the runner calls them when it builds the rows. The two
convertible citation models become public, because a row carries one as its target.

*Alternative considered:* the runner checks `document_id in document_urls` and `source.url is not
None` itself. Rejected, because that restates the PDF check and the web-URL check. A later change to
either condition would then open a row the inline citation cannot open, or the reverse.

### D3. The row's label is the first cell's value before escaping

`_render_value` is split into rendering and escaping: it returns the plain value, and the cell
escapes it. The list case joins plain items and escapes once. That is the same output as today,
because escaping each item and then joining them with `, ` gives the same text as joining and then
escaping. The row's label is the plain value of its first column with line breaks turned into
spaces, or its identifier when that value is empty. The cell of an openable row carries only the
tag.

The builder knows whether the label is the `doc <id>` fallback, so it can skip the shortening for
that label, as the spec requires.

*Alternative considered:* unescape the rendered cell to get the label. Rejected, because it
reverses a transformation instead of skipping it, and a value that already contains `\|` would come
out wrong.

### D4. A document row opens at page 1

`document_rows` builds each openable row's target with page 1, whatever pages the report cites. A
row names the whole document, so it opens where the document begins, and the page needs nothing
from the report text.

*Alternatives considered:*

- **The first page the report cites.** The user rejected it: a row names the whole document rather
  than a location in it, and the inline pills already open the cited pages.
- **No selector.** Rejected, because nobody has checked how the client opens a `pdf_bbox`-less PDF
  citation.

### D5. Row annotations are numbered after the inline ones, and the build can fail alone

The runner passes `first_index=len(converted.annotations)` to the build. The build's annotations are
added to the delivery only after the build returns, so a build that raises adds no row annotation,
as the spec's failure rule requires. The runner keeps the inline count for the (8c) event separately
from the combined list it sends.

*Alternative considered:* renumber every annotation just before sending. Rejected, because the
builder then produces indices that are wrong until someone fixes them, and a test of the builder
alone would see them.

### D6. The tag id factory is shared

The default tag id factory becomes a public function in `citations.py`, and `build_references_section`
accepts a `make_tag_id` argument the way `convert_citations` does, so a test can fix the ids. The ids
stay 12 hex characters (48 bits), so a collision between an inline id and a row id is as unlikely as
one between two inline ids.

### D7. The default becomes null and nothing else about the field changes

`Field(default=None, ge=10, ...)`, with the description rewritten to say that null is the default and
that the budget also applies to row pills. `make format` regenerates `docs/generated-app-schema.json`.

*Alternative considered:* remove the property. The user rejected it, because a channel whose client
has little room still needs a budget.

## Risks / Trade-offs

- [A later turn does not see the names of openable rows: the persisted report carries only their
  tags, and the annotations are not restored into the history] → Accepted. Deep Research is run as a
  single turn, so no later turn is expected to read the report back.

- [If sending the annotations fails, an openable row shows the raw tag and no name, because the tag
  replaced the name] → Accepted, and written into the failure requirement. The same failure already
  costs every inline pill, and it is logged as a WARNING.
- [Nobody has seen a pill as the only content of a table cell] → Inline pills in table cells are
  already specified and converted. Check it once in the chat UI with a real report before
  archiving.
- [With null as the default, a long title in a table cell or in a sentence may make a wide pill]
  → A channel whose client lacks room sets `max_pill_title_chars`. This is the trade the user chose.
- [A channel that relied on the default of 20 now gets whole titles] → Such a channel sets
  `max_pill_title_chars: 20` to keep the old behavior. No configuration fails validation.

## Migration Plan

No configuration has to change: the property keeps its name and its floor. After deployment, every
channel that does not set the property shows whole titles on its pills. To roll back, revert the
change. Persisted reports keep whatever tags and annotations they were delivered with.

## No changes required

- `dial_conf/core/applications-template.json`: `max_pill_title_chars` is not required and has a
  default, and a property with a default stays out of the template.
- `README.md`: it does not mention `max_pill_title_chars`, and no environment variable changes.
- `src/dial_deep_research/app/annotations_demo/completion.py`: it already passes
  `pill_title_max_chars=None` and builds no References section.
- `openspec/specs/logging-policy/spec.md`: the (8c) `annotations` count keeps its meaning (D5 and
  the Non-Goals).
- `openspec/specs/report-composition/spec.md`: a `<cit>` marker tag is not one of the hyperlink
  forms the no-hyperlink rule names, so the rule needs no change.
- The code that sends the annotations: it dumps whatever list it gets once, after the content, and
  a longer list changes nothing about it.
- `tests/test_application_properties_resolution.py`: it lists the field's name only.
