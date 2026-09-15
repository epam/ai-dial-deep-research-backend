## ADDED Requirements

### Requirement: MCP server declares the References table its sources are listed in

The application builds the report's References section itself (see **report-citations**), and what a
row of it holds depends on the server the source came from: a document's facts live under that
channel's own metadata keys, a dataset's under the fields its catalogue reports. An MCP server entry
SHALL therefore declare the table its sources are listed in.

`MCPClientSettings` SHALL expose `references_table: ReferencesTable`, a **required** nested model
with two fields:

- `title: str` — required, non-empty (`min_length=1`); the `###` sub-heading the table is written
  under, for example `Documents` or `Datasets`.
- `columns: list[ReferenceColumn]` — required, `min_length=1`; the table's columns in the order they
  are rendered. `ReferenceColumn` carries two required, non-empty strings: `heading`, the column's
  header text, and `key`, the metadata key or catalogue field whose value fills the cell.

Both the table title and every column heading are **user-facing text the reader sees**, so they are
configured rather than fixed: a channel writes them in the language its readers read. Every `key` is
**the channel's own name for a fact**, which is why the app cannot supply one: a document's metadata
schema belongs to the channel that indexed it, and a key's meaning is not inferable from its name.

**The columns are ordered, and the first one names the source.** The first column is the one a reader
identifies the row by, so it is the column that falls back to the source's identifier when its key
resolves nothing (**report-citations** owns that rule). Ordering is why `columns` is a list rather
than an object keyed by heading: the order is behavior, not presentation.

**Every server entry SHALL carry one**, whatever its `server_type` and whatever the instance's
report structure declares. Every supported server type serves sources a report cites, so a server
without a table is a server whose cited sources cannot be listed — the same reason a `generic_rag`
server must name its file-sharing tool and a `statgpt` server its dataset-metadata tool. An instance
whose structure declares no references section still validates and simply builds no section.

**Requiring it is a breaking configuration change**: an instance whose server entries do not carry a
`references_table` fails validation, and its turns are delivered as "application not configured"
until its properties are edited.

The app SHALL NOT derive a column from anything else it is configured with. In particular the
document title key (`document_title_key`) and a table's first column are configured separately and
MAY name different keys: the title key labels a citation pill, which exists whether or not the
structure declares a references section, while the column fills a row. A channel that wants them to
agree names the same key twice, deliberately.

#### Scenario: A server entry without a references table is rejected

- **WHEN** `ApplicationProperties.model_validate` receives an MCP server entry that carries no
  `references_table`
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the missing field

#### Scenario: An empty table is rejected

- **WHEN** a server entry's `references_table` carries an empty `title`, an empty `columns` list, or
  a column with an empty `heading` or `key`
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: Column order is preserved

- **WHEN** a server entry configures columns `Title`/`publication_title` then
  `Published`/`publication_date`
- **THEN** the built table's header row SHALL read `Title` then `Published`, and the first column
  SHALL be the one that falls back to the source's identifier

#### Scenario: A table is required even with no references section configured

- **WHEN** an instance configures a report structure whose every section leaves `references_section`
  at its default of `False`
- **THEN** its server entries SHALL still be required to carry a `references_table`, validation
  SHALL succeed once they do, and no References section SHALL be built

#### Scenario: The title key and the first column are independent

- **WHEN** a `generic_rag` server names `document_title_key` as `publication_title` and a first
  column reading `document_name`
- **THEN** validation SHALL succeed, citation pills SHALL be labelled from `publication_title`, and
  the References rows' first column SHALL be filled from `document_name`

## MODIFIED Requirements

### Requirement: Application properties model

The repository SHALL define a pydantic model (`ApplicationProperties`) that is the single
source of per-channel configuration, replacing the YAML-loaded `ChannelConfig`. The model
SHALL expose:

- `max_research_iterations: int` — default `10`, constrained `ge=1`; the cap on
  research-agent → research-review loops before the report is forced.
