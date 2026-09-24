## 1. Pill budget default

- [x] 1.1 Set the default of `max_pill_title_chars` to `None` in `app_properties.py`, keeping `ge=10`, and rewrite its field description to say null is the default and that the budget also applies to a References row's pill.
- [x] 1.2 Update `test_the_pill_title_budget_has_a_default` in `tests/test_app_properties.py` to expect `None`.

## 2. Shared citation pieces

- [x] 2.1 Split `_convertible_citation` into two public functions, one per kind of source, returning the convertible citation or `None`, and make `_convertible_citation` call them (design D2).
- [x] 2.2 Make the two convertible citation models public, since a References row carries one as its target.
- [x] 2.3 Let `_document_body` and `_dataset_body` take the card label and the pill label as arguments, with the inline conversion passing labels that end in `, page <ix>` or ` dataset` (design D1).
- [x] 2.4 Add a public function building a row's annotation from an index, a tag id, a label, a target, whether the label is the identifier fallback, and the pill budget: both labels are the bare label, the pill's copy shortened unless it is a document's `doc <id>` fallback.
- [x] 2.5 Open a document row at page 1 (design D4).
- [x] 2.6 Make the default tag id factory a public function shared by the conversion and the References build (design D6).

## 3. References section

- [x] 3.1 Split `_render_value` into rendering and escaping, so the plain value of the first column is available as a label (design D3).
- [x] 3.2 Give `ReferenceRow` an optional target; a row with one carries only a marker tag in its first cell and yields one annotation.
- [x] 3.3 Make `build_references_section` return the section text and its row annotations together, taking the first index, the pill budget and a tag id factory.
- [x] 3.4 Let `document_rows` and `dataset_rows` attach each row's target from the document URLs, and from the dataset sources.
- [x] 3.5 Rewrite the module docstring's "No row is interactive" paragraph to describe openable rows.

## 4. Delivery

- [x] 4.1 In `runner.py`, pass the document URLs, dataset sources, pill budget and `len(converted.annotations)` to the References build, and add the row annotations to the delivery only when the build succeeds (design D5).
- [x] 4.2 Keep the (8c) event's `annotations` count at the number of inline annotations.

## 5. Tests and docs

- [x] 5.1 Add tests in `tests/test_references_section.py` for the References scenarios in the delta spec: a document row opening at page 1, a dataset row, a row that stays text, a row labelled by its identifier, the budget on a row pill, a label not escaped for the table, indices following the inline ones, and no hyperlink.
- [x] 5.2 Update existing tests that asserted no marker tag in the section or a default budget of 20, and add a runner test that a failing References build emits no row annotation.
- [x] 5.3 Update the citation-step paragraph of `docs/architecture.md` for openable rows and the null default.
- [x] 5.4 Run `make format` (which regenerates `docs/generated-app-schema.json`), `make lint` and `make test`.

## 6. Review follow-ups

- [x] 6.1 Add delta specs for `research-execution` (the References section names in text only the sources whose citations did not convert) and `logging-policy` (the (8c) count leaves out row annotations).
- [x] 6.2 Fix the docstrings of `build_references_section` (it returns the text and the row annotations) and `ConvertibleDocumentCitation` (a row's page is not named by a marker).
- [x] 6.3 Add tests: a dataset row whose record carries a URL that is not a web URL stays text; a References build that raises after some rows became pills adds no row annotation; a delivered pill under the default budget carries the whole title.
