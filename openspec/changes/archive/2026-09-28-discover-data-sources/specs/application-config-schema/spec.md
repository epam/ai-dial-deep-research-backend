## ADDED Requirements

### Requirement: A statgpt MCP server may declare its glossary tools

`MCPClientSettings` SHALL expose one optional field, `glossary`, with no default value. When set,
it SHALL be a nested object with four required fields, and it SHALL reject unknown fields, so a
misspelled field fails validation instead of being ignored:

- `list_terms_tool: str`, non-empty: the name of the server's tool that lists the glossary's
  terms.
- `definitions_tool: str`, non-empty: the name of the server's tool that returns the definitions
  of named terms.
- `max_terms_per_definitions_call: int`, constrained `ge=1`: the largest number of terms one call
  of the definitions tool may request.
- `references_table`: a `ReferencesTable`, the model a server's References table uses, with a title
  and columns keyed by fields of a glossary term's record, such as `term` and `definition`. It
  configures the glossary table of the References section (see **report-citations**). A reader
  sees the title and the headings, so a channel writes them in the language its readers read. The
  field descriptions of `ReferencesTable` and `ReferenceColumn` SHALL cover the glossary table
  too: a column's key can be a field of a glossary term's record, and the first column falls back to
  the cited term.

The two tool names SHALL name different tools, and a `glossary` object whose `list_terms_tool` and
`definitions_tool` are equal SHALL be rejected with a validation error stating that both fields name
the same tool. The app calls the list tool with no arguments and the definitions tool with
`{"terms": [...]}`, and the References glossary table tells the research agent's results of the two
tools apart by name, so one tool configured as both would be called and read with the wrong shape.

The field's description SHALL tell the admin to set the `glossary` object whenever the server
exposes glossary tools that the research agent would be offered anyway, which is when the server's
`tools_to_include` is empty or already names the glossary tools. Without the object the app neither
fetches the glossary, nor gives the report writer the terminology rule and the glossary citation
form, nor lists cited terms in the References section.

The limit SHALL be configured rather than discovered, because the server states it only as prose in
the tool's argument description, and a request over it fails whole. The **data-sources-discovery**
capability owns how the app uses the three values.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. The glossary is served by the
dataset server. Since at most one server of each type may be configured, at most one configured
server names a glossary, which follows from the two rules rather than needing a third check.

A `statgpt` server is **not** required to set it: a channel whose server exposes no glossary is a
valid channel.

Naming a tool the server does not advertise SHALL NOT be a validation error, because the advertised
tool list is only known at request time. It SHALL surface as failed glossary calls, which
**data-sources-discovery** turns into the failure text without failing the turn.

The two tool names SHALL NOT need to appear in `tools_to_include`. That filter states which tools a
model is offered, and the app makes the glossary calls itself. Whether the definitions tool is
offered to the research agent remains the filter's decision.

Because the field is optional, `dial_conf/core/applications-template.json` SHALL NOT set it.

#### Scenario: A statgpt server declares a glossary

- **WHEN** a `statgpt` server entry sets `glossary` with the two tool names and a limit of 10
- **THEN** validation SHALL pass, and the app SHALL fetch the glossary through exactly those tools
  in batches of at most 10 terms

#### Scenario: A generic_rag server declaring a glossary is rejected

- **WHEN** a `generic_rag` server entry sets `glossary`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may declare a glossary

#### Scenario: An incomplete glossary is rejected

- **WHEN** a `glossary` object omits `max_terms_per_definitions_call` or `references_table`, or sets
  `max_terms_per_definitions_call` to 0
- **THEN** validation SHALL fail with an error identifying that field

#### Scenario: A glossary naming one tool for both roles is rejected

- **WHEN** a `glossary` object sets `list_terms_tool` and `definitions_tool` to the same name
- **THEN** validation SHALL fail with an error stating that both fields name the same tool

#### Scenario: A statgpt server without a glossary is valid

- **WHEN** a `statgpt` server entry sets no `glossary`
- **THEN** validation SHALL pass, and no glossary call SHALL be made for that channel

### Requirement: A statgpt MCP server may declare its dataset-structure tool

`MCPClientSettings` SHALL expose one optional string field, `dataset_structure_tool`, with no
default value, naming the server's tool that returns the structure of one dataset. When it is set,
the app fetches the structure of every dataset the list-datasets tool reported, at the start of
every turn, and shows the structures to the models. The **data-sources-discovery** capability
owns the tool's contract and how the app uses it.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. The structures describe the
datasets the list-datasets tool reports, and only a `statgpt` server names that tool. Since at
most one server of each type may be configured, at most one configured server names a
dataset-structure tool.

