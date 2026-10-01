## MODIFIED Requirements

### Requirement: Application properties model

The repository SHALL define a pydantic model (`ApplicationProperties`) that is the single
source of per-channel configuration, replacing the YAML-loaded `ChannelConfig`. The model
SHALL expose:

- `max_research_iterations: int` — default `5`, constrained `ge=1`; the cap on
  research-agent → research-review loops before the report is forced.
- `max_research_graph_steps: int` — default `500`, constrained `ge=1`; the per-graph-run step
  ceiling passed to LangGraph as `recursion_limit` (see the **research-execution**
  capability's step-budget requirement for what it counts).
- `default_report_structure: list[ReportSection]` — the ordered sections **the report writer
  writes** when the user asks for no particular format, constrained `min_length=1`. The References
  section is not among them and cannot be: the application builds it and appends it to every
  report (see the **report-citations** capability), and its two strings are the properties below.
  `ReportSection` is a nested model with three fields:
  - `name: str` — required, non-empty (`min_length=1`); the section's heading in the report.
  - `description: str` — required, non-empty (`min_length=1`); everything the writer and the review
    step need to know about that section's content, and the **single home** for that section's
    rules: no other prompt, model, or spec SHALL carry per-section content instructions.
  - `protected: bool` — default `False`; whether user instructions may drop or restyle this
    section (see the **report-composition** capability's protected-sections requirement).

  `ReportSection` SHALL reject unknown fields (`extra="forbid"`), so a stored section entry
  carrying the withdrawn `references_section` field fails validation rather than being accepted as
  a section the writer is then asked to write beside the app's own.

  The default value SHALL be the four sections Overview, Key Findings, Detailed Analysis and
  Conclusion, each with its description, and Overview SHALL default to `protected: true`.

  The list SHALL be constrained to contain at least one section with `protected: true`, so no
  configuration can produce a report whose every section a user instruction may remove.
  Section `name`s SHALL be unique across the list — as MCP `server_name`s already are — since
  duplicate headings make "every configured section is present" and the review step's
  ordered-section check ambiguous.

  **No section may carry the References section's heading.** Validation SHALL reject a structure
  containing a section whose `name` matches `references_section_name`, compared with the
  surrounding whitespace ignored and the letter case folded: the collision is about the heading a
  reader sees, so `references` collides with `References`. The error SHALL name the offending
  section or sections and the property they collide with, since either half is a fix — rename the
  section, or set the property to another heading. The rule exists because the application appends
  its section unconditionally: a section of that name is one the report writer is told to write, by
  the configured structure it must reproduce, and told not to write, by the rule naming the
  appended section.
- `references_section_name: str` — default `References`, non-empty (`min_length=1`); the heading
  the application writes its References section under. A reader sees it, so a channel sets it in
  the language its readers read.
- `references_section_empty_text: str` — default a single sentence saying the report cites no
  source, non-empty (`min_length=1`); what the References section carries when the report cited
  nothing at all. It is the only prose an app-built section holds, and a reader sees it, so a
  channel sets it in the language its readers read.
- `max_report_words: int` — default `2750`, constrained `ge=1`; the report's word ceiling (see
  the **report-composition** capability for how a word is counted and how the ceiling is
  enforced).
- `max_report_versions: int` — default `3`, constrained `ge=1`; how many report versions may be
  written in one turn. Version 1 is the first draft; each later version is a rewrite the review
  demanded. The last permitted version is delivered without another review. `1` disables the
  review: the first draft is delivered unreviewed.
- `prompts` — a nested required model with two required, non-empty (`min_length=1`) string
  fields: `client_name`, `agent_name`. It SHALL NOT carry a `data_sources_descriptions` field: what
  the models are told about a server's sources is that server's `description` (see **An MCP server
  may describe its sources to the models**), and `Prompts` SHALL reject unknown fields, so a stored
  configuration that still sets `data_sources_descriptions` fails validation instead of having its
  text silently dropped.
  `prompts` SHALL also carry the optional `client_rules` list, empty by default, specified in
  **Prompts carry the channel's client rules** below.

The model SHALL NOT carry a deployment id (`channel_name` is dropped — instance identity
lives in DIAL Core) and SHALL NOT carry an Opik project name (moved to the
`OPIK_PROJECT_NAME` env setting).

#### Scenario: Valid properties validate

- **WHEN** `ApplicationProperties.model_validate` receives an object with the two prompt
  strings and no `max_research_iterations`
- **THEN** validation SHALL succeed and `max_research_iterations` SHALL equal `5`

#### Scenario: Empty prompt field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives an object where
  `prompts.client_name` or `prompts.agent_name` is an empty string
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: Report defaults resolve without configuration

- **WHEN** `ApplicationProperties.model_validate` receives an object that configures no report
  properties
- **THEN** validation SHALL succeed, `default_report_structure` SHALL be the four default sections
  in order (Overview, Key Findings, Detailed Analysis, Conclusion) with Overview alone carrying
  `protected: true`, `references_section_name` SHALL equal `References`,
  `references_section_empty_text` SHALL be the default cited-nothing sentence, `max_report_words`
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

#### Scenario: A section entry carrying the withdrawn references flag is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` whose
  section entry still carries `references_section: true`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the unknown field, rather
  than accepting a References section the report writer would be asked to write beside the one the
  application appends

#### Scenario: A section claiming the References heading is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing a
  section named `references` while `references_section_name` is at its default `References`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming that section and
  `references_section_name`

#### Scenario: A channel writes the section's strings in its readers' language

- **WHEN** an instance sets `references_section_name` and `references_section_empty_text` to
  strings of its own
- **THEN** validation SHALL succeed, the built section SHALL carry that heading, and a report
  citing nothing SHALL carry that text

#### Scenario: Duplicate section names are rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing
  two sections with the same `name`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the duplicated section
  name(s)

#### Scenario: A deployment protects a section of its own

- **WHEN** an instance configures a structure that marks a "Regulatory disclaimer" section
  `protected: true`
- **THEN** validation SHALL succeed and that section SHALL receive the same protection from user
  instructions as Overview does

#### Scenario: The removed descriptions field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives `prompts` carrying
  `data_sources_descriptions`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming `data_sources_descriptions`
  as an unexpected field

## ADDED Requirements

### Requirement: An MCP server may describe its sources to the models, and a document server must say something

`MCPClientSettings` SHALL expose one optional field, `description: str | None`, default `None`,
non-empty and not blank when set: `min_length=1`, and a value of only whitespace SHALL be
rejected, since it would tell the models nothing. It is the static text the models are shown about this
server's sources: for a document server, typically a topics map of the publications it holds; for
a dataset server, anything about the datasets that the fetched list and structures do not say.
The **data-sources-discovery** capability owns where the text is placed in the data-sources string.

Any server type MAY set it. A `statgpt` server is not required to, because the app always fetches
its list of datasets. **A `generic_rag` server SHALL set `description`, `document_stats`, or
both**, and a configuration whose `generic_rag` server sets neither SHALL be rejected with a
validation error naming the server and both fields. Without either, the models would be told
nothing about the documents, while the preparation instructions say that nothing outside the
data sources they list is reachable during research.

The text MAY carry Markdown structure of its own, such as headings: the app shows it inside a tag
of its own (see **data-sources-discovery**), so its headings cannot take in the parts after it.

The field description SHALL tell the admin that the models see this text on every turn, and that
the application fetches and shows on its own the list of datasets, their structures when a
dataset-structure tool is configured, the glossary when one is configured, and the document
statistics when `document_stats` is configured, so a fact the app fetches that is also written
here is shown to the models twice and goes stale when the server's content changes. It SHALL also say that
a `generic_rag` server sets this field, `document_stats`, or both.

The committed `dial_conf/core/applications-template.json` SHALL set `description` on its
`generic_rag` server, the one of the two fields that needs no running server to show, and SHALL
NOT set it on its `statgpt` server.

#### Scenario: A document server carries the topics map

- **WHEN** a `generic_rag` server entry sets `description` to a topics map of its publications
- **THEN** validation SHALL pass, and the data-sources string SHALL carry that text

#### Scenario: A dataset server without a description is valid

- **WHEN** a `statgpt` server entry sets no `description`
- **THEN** validation SHALL pass

#### Scenario: A document server with statistics and no description is valid

- **WHEN** a `generic_rag` server entry sets `document_stats` and no `description`
- **THEN** validation SHALL pass

#### Scenario: A document server with neither is rejected

- **WHEN** a `generic_rag` server entry sets neither `description` nor `document_stats`
- **THEN** validation SHALL fail with an error naming that server, `description` and
  `document_stats`

#### Scenario: An empty or blank description is rejected

- **WHEN** a server entry sets `description` to an empty string or to a string of only whitespace
- **THEN** validation SHALL fail with an error identifying the field

### Requirement: A generic_rag MCP server may configure its document statistics

`MCPClientSettings` SHALL expose one optional field, `document_stats`, default `None`. When set, it
SHALL be a nested object that rejects unknown fields, with these fields:

- `list_documents_tool: str`, required, non-empty: the name of the server's tool that lists the
  indexed documents with their metadata.
- `document_date_key: str`, required, non-empty: the metadata key that holds a document's
  publication date, for example `publication_date`.
- `document_type_key: str | None`, default `None`, non-empty when set: the metadata key that holds
  a document's type, for example `publication_type`. When set, the statistics are also reported
  per type.
- `page_size: int`, default `1000`, constrained `ge=1`: how many documents one call of the list
  tool requests.

The two keys are configured rather than discovered because a Generic RAG channel defines its own
metadata schema, so the names of its date and type fields differ between channels. Setting the
same key for both SHALL NOT be a validation error: no channel is known to need it, and nothing
breaks when one does.

The field description SHALL tell the admin that with `document_stats` the app lists every
document at the start of every turn and shows the models how many documents there are and which
publication dates they cover, overall and per type when `document_type_key` is set. It SHALL
also say that the app requests at most `MAX_DOCUMENT_PAGES` pages, and that when a page cannot be
listed or the cap does not reach the total, the models are told for that turn that the list of
documents could not be obtained. Without it, the app makes no document call. The `page_size` field
description SHALL say that a collection the cap does not cover gets no statistics.

**Only a `generic_rag` server may set it**, and a configuration where any other server type does
SHALL be rejected with a validation error naming the offending server. The documents are served by
the document server.

Naming a tool the server does not advertise, or a key no document carries, SHALL NOT be a
validation error, because the advertised tools and the stored metadata are only known at request
time. A missing tool surfaces as a failed call, which **data-sources-discovery** handles without
failing the turn, and a missing key leaves the dates or the types unknown.

`list_documents_tool` SHALL NOT need to appear in `tools_to_include`, because the app makes the
calls itself. Whether the tool is offered to the research agent remains that filter's decision.

Because the field is optional, `dial_conf/core/applications-template.json` SHALL NOT set it.

#### Scenario: A generic_rag server configures document statistics

- **WHEN** a `generic_rag` server entry sets `document_stats` with `list_documents_tool`
  `list_documents`, `document_date_key` `publication_date` and `document_type_key`
  `publication_type`
- **THEN** validation SHALL pass, and `page_size` SHALL equal `1000`

#### Scenario: A statgpt server configuring document statistics is rejected

- **WHEN** a `statgpt` server entry sets `document_stats`
- **THEN** validation SHALL fail with an error naming that server and stating that only a
  `generic_rag` server may configure document statistics

#### Scenario: An incomplete or malformed object is rejected

- **WHEN** a `document_stats` object omits `document_date_key`, sets `page_size` to 0, or carries
  an unknown field
- **THEN** validation SHALL fail with an error identifying that field

#### Scenario: The type key is optional

- **WHEN** a `document_stats` object sets no `document_type_key`
- **THEN** validation SHALL pass, and the statistics SHALL carry no per-type part
