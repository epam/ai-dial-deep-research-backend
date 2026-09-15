## 1. Configuration

- [x] 1.1 Add `ReferenceColumn` (`heading`, `key`) and `ReferencesTable` (`title`, `columns`) to `app_properties.py`, with the field descriptions the generated schema publishes.
- [x] 1.2 Add the required `references_table: ReferencesTable` field to `MCPClientSettings`.
- [x] 1.3 Rewrite `ReportSection.description`'s field description to state both branches, and `references_section`'s to say the app builds the section.
- [x] 1.4 Replace `_REFERENCES_DESCRIPTION` with the cited-nothing text, and keep the default structure otherwise unchanged.
- [x] 1.5 Add a `writer_sections(sections)` helper beside `references_section(sections)` returning the structure minus its references section.
- [x] 1.6 Add `references_tables` to `ApplicationProperties`, handing the citation step each server's table paired with the server type its sources come from.

## 2. Resolution

- [x] 2.1 Rename `read_document_titles` to `read_document_metadata` and return each cited document's metadata object whole; move the title extraction to the caller.
- [x] 2.2 Make `DatasetSource.url` optional, and normalize a URL `is_web_url` rejects to `None` where the record is built.
- [x] 2.3 Stop dropping URL-less records in `read_dataset_sources`, and carry each record's raw fields for the References row.
- [x] 2.4 Update `_convertible_citation` to read the now-optional dataset URL.

## 3. The References section

- [x] 3.1 Write `app/research/references.py`: cell rendering (string, number, boolean, list, anything else), pipe and newline escaping, and the first-column identifier fallback.
- [x] 3.2 Build one table per server whose sources the report cites, in configured order, each under its `###` title, skipping a server with nothing cited.
- [x] 3.3 Render the whole section: the `##` heading, the tables, or the cited-nothing text when no source was cited.
- [x] 3.4 Add `strip_references_section(text, name)` removing a `##` heading matching the configured name and everything after it.

## 4. Delivery

- [x] 4.1 Derive titles from the metadata answer in the runner, keeping the titled count bounded by the resolved count.
- [x] 4.2 Run the section build as the citation step's third pass: strip a stray section, build, append.
- [x] 4.3 Add the `references_build_failed` kind and its warning, and make a failure cost the section alone.
- [x] 4.4 Recompute `datasets_resolved` as the number of selected records carrying a URL, so the (8c) event's contract holds.

## 5. Prompts and rules

- [x] 5.1 Render the report structure and the protected-section names from `writer_sections`, so neither prompt carries the references section.
- [x] 5.2 Make `ReportStructureRule` expect `writer_sections`, so a `## References` heading in a draft is a violation.
- [x] 5.3 Make `render_length_exemptions` render the inline citations alone.
- [x] 5.4 Delete `_drop_references_section` from `report_length.py` and its use in `count_report_words`.

## 6. Tests

- [x] 6.1 Unit-test `references.py`: every cell-rendering rule, the escaping, the first-column fallback, the dropped table, the cited-nothing text, and the section with no configured references section.
- [x] 6.2 Unit-test `strip_references_section` against a matching heading, a renamed one, and one at another level.
- [x] 6.3 Test the configuration: a server entry with no table rejected, an empty title or column rejected, column order preserved, and a title key differing from the first column.
- [x] 6.4 Test the delivery order end to end: a stray section removed, the built one appended after the conversion, and a build failure delivering the pills without the section.
- [x] 6.5 Update the existing tests that assume the writer writes the references section, that the word count exempts it, and that `read_document_titles` returns titles.

## 7. Documentation and artifacts

- [x] 7.1 Update `docs/architecture.md` with the citation step's third pass.
- [x] 7.2 Add a `references_table` to every server entry in `dial_conf/core/applications-template.json`.
- [x] 7.3 Run `make format` to regenerate `docs/generated-app-schema.json`, then `make lint` and `make test`.
