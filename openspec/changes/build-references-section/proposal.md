## Why

The report's References section is written by the report-writer model from a prose description of
what belongs in it. Nothing makes its rows correct. The model writes what it recalls from the
chunks it read, so a row can carry a title the publication does not have, a date it never saw, or
leave out a source the report cited — and a reader has no way to tell a recalled row from a real
one. The section exists precisely to be the report's factual index of its sources, which is the one
job a recollection cannot do.

The facts that would make it correct are already fetched, on every turn that delivers a cited
report. The citation step reads the document-metadata resource for every cited document and calls
the dataset catalogue for every cited dataset, and it does so before the text is appended. Building
the section from those answers costs no extra round trip and makes every row a server's metadata
rather than a model's memory.

## What Changes

- **The application builds the References section; the report writer no longer writes it.** The
  section is not part of the configured report structure at all: `default_report_structure` lists
  only the sections the writer writes, and a `##` heading a draft adds for its own references is an
  extra heading, which the structure check rejects like any other. The delivery step appends the
  built section after the link-removal pass and the citation conversion, so the text the reader
  sees and the text persisted for the next turn both carry it.

- **Both the report writer and the report reviewer are told the section is not theirs.** The writer
  is instructed not to write it and not to enumerate its sources anywhere else. The reviewer holds
  the same prohibition as one of its checks, so it reports one the draft wrote and has no ground to
  demand one; today nothing in the review prompt mentions the section at all. The check is needed
  because the app's heading check catches only a
  references section written as a `##` heading: the same list under a `###` sub-heading, in bold,
  or as a bare list of titles would otherwise be forbidden to the writer and detected by nobody.

- **What a References table holds is configured per MCP server.** A new required `references_table`
  on each server entry carries the sub-heading the table is written under and its ordered columns,
  each column a user-facing heading and the metadata key it reads. The `generic_rag` server's table
  describes the documents a report cites; the `statgpt` server's describes its datasets. The
  configuration is where the headings live because the metadata key names are the channel's own and
  the headings are the channel's language.

  **This is a breaking configuration change.** A server entry that does not carry a
  `references_table` fails validation, and the instance's turns reach the user as "application not
  configured" until its properties are edited.

- **The first column names the source, and it is the column that degrades.** A row whose first
  column resolved nothing reads `doc <id>` for a document and the URN for a dataset — the same
  fallback the citation pill already uses. Every other column is left blank when its key resolves
  nothing. **Every source the report cites gets a row**, whether or not its metadata resolved and
  whether or not its citations became pills, because the row is what tells a reader which source a
  marker names.

- **One metadata read serves both the pill label and the References rows.** The document-metadata
  read returns each cited document's stored metadata whole instead of only the configured title,
  and the title key and every configured column key are read out of that one answer. The read is
  unchanged on the wire: it already asks the resource about every cited document.

- **The dataset catalogue read keeps every cited record, including one with no page URL.** Today a
  record without an openable URL is dropped, because the only consumer was the pill. A References
  row wants such a record: the dataset was cited and the reader needs its name. The URL condition
  moves to the conversion, which is where it decides a pill, and a record whose URL is not one a
  browser can open carries no URL at all rather than an unusable one.

- **The References section is non-interactive in this iteration: no row carries a link or a pill.**
  A document's shared URL is storage-relative (`files/<bucket>/appdata/<deployment>/<name>`), so a
  Markdown link to it in the report body resolves against the chat page's own origin and opens
  nothing. Making a row openable therefore means an annotation of its own, which renders the row as
  a pill with a citation card; that is deferred until the one-click behavior we want from a row is
  settled with the DIAL Chat team. The rows name their sources; the inline pills open them.

  Because the app writes no link, the report's no-hyperlink rule needs no exemption and is left
  exactly as it stands.

- **The section's heading and its cited-nothing text become two application properties.**
  `references_section_name` carries the `##` heading the app writes and defaults to `References`;
  `references_section_empty_text` carries what the section says when the report cited no source at
  all and defaults to one plain sentence. Both are reader-facing, so a channel overrides them to
  write them in its readers' language, and both carry defaults, so no existing configuration has to
  be edited for them. `ReportSection` loses its `references_section` flag and with it the rule that
  only the last section may set one: a report structure is now exactly the sections the writer
  writes, and no section's `description` means two different things.

- **The word ceiling no longer exempts anything but the inline citations.** The exemption existed
  because the writer wrote the references section and its length followed from the research rather
  than from what the report chose to say. The writer no longer writes it, so there is nothing in a
  draft to exempt — and a draft that writes one anyway is in violation, which must not also earn it
  length budget.