- `max_research_graph_steps: int` — default `500`, constrained `ge=1`; the per-graph-run step
  ceiling passed to LangGraph as `recursion_limit` (see the **research-execution**
  capability's step-budget requirement for what it counts).
- `default_report_structure: list[ReportSection]` — the ordered sections a report follows when
  the user asks for no particular format, constrained `min_length=1`. `ReportSection` is a
  nested model with four fields:
  - `name: str` — required, non-empty (`min_length=1`); the section's heading in the report.
  - `description: str` — required, non-empty (`min_length=1`). For a section the report writer
    writes, it is everything the writer and the review step need to know about that section's
    content, and it is the **single home** for that section's rules: no other prompt, model, or
    spec SHALL carry per-section content instructions. For the **references section**, which the
    writer does not write, it is instead the text that section carries when the report cited no
    source at all — the only prose an app-built section holds, configured because it is
    user-facing text in the channel's own language.
  - `protected: bool` — default `False`; whether user instructions may drop or restyle this
    section (see the **report-composition** capability's protected-sections requirement).
  - `references_section: bool` — default `False`; whether this section is the report's list of
    sources. It declares what the section *is*, not what the app does with it: the consequences —
    that the application builds the section rather than the report writer, and that it is excluded
    from the structure the writer is given and checked against — are defined by the
    **report-composition** and **report-citations** capabilities.

  The default value SHALL be the five sections Overview, Key Findings, Detailed Analysis,
  Conclusion, and References, each with its description. Overview and References SHALL default to
  `protected: true`, References SHALL default to `references_section: true`, and the References
  description SHALL be the cited-nothing text rather than entry-format rules, the entry format
  now being the `references_table` each MCP server declares.

  The list SHALL be constrained to contain at least one section with `protected: true`, so no
  configuration can produce a report whose every section a user instruction may remove. **Only the
  last section MAY set `references_section: true`**, since a report lists its sources at the end; a
  structure MAY set it on no section at all, and then no References section is built.
  Section `name`s SHALL be unique across the list — as MCP `server_name`s already are — since
  duplicate headings make "every configured section is present" and the review step's
  ordered-section check ambiguous.
- `max_report_words: int` — default `2750`, constrained `ge=1`; the report's word ceiling (see
  the **report-composition** capability for how a word is counted and how the ceiling is
  enforced).
- `max_report_versions: int` — default `3`, constrained `ge=1`; how many report versions may be
  written in one turn. Version 1 is the first draft; each later version is a rewrite the review
  demanded. The last permitted version is delivered without another review. `1` disables the
  review: the first draft is delivered unreviewed.
- `prompts` — a nested required model with three required, non-empty (`min_length=1`) string
  fields: `client_name`, `agent_name`, `data_sources_descriptions`.

The model SHALL NOT carry a deployment id (`channel_name` is dropped — instance identity
lives in DIAL Core) and SHALL NOT carry an Opik project name (moved to the
`OPIK_PROJECT_NAME` env setting).

#### Scenario: Valid properties validate

- **WHEN** `ApplicationProperties.model_validate` receives an object with the three prompt
  strings and no `max_research_iterations`
- **THEN** validation SHALL succeed and `max_research_iterations` SHALL equal `10`

#### Scenario: Empty prompt field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives an object where any of
  `prompts.client_name`, `prompts.agent_name`, or `prompts.data_sources_descriptions` is an
  empty string
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: Report defaults resolve without configuration

- **WHEN** `ApplicationProperties.model_validate` receives an object that configures no report
  properties
- **THEN** validation SHALL succeed, `default_report_structure` SHALL be the five default
  sections in order (Overview, Key Findings, Detailed Analysis, Conclusion, References) with
  Overview and References carrying `protected: true`, References alone carrying
  `references_section: true` and the cited-nothing text as its description, `max_report_words`
  SHALL equal `2750`, and `max_report_versions` SHALL equal `3`

#### Scenario: Empty report structure is rejected

- **WHEN** `ApplicationProperties.model_validate` receives `default_report_structure` as an
  empty list, or a section with an empty `name` or `description`
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: A structure with no protected section is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` whose
  every section leaves `protected` at its default of `False`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming
  `default_report_structure` and stating that at least one section must be protected

#### Scenario: A references section before the last one is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` where a
  section other than the last sets `references_section: true`
- **THEN** validation SHALL raise a pydantic `ValidationError` stating that only the last section
  may set it, and naming the misplaced section

#### Scenario: A structure with no references section validates

- **WHEN** an instance configures a structure whose every section leaves `references_section` at
  its default of `False`
- **THEN** validation SHALL succeed, and no References section SHALL be built

#### Scenario: Duplicate section names are rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing
  two sections with the same `name`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the duplicated section
  name(s)

#### Scenario: A deployment protects a section of its own

- **WHEN** an instance configures a structure that marks a "Regulatory disclaimer" section
  `protected: true`
- **THEN** validation SHALL succeed and that section SHALL receive the same protection from user
  instructions as the references section does