A `statgpt` server is **not** required to set it. Without it the models see the list of datasets
and no structures, and the research agent can still call the structure tool itself when the
server's `tools_to_include` filter offers it.

The field's description SHALL say that showing the datasets to the models is designed for a
channel whose catalogue holds on the order of ten datasets, because the whole list and every
structure reach every call that receives the data-sources string, and that leaving the field unset
shows the list without the structures.

Naming a tool the server does not advertise SHALL NOT be a validation error, because the advertised
tool list is only known at request time. It SHALL surface as failed structure calls, which
**data-sources-discovery** turns into failure entries without failing the turn.

The name SHALL NOT need to appear in `tools_to_include`. That filter states which tools a model is
offered, and the app makes the structure calls itself. Whether the structure tool is offered to
the research agent remains the filter's decision.

Because the field is optional, `dial_conf/core/applications-template.json` SHALL NOT set it.

#### Scenario: A statgpt server declares a dataset-structure tool

- **WHEN** a `statgpt` server entry sets `dataset_structure_tool` to the name of a tool it
  advertises
- **THEN** validation SHALL pass, and the app SHALL call exactly that tool once for every dataset
  the list-datasets tool reported

#### Scenario: A generic_rag server declaring a dataset-structure tool is rejected

- **WHEN** a `generic_rag` server entry sets `dataset_structure_tool`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a dataset-structure tool

#### Scenario: A statgpt server without a dataset-structure tool is valid

- **WHEN** a `statgpt` server entry sets no `dataset_structure_tool`
- **THEN** validation SHALL pass, and no structure call SHALL be made by the app for that channel

## RENAMED Requirements

- FROM: `### Requirement: MCP server declares its dataset-metadata tool`
- TO: `### Requirement: MCP server declares its list-datasets tool`

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
- `prompts` — a nested required model with three required, non-empty (`min_length=1`) string
  fields: `client_name`, `agent_name`, `data_sources_descriptions`. The field description of
  `data_sources_descriptions` SHALL tell the admin to write in it only what the app does not fetch
  from the servers itself, and SHALL name what the app fetches: the list of datasets, their
  structures when a dataset-structure tool is configured, and the glossary when one is configured
  (see **data-sources-discovery**). The app appends what it fetched after this text, so a channel
  that also describes its datasets here shows the models each dataset twice.

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

### Requirement: MCP server declares which supported retrieval server it is

`MCPClientSettings` SHALL carry a required `server_type` field whose value is one of a **closed**
list of supported retrieval servers: `generic_rag`, which serves the documents a report cites as
`[doc <id>, page <ix>]`, and `statgpt`, which serves the datasets it cites as `[dataset <id>]`.
There SHALL be no default and no other accepted value, so a server whose type is absent or
unrecognised fails validation.

The list is closed on purpose, and it is a statement about **attribution** rather than about
connectivity. What a citation must carry — an integer document id and a 1-based page number (see
**research-execution**) — is no part of the MCP protocol, and neither is the compact
`(doc_id, page_ix)` form the report writer is taught to translate. A retrieval server that
attributes its results differently, with documents that have no pages or with web pages instead of
files, cannot be expressed in the citation format at all, so admitting it is a change to that
format and to its parser rather than a configuration entry. Naming the supported servers is
therefore the honest statement of what this application works with; the open contracts are the
file-sharing tool and the list-datasets tool below, whose **names** any server may choose.

`ApplicationProperties` SHALL reject a configuration carrying **more than one** server of the same
type, with a validation error naming the type and the offending servers. Each server numbers its
own content, and a citation carries that number without saying which server issued it, so two
servers of one type make an id ambiguous with nothing in the marker, the retrieval result or the
protocol able to tell them apart. This holds for dataset servers as well as document ones, and more sharply than it once did: a
dataset citation is now resolved back against the configured dataset server to find the dataset's
name and the address of its page, so two dataset servers shipping the same dataset id would let a
pill open the wrong dataset's page rather than merely reading ambiguously. Supporting several
servers of one type requires a citation to name its source first — a change to the
**research-execution** citation requirement.

`server_name` stays a separate field and keeps its own purpose: it is the connection key the app
builds its MCP client with, and it must be unique across the list, whereas `server_type` says what
the server is. Neither reaches a model or appears in a citation.

#### Scenario: One server of each type is accepted

- **WHEN** `ApplicationProperties.model_validate` receives one `generic_rag` server and one
  `statgpt` server