- **The app never carves a section out of a draft.** A draft that writes its own references
  section carries an extra `##` heading, which the structure check rejects in Python and the
  revision instruction names, so the loop is what removes it, while a version remains. A draft that
  exhausts the version budget still carrying one is delivered with that section followed by the
  app's own. The duplication is accepted deliberately: it is visible to the reader and costs
  nothing, where removing the heading and everything below it silently dropped whatever sections
  the writer had put after it.

- **A references section survives a user instruction because the app writes it, not because it is
  marked protected.** The shipped structure no longer carries a References section to protect, and
  an instruction to leave the sources out is refused by the section being appended unconditionally.

- **A failed build costs the section and nothing else.** It is one WARNING naming its kind, beside
  the citation step's own event, and the report is delivered without the section rather than the
  turn failing.

## Capabilities

### New Capabilities

None. Every requirement this change adds belongs to a capability that already owns the surrounding
behavior.

### Modified Capabilities

- `report-citations`: a new requirement for building the References section — what it contains, how
  a row degrades, where it is appended and what a failure costs; the document-metadata read returns
  each cited document's metadata whole rather than only its title; the dataset-metadata read keeps
  every cited record rather than only those with an openable page URL.
- `report-composition`: the configured structure is the sections the writer writes, with no
  references section in it to exclude; the word-ceiling requirement drops the references exemption;
  the empty-report rule moves from something the writer must say to something the application
  writes; the review model is told never to ask for a references section; and a references section
  survives a user instruction by being appended unconditionally rather than by being a protected
  section.
- `application-config-schema`: the new `references_table` on an MCP server entry, required on every
  server; the new `references_section_name` and `references_section_empty_text` properties, both
  defaulted; and the removal of `ReportSection.references_section` together with the rule that only
  the last section may set it.
- `research-execution`: the report-node requirement no longer says every cited source is decoded in
  a section the writer writes; it says the application decodes them.
- `logging-policy`: a References section that could not be built is one WARNING naming its kind,
  graded the way the title-read failures are — it costs the section, never a pill and never the
  report.

## Impact

- **`src/dial_deep_research/app_properties.py`**: the `ReferenceColumn` and `ReferencesTable`
  models, the required `references_table` field on `MCPClientSettings`, accessors on
  `ApplicationProperties` handing the citation step each server's table, the new
  `references_section_name` and `references_section_empty_text` properties with their defaults, and
  the removal of `ReportSection.references_section`, the `references_section()` and
  `writer_sections()` helpers, the only-last-section validator and the References entry of the
  shipped default structure.
- **`src/dial_deep_research/app/research/references.py`** (new): building the section's Markdown
  from the cited ids, the resolved metadata and the configured tables — pure functions over data,
  so every rule is testable without a server or a model.
- **`src/dial_deep_research/app/research/document_metadata.py`**: `read_document_titles` becomes a
  read of each cited document's metadata object, the title being one key the caller reads out of
  it.
- **`src/dial_deep_research/app/research/dataset_metadata.py`**: every cited record is kept, and a
  record whose URL a browser cannot open carries no URL rather than being dropped.
- **`src/dial_deep_research/app/research/citations.py`**: `DatasetSource.url` becomes optional, and
  the dataset conversion condition reads it as such.
- **`src/dial_deep_research/app/research/runner.py`**: deriving titles from the metadata answer,
  building the section and appending it, and the new failure kind with its warning.
- **`src/dial_deep_research/app/research/report_rules.py`** and
  **`src/dial_deep_research/app/research/prompts.py`**: the structure rule and the rendered
  structure lose the filtering that excluded the references section, the writer is told not to write
  it, the review request carries the same prohibition, and the length exemptions render the
  citations alone.
- **`src/dial_deep_research/app/research/report_length.py`**: `_drop_references_section` is
  removed, the draft having no references section to drop, and `normalize_heading` with it, nothing
  looking a section up by name any more.
- **`docs/architecture.md`**: the report-delivery flow gains the section build.
- **`docs/generated-app-schema.json`**: regenerated by `make format` from the new models.
- **`dial_conf/core/applications-template.json`**: every server entry names a `references_table`,
  which a server entry is now required to carry. The two new section properties stay out of it,
  carrying defaults — a template that copied a default would pin every seeded channel to the value
  it had at seed time.
- **Not touched**: the README environment-variable table, no environment variable being added; the
  inline citation forms and the annotation payload, which this change does not alter; the
  annotations demo, which converts citations directly and builds no section.
- **Out of scope**: making a References row openable in one click, which waits on the DIAL Chat
  team; and any change to which sources a report may cite.
