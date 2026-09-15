## 1. Configuration

- [x] 1.1 Add `ReferenceColumn` (`heading`, `key`) and `ReferencesTable` (`title`, `columns`) to `app_properties.py`, with the field descriptions the generated schema publishes.
- [x] 1.2 Add the required `references_table: ReferencesTable` field to `MCPClientSettings`.
- [x] 1.3 Add `references_tables` to `ApplicationProperties`, handing the citation step each server's table paired with the server type its sources come from.
- [ ] 1.4 Add `references_section_name` (default `References`) and `references_section_empty_text` (default the cited-nothing sentence) to `ApplicationProperties`, each non-empty, with the field descriptions the generated schema publishes.
- [ ] 1.5 Remove `ReportSection.references_section`, restore `description`'s field description to the one meaning it has for a section the writer writes, and set `extra="forbid"` on `ReportSection` so a stored entry still carrying the withdrawn field fails validation.
- [ ] 1.6 Remove the References entry from `DEFAULT_REPORT_STRUCTURE`, leaving Overview, Key Findings, Detailed Analysis and Conclusion with Overview protected, and delete `_REFERENCES_DESCRIPTION`.
- [ ] 1.7 Delete the `references_section(sections)` and `writer_sections(sections)` helpers and the only-last-section check in `_validate_report_structure`, with every caller.

## 2. Resolution

- [x] 2.1 Rename `read_document_titles` to `read_document_metadata` and return each cited document's metadata object whole; move the title extraction to the caller.
- [x] 2.2 Make `DatasetSource.url` optional, and normalize a URL `is_web_url` rejects to `None` where the record is built.
- [x] 2.3 Stop dropping URL-less records in `read_dataset_sources`, and carry each record's `raw_fields` for the References row.
- [x] 2.4 Update `_convertible_citation` to read the now-optional dataset URL.

## 3. The References section

- [x] 3.1 Write `app/research/references.py`: cell rendering (string, number, boolean, list, anything else), pipe and newline escaping, and the first-column identifier fallback.
- [x] 3.2 Build one table per server whose sources the report cites, in configured order, each under its `###` title, skipping a server with nothing cited.
- [x] 3.3 Render the whole section: the `##` heading, the tables, or the cited-nothing text when no source was cited.
- [x] 3.4 Strip a string value before rendering it, so a value that only looks filled leaves the cell empty and the first column reaches its fallback.
- [ ] 3.5 Take the heading from `references_section_name` and the cited-nothing text from `references_section_empty_text`, neither coming from a report section any more.
- [ ] 3.6 Delete `strip_references_section`, the app removing no text a writer wrote.

## 4. Delivery

- [x] 4.1 Derive titles from the metadata answer in the runner, keeping the titled count bounded by the resolved count.
- [x] 4.2 Add the `references_build_failed` kind and its warning, and make a failure cost the section alone.
- [x] 4.3 Recompute `datasets_resolved` as the number of selected records carrying a URL, so the (8c) event's contract holds.
- [ ] 4.4 Make the section build the citation step's third pass on every turn that delivers a report: build and append, with no strip before it and no configuration able to skip it.

## 5. Prompts and rules

- [x] 5.1 Make `LENGTH_EXEMPTIONS` the inline citations alone, and delete `render_length_exemptions`.
- [x] 5.2 Delete `_drop_references_section` from `report_length.py` and its use in `count_report_words`.
- [ ] 5.3 Render the report structure and the protected-section names from the configured structure itself, with no section subtracted at either layer.
- [ ] 5.4 Make `ReportStructureRule` expect the configured structure, so a `## References` heading in a draft is an extra heading the check reports.
- [ ] 5.5 Word the writer's references rule from `references_section_name` rather than from a section entry, keeping it a prohibition on writing the section or listing sources anywhere else.
- [ ] 5.6 Add the same prohibition to `REPORT_REVIEW_REQUEST`: the app appends the section itself, and the reviewer never asks a revision for one, whatever the question or the approved plan said. It is not asked to check for one.
- [ ] 5.7 Delete `find_section_heading_line` and `normalize_heading` from `report_length.py`, nothing looking a section up by name any more.

## 6. Cleanups this change carries

- [x] 6.1 Remove the unused `sections` parameter from `route_after_report` and from its callers.
- [x] 6.2 Correct the docstrings that still explained a word-count exemption for the references section (`_validate_report_structure`, `normalize_heading`), and rewrap `ReportReviewOutcome`'s.

## 7. Tests

- [x] 7.1 Unit-test `references.py`: every cell-rendering rule, the escaping, the first-column fallback including a whitespace-only value, the dropped table and the cited-nothing text.
- [x] 7.2 Test the configuration: a server entry with no table rejected, an empty title or column rejected, column order preserved, and a title key differing from the first column.
- [x] 7.3 Test the delivery: the built section appended after the conversion, every cited source listed without a pill, and a build failure delivering the pills without the section.
- [ ] 7.4 Test the two new properties: their defaults resolving without configuration, an instance setting both, and a section entry carrying `references_section` rejected.
- [ ] 7.5 Replace the `strip_references_section` tests with one asserting that a draft's own references section and every section after it survive delivery, followed by the built section.
- [ ] 7.6 Test that the review request carries the prohibition, and that the rendered structure for both prompts is the configured structure entire.
- [ ] 7.7 Update the tests that assume a references section in the report structure, a `references_section` flag, or a structure that declares none.

## 8. Documentation and artifacts

- [x] 8.1 Add a `references_table` to every server entry in `dial_conf/core/applications-template.json`; the two new properties stay out of it, carrying defaults.
- [ ] 8.2 Update `docs/architecture.md`: the citation step's third pass appends and removes nothing, and the report structure no longer carries the section.
- [ ] 8.3 Run `make format` to regenerate `docs/generated-app-schema.json`, then `make lint` and the test suite.