- **THEN** validation SHALL succeed

#### Scenario: A server with no type is rejected

- **WHEN** an MCP server entry omits `server_type`
- **THEN** validation SHALL fail on that field

#### Scenario: An unsupported type is rejected

- **WHEN** an MCP server entry names a type outside the supported list
- **THEN** validation SHALL fail on that field, rather than accepting a server whose attribution
  the citation format cannot express

#### Scenario: Two servers of one type are rejected

- **WHEN** `ApplicationProperties.model_validate` receives two `generic_rag` servers
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the type and both servers

#### Scenario: Two dataset servers are rejected by the same rule

- **WHEN** `ApplicationProperties.model_validate` receives two `statgpt` servers
- **THEN** validation SHALL raise, a dataset id being resolved back against the configured
  dataset server, so two of them would let a pill open the wrong dataset's page

#### Scenario: The generated schema carries the type as an enumeration

- **WHEN** the DIAL application-type schema is generated from `ApplicationProperties`
- **THEN** the MCP server entry SHALL carry `server_type` as a required string enumeration of the
  supported values, inlined rather than referenced through `$defs`, and the committed schema
  artifact SHALL be regenerated to match

### Requirement: MCP server declares its document-metadata resource and title key

`MCPClientSettings` SHALL expose two string fields, `document_metadata_resource` and
`document_title_key`, naming the MCP resource this server serves document metadata from and the
metadata key that holds a document's human title in this channel's schema. The **report-citations**
capability owns what that resource must answer with; these fields carry only where to read it and
which key to take, and they are the only things the app knows about either before reading.

`document_metadata_resource` SHALL be a resource URI template carrying exactly one placeholder,
`{document_ids}`. A value with no placeholder, or with more than one, SHALL be rejected: the app
substitutes the cited ids into it, so a template it cannot substitute into names no readable
resource.

**A `generic_rag` server SHALL name both**, and a configuration where one names neither SHALL be
rejected with a validation error naming that server. The rule is the `file_sharing_tool` rule, for
the same reason it is the `list_datasets_tool` rule: a document citation carries an integer id
that means something only inside the server that issued it, so a channel with no metadata resource
labels every pill `doc <id>, page <ix>` — a number the reader cannot place against any publication
they know. A document server is in a deployment to have its publications cited, and a citation
naming an internal number is not worth serving silently.

**They SHALL be set together or not at all.** A configuration setting one without the other SHALL be
rejected with an error of its own — a URI with no key names nothing to take, and a key with no URI
has nothing to take it from — so a half-configured pair reads as the mistake it is rather than as a
server that named neither.

The cost of requiring them is paid at configuration rather than at delivery: a channel whose
document metadata genuinely carries no title cannot be configured, and an existing channel that has
not set the fields fails validation until it does, which reaches the user as "application not
configured". A **runtime** absence is unchanged and still costs only a label: an id the resource
does not know, or a document carrying nothing usable under the configured key, keeps the marker
label and converts as before (see **report-citations**).

**Only a `generic_rag` server may set them.** A `statgpt` server SHALL be rejected for setting
either: it serves datasets rather than documents, and a document-metadata resource named there would
never be read. Together with the rule that at most one server of each type may be configured, this
makes "at most one configured server names a document-metadata resource" a consequence rather than a
rule of its own, for the same reason it is one for the file-sharing tool.

Both SHALL be plain string fields on `MCPClientSettings` rather than a nested model, for the reason
the file-sharing field states: the DIAL application-type schema inlines each root property's model
and rejects a model nested below that, and `mcp_servers` is already such a root property.

Configuration is the only way the app learns either value: there SHALL be no default URI, no default
key, and no fallback that guesses a key from a metadata object's contents. Naming a resource a server
does not serve, or a key its metadata does not carry, SHALL remain a delivery-time outcome rather
than a validation error — what a server serves is known only when it is read, and the
**report-citations** rule that a metadata failure costs a label continues to govern it.

#### Scenario: A document server configures both fields

- **WHEN** `ApplicationProperties.model_validate` receives a `generic_rag` server naming both a
  resource template and a title key
- **THEN** validation SHALL succeed, and both values SHALL be available to the app at the citation
  step

#### Scenario: A document server configuring neither is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `generic_rag` server that names a
  file-sharing tool and neither metadata field
- **THEN** validation SHALL fail with an error naming that server and saying that a document server
  must name both, because a document id is internal to the server and labels no source the reader
  can place

#### Scenario: One field without the other is rejected

- **WHEN** a server entry names a resource template but no title key, or a title key but no resource
  template
