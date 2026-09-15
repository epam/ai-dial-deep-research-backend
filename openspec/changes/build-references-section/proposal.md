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
  writer is shown every configured section except the references one, and a `##` heading matching
  the references section's name in a draft is a structure violation like any other extra heading.
  The delivery step appends the built section after the link-removal pass and the citation
  conversion, so the text the reader sees and the text persisted for the next turn both carry it.

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

- **A references section's `description` stops being writer instructions and becomes the text the
  section carries when the report cited no source at all.** It is the only prose left in an
  app-built section, and it stays configured because it is user-facing text in the channel's own
  language. Every other section's `description` is unchanged.

- **The word ceiling no longer exempts anything but the inline citations.** The exemption existed
  because the writer wrote the references section and its length followed from the research rather
  than from what the report chose to say. The writer no longer writes it, so there is nothing in a
  draft to exempt — and a draft that writes one anyway is in violation, which must not also earn it
  length budget.

- **A references section a draft wrote anyway is removed before the built one is appended**, so a
  reader never sees the section twice. The draft is still judged as the writer wrote it, so the
  stray section is reported as a structure violation and counts toward the ceiling; the removal is
  a delivery-time repair, in the same place and of the same kind as the link removal.

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
- `report-composition`: the references section is written by the application, so the structure
  requirement excludes it from what the writer is given and from what the draft is checked against;
  the word-ceiling requirement drops the references exemption; the empty-report rule moves from
  something the writer must say to something the application writes.
- `application-config-schema`: the new `references_table` on an MCP server entry, required on every
  server; and `ReportSection.description` for a references section, which now carries the
  cited-nothing text rather than writer instructions.
- `research-execution`: the report-node requirement no longer says every cited source is decoded in
  a section the writer writes; it says the application decodes them.
- `logging-policy`: a References section that could not be built is one WARNING naming its kind,
  graded the way the title-read failures are — it costs the section, never a pill and never the
  report.

## Impact

- **`src/dial_deep_research/app_properties.py`**: the `ReferenceColumn` and `ReferencesTable`
  models, the required `references_table` field on `MCPClientSettings`, accessors on
  `ApplicationProperties` handing the citation step each server's table, the rewritten
  `ReportSection.references_section` and `description` field descriptions, and the default
  structure's References description, which becomes the cited-nothing sentence.
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
  removing a stray references section, building the section and appending it, and the new failure
  kind with its warning.
- **`src/dial_deep_research/app/research/report_rules.py`** and
  **`src/dial_deep_research/app/research/prompts.py`**: the structure rule and the rendered
  structure exclude the references section; the length exemptions render the citations alone.
- **`src/dial_deep_research/app/research/report_length.py`**: `_drop_references_section` is
  removed, the draft having no references section to drop.
- **`docs/architecture.md`**: the report-delivery flow gains the section build.
- **`docs/generated-app-schema.json`**: regenerated by `make format` from the new models.
- **`dial_conf/core/applications-template.json`**: every server entry names a `references_table`,
  which a server entry is now required to carry.
- **Not touched**: the README environment-variable table, no environment variable being added; the
  inline citation forms and the annotation payload, which this change does not alter; the
  annotations demo, which converts citations directly and builds no section.
- **Out of scope**: making a References row openable in one click, which waits on the DIAL Chat
  team; and any change to which sources a report may cite.