- **THEN** validation SHALL raise a pydantic `ValidationError` saying the two are set together or not
  at all

#### Scenario: A template with no placeholder is rejected

- **WHEN** a server entry's `document_metadata_resource` carries no `{document_ids}` placeholder
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the missing placeholder

#### Scenario: A dataset server setting either is rejected

- **WHEN** an MCP server entry of type `statgpt` sets `document_metadata_resource` or
  `document_title_key`
- **THEN** validation SHALL raise a pydantic `ValidationError` stating that only a document server
  may set them

#### Scenario: A channel serving no documents needs neither field

- **WHEN** a configuration carries a `statgpt` server and no `generic_rag` server
- **THEN** validation SHALL pass, and no document-metadata resource SHALL be configured

### Requirement: MCP server declares its list-datasets tool

`MCPClientSettings` SHALL expose one string field, `list_datasets_tool`, naming the tool this
server advertises for the app to call in order to list the channel's datasets. The app calls it
at the start of every turn, to show the models which datasets exist, and reads the same answer to
learn a cited dataset's name and the address of its page. The **report-citations** capability
owns what that tool must do, and **data-sources-discovery** owns how its answer reaches the models;
this field carries only its name, and the name is the only thing the app knows about the tool
before calling it.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. Datasets are what a dataset server
serves, and a `[dataset <id>]` marker names no server, so a second server answering about dataset
ids would make a citation ambiguous — the same reason `file_sharing_tool` belongs to the document
server alone. Since at most one server of each type may be configured, at most one configured server
names a list-datasets tool, and that is a consequence of the two rules rather than a third check.

**A `statgpt` server SHALL name it**, and a configuration where one does not SHALL be rejected
with a validation error naming that server. The rule is the `file_sharing_tool` rule, for the same
reason: a citation carries an identifier that means something only inside the server that issued
it, and the tool is the only thing that turns that identifier into a name and a page the reader can
open. Without it every dataset citation reaches the reader as a bare URN in square brackets, which
is a server that cannot be cited rather than a deployment choice.

The cost of this rule is paid at configuration rather than at delivery, and it is real: a channel
whose dataset server advertises no catalogue tool cannot be configured at all, and an existing
channel that has not set the field fails validation until it does — which the **application-config-schema**
rule on invalid properties delivers to the user as "application not configured". That is the
intended trade: a dataset server is in a deployment to have its data cited, and a citation the
reader cannot follow is not worth serving silently.

Configuration is the only way the app learns the name: there SHALL be no default value and no
fallback that guesses a tool from what the server advertises, so a server whose tool is called
something else is reached by editing this field rather than by changing code.

Naming a tool the server does not in fact advertise SHALL remain a delivery-time failure rather than
a validation error, for the reason the file-sharing tool's does: the advertised tool list is fetched
per turn, and the **report-citations** rule that no citation failure costs the report continues to
govern it.

`dial_conf/core/applications-template.json` SHALL set, on every server entry it carries, exactly
what that entry's `server_type` is required to set — so a dataset server entry there names a
list-datasets tool, and a contributor's seeded channel validates as it stands.

#### Scenario: A statgpt server names the tool

- **WHEN** a `statgpt` server entry sets `list_datasets_tool` to the name of a tool it advertises
- **THEN** validation SHALL pass, and the app SHALL call exactly that tool in the data-sources
  fetch at the start of every turn

#### Scenario: A generic_rag server naming it is rejected

- **WHEN** a `generic_rag` server entry sets `list_datasets_tool`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a list-datasets tool

#### Scenario: A statgpt server without the field is rejected

- **WHEN** a `statgpt` server entry sets no `list_datasets_tool`
- **THEN** validation SHALL fail with an error naming that server and saying that a dataset server
  must name the tool, because its datasets are cited by URN and nothing else turns a URN into a
  page the reader can open

#### Scenario: A channel serving no datasets needs no such tool

- **WHEN** a configuration carries a `generic_rag` server and no `statgpt` server
- **THEN** validation SHALL pass, no list-datasets tool SHALL be configured, and a dataset
  marker in a delivered report SHALL keep its text

#### Scenario: The committed template names what each server type requires

- **WHEN** `dial_conf/core/applications-template.json` carries a server entry
- **THEN** that entry SHALL set every field its `server_type` is required to set, so a channel
  seeded from the template validates without further editing

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

**Every server entry SHALL carry one**, whatever its `server_type`. Every supported server type
serves sources a report cites, so a server without a table is a server whose cited sources cannot be
listed — the same reason a `generic_rag` server must name its file-sharing tool and a `statgpt`
server its list-datasets tool. The report structure has no say in it: the References section is
built for every report a channel delivers.

**Requiring it is a breaking configuration change**: an instance whose server entries do not carry a
`references_table` fails validation, and its turns are delivered as "application not configured"
until its properties are edited.

The app SHALL NOT derive a column from anything else it is configured with. In particular the
document title key (`document_title_key`) and a table's first column are configured separately and
MAY name different keys: a pill's title is shortened to the channel's pill-title budget while a
row's cell is not, so a channel may want a short label on the pill and a fuller string in the row. A
channel that wants them to agree names the same key twice, deliberately.

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

#### Scenario: A table is required whatever the report structure says

- **WHEN** an instance configures a report structure of its own, naming only sections the report
  writer writes
- **THEN** its server entries SHALL still each be required to carry a `references_table`, since the
  References section is built for every report and the structure has no say in whether it is

#### Scenario: The title key and the first column are independent

- **WHEN** a `generic_rag` server names `document_title_key` as `publication_title` and a first
  column reading `document_name`
- **THEN** validation SHALL succeed, citation pills SHALL be labelled from `publication_title`, and
  the References rows' first column SHALL be filled from `document_name`

### Requirement: MCP server declares its data-query meta key

`MCPClientSettings` SHALL expose one string field, `data_query_meta_key`, naming the key under
which this server's tool results carry their data-query records in the MCP result's `_meta`. The
**report-citations** capability owns what the payload under that key must carry and what the app
does with it; this field carries only the key.

The key is configuration rather than a constant because a server builds it from a namespace that
belongs to one deployment's channel configuration — the MCP specification requires extension keys
in `_meta` to carry a reverse-DNS prefix, such as `acme.example.org/client` — so the same server
software emits a different key in each deployment. The app SHALL match the configured string
against a `_meta` key character for character, with no prefix or suffix matching and no
case-folding.

**The key is the only part of the data-query contract that is configured.** The shape under it and
the shape of the structured result — which fields carry the query id, the data explorer URL, the
dataset URN, the series count and the filter — are defined by the data-query server software and
are the same in every deployment, so **report-citations** states them as a contract and the app
pins them in code. There SHALL be no configuration field naming any of them. A configured field
name would protect only against a server renaming one field while changing nothing else, and would
let one channel's setting drift away from the server it describes.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. Data queries are what a dataset
server runs, and a `[data_query <id>]` marker names no server, so a second server reporting query
ids would make a citation ambiguous — the same reason `list_datasets_tool` belongs to the
dataset server alone.

**A `statgpt` server SHALL name it**, and a configuration where one does not SHALL be rejected with
a validation error naming that server. The report writer is told to cite every fact drawn from a
data query as `[data_query <id>]` (**research-execution**), and the key is the only thing that turns
such an id into a page the reader can open and into the dataset the References section lists. A
dataset server without it would deliver every data-query citation as a bare id in square brackets
and list none of the datasets those citations drew on.

The cost is the one `list_datasets_tool` pays, paid at configuration: an existing channel with a
`statgpt` server that has not set the field fails validation until it does, which the rule on
invalid properties delivers to the user as "application not configured".

There SHALL be no default value. A key that matches nothing a server sends SHALL remain a
delivery-time outcome rather than a validation error, because what a server puts in `_meta` is
known only once its tools have been called: every data-query citation then keeps its marker text,
and the citation step records it (see **logging-policy**).

`dial_conf/core/applications-template.json` SHALL keep setting exactly what each of its server
entries' types requires, which the list-datasets-tool requirement already states. The template
carries no `statgpt` server, so this field adds nothing to it.

#### Scenario: A statgpt server names its key

- **WHEN** a `statgpt` server entry sets `data_query_meta_key` to `acme.example.org/client`
- **THEN** validation SHALL pass, and the app SHALL read data-query records from that key and no
  other in the server's tool results

#### Scenario: A generic_rag server naming it is rejected

- **WHEN** a `generic_rag` server entry sets `data_query_meta_key`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a data-query meta key

#### Scenario: A statgpt server without the key is rejected

- **WHEN** a `statgpt` server entry sets `list_datasets_tool` and no `data_query_meta_key`
- **THEN** validation SHALL fail with an error naming that server and saying that a dataset server
  must name the key, because its data-query citations are resolved through it

#### Scenario: A channel serving no datasets needs no key

- **WHEN** a configuration carries a `generic_rag` server and no `statgpt` server
- **THEN** validation SHALL pass, and no data-query meta key SHALL be configured
