# application-config-schema Specification

## Purpose

The Deep Research schema-rich application type: per-instance configuration ("channels")
delivered as DIAL application properties. Covers the pydantic properties model, the DIAL
application-type JSON schema generated from it, the committed schema artifact with its lint
drift guard, the schema endpoint DIAL Core fetches from, per-request property resolution and
validation, and the friendly failure mode when a request arrives without a valid
configuration.

## Requirements

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
  - `description: str` — required, non-empty (`min_length=1`); everything the report writer and
    the review step need to know about this section's content. It is the **single home** for that
    section's rules: no other prompt, model, or spec SHALL carry per-section content
    instructions.
  - `protected: bool` — default `False`; whether user instructions may drop or restyle this
    section (see the **report-composition** capability's protected-sections requirement).
  - `references_section: bool` — default `False`; whether this section is the report's list of
    sources. It declares what the section *is*, not what the app does with it: the consequence —
    that its words do not count toward `max_report_words` — is defined by the **report-composition**
    capability's ceiling requirement, and in every other respect the section behaves like any other.

  The default value SHALL be the five sections Overview, Key Findings, Detailed Analysis,
  Conclusion, and References, each with its description. Overview and References SHALL default to
  `protected: true`, References SHALL default to `references_section: true`, and the References
  description SHALL carry the entry format for every source type a report may cite — publications
  and datasets alike — including what each entry decodes and the columns it carries.

  The list SHALL be constrained to contain at least one section with `protected: true`, so no
  configuration can produce a report whose every section a user instruction may remove. **Only the
  last section MAY set `references_section: true`**, since a report lists its sources at the end; a
  structure MAY set it on no section at all, and then nothing is exempt from the word count.
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
  `references_section: true` and the source-table rules in its description, `max_report_words`
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
- **THEN** validation SHALL succeed, and nothing SHALL be exempt from the word count

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

### Requirement: DIAL application-type schema generation

The properties model SHALL generate a JSON schema conforming to the DIAL application-type
meta-schema (`https://dial.epam.com/application_type_schemas/schema#`). Generation SHALL:

- resolve root-property `$ref`s so each root property carries its own inline schema;
- inject a `dial:meta` object into every root property with `"dial:propertyKind": "server"`
  and a sequential `"dial:propertyOrder"` following field declaration order;
- support an `include_dial_fields` toggle: when enabled, the schema root SHALL additionally
  carry `$schema` (the DIAL meta-schema URI), `$id` (a generic placeholder ending in
  `/custom_application_schemas/deep-research`),
  `"dial:applicationTypeDisplayName": "Deep Research"`, and
  `"dial:appendApplicationPropertiesHeader": false`; when disabled, none of these root
  keywords SHALL be present (DIAL Core supplies them from its `applicationTypeSchemas` entry).

#### Scenario: Root properties carry dial:meta

- **WHEN** the schema is generated
- **THEN** every root property SHALL contain a `dial:meta` object with `dial:propertyKind` equal
  to `"server"` and a unique `dial:propertyOrder` integer

#### Scenario: A list-of-models property is inlined

- **WHEN** the schema is generated for `default_report_structure`, a list of nested
  `ReportSection` models
- **THEN** its `items` schema SHALL carry the `ReportSection` fields inline, with no `$ref` left
  anywhere in the generated schema

#### Scenario: Wrapper keywords only with include_dial_fields

- **WHEN** the schema is generated with `include_dial_fields` disabled
- **THEN** the schema root SHALL NOT contain `$id`, `$schema`, or any `dial:applicationType*`
  keyword, while the per-property `dial:meta` blocks SHALL still be present

### Requirement: Committed schema artifact guarded against drift

The repository SHALL commit the generated application-type schema (with the DIAL root
wrapper) at `docs/generated-app-schema.json`, regenerated by a script
(`scripts/dump_app_schema.py`). The lint gate SHALL run the script in check mode and fail
when the committed artifact differs from freshly generated output.

#### Scenario: Model change without regeneration fails lint

- **WHEN** a field is added to the properties model and `docs/generated-app-schema.json` is
  not regenerated
- **THEN** `make lint` SHALL fail, naming the schema drift

#### Scenario: Regeneration restores lint

- **WHEN** the dump script is run after a model change and the artifact is committed
- **THEN** `make lint` SHALL pass the schema check

### Requirement: Application schema endpoint

The app SHALL expose `GET /v1/configuration-support/application-schema` returning the
generated property schema without the DIAL root wrapper (`include_dial_fields` disabled),
with HTTP 200 and a JSON body. This is the endpoint DIAL Core (>= 0.41.0) references via
`dial:applicationTypeSchemaEndpoint`.

#### Scenario: Schema served to Core

- **WHEN** a client issues `GET /v1/configuration-support/application-schema`
- **THEN** the app SHALL respond with HTTP 200 and the JSON property schema, whose root
  contains the `max_research_iterations` and `prompts` properties with their `dial:meta`
  blocks and no `$id`/`$schema`/`dial:applicationType*` root keywords

### Requirement: Per-request application properties resolution

Each chat completion turn SHALL obtain its configuration by resolving the request's DIAL
application properties through the aidial-sdk
(`request.request_dial_application_properties()`) and validating the result into the
properties model. The application type SHALL declare
`dial:appendApplicationPropertiesHeader: false`, so in production Core sends
`X-DIAL-APPLICATION-ID` and the SDK fetches the instance's `applicationProperties` from Core
via REST; an explicit `X-DIAL-APPLICATION-PROPERTIES` header, when present, SHALL be honored
by the same SDK call (used by tests to inject properties without a Core round-trip). The
validated properties SHALL be passed as parameters into the preparation and research runs —
no module-level properties singleton SHALL exist.

#### Scenario: Instance properties reach the agent

- **WHEN** DIAL Core routes a chat completion for an application instance whose
  `applicationProperties` set `prompts.agent_name` to `"ACME Deep Research"`
- **THEN** the preparation agent's system prompt for that turn SHALL contain
  `"ACME Deep Research"`, and a concurrent request for a different instance SHALL see only its
  own properties

#### Scenario: Properties injected via header

- **WHEN** a request carries a well-formed `X-DIAL-APPLICATION-PROPERTIES` header
- **THEN** the turn SHALL use those properties without any REST fetch to Core

### Requirement: Missing or invalid application properties fail the turn with a friendly error

The turn SHALL fail with a friendly configuration error whenever application properties
cannot be resolved (no application id and no header, Core fetch failure) or fail validation
against the properties model: the cause SHALL be logged server-side and the response SHALL
be a friendly assistant message explaining the app is not configured, completing
successfully (HTTP 200) from DIAL's perspective, consistent with the existing top-level
error funnel. The turn SHALL NOT run with default or partial prompt content.

#### Scenario: Bare deployment call without an instance

- **WHEN** a client calls the `deep-research` deployment directly with no application
  identity and no properties header
- **THEN** the response SHALL be a friendly configuration error message (HTTP 200), no
  preparation or research agent SHALL run, and the failure SHALL be logged server-side

#### Scenario: Invalid stored properties

- **WHEN** Core returns `applicationProperties` that fail model validation (e.g. an empty
  `prompts.client_name`)
- **THEN** the turn SHALL respond with the friendly configuration error message and log the
  validation error server-side

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
therefore the honest statement of what this application works with; the open contract is the
file-sharing tool below, whose **name** any server may choose.

`ApplicationProperties` SHALL reject a configuration carrying **more than one** server of the same
type, with a validation error naming the type and the offending servers. Each server numbers its
own content, and a citation carries that number without saying which server issued it, so two
servers of one type make an id ambiguous with nothing in the marker, the retrieval result or the
protocol able to tell them apart. This holds for dataset servers as well as document ones: dataset
citations are not converted into anything today, but nothing stops two dataset servers from
shipping the same dataset id, so the rule is one rule rather than one per type. Supporting several
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
- **THEN** validation SHALL raise, even though no dataset citation is converted today

#### Scenario: The generated schema carries the type as an enumeration

- **WHEN** the DIAL application-type schema is generated from `ApplicationProperties`
- **THEN** the MCP server entry SHALL carry `server_type` as a required string enumeration of the
  supported values, inlined rather than referenced through `$defs`, and the committed schema
  artifact SHALL be regenerated to match

### Requirement: MCP server declares its file-sharing tool

`MCPClientSettings` SHALL expose one string field, `file_sharing_tool`, naming the tool
this server advertises for the app to call in order to make cited documents readable by the person
reading the report. The **report-citations** capability owns what that tool must do; this field
carries only its name, and the name is the only thing the app knows about the tool before calling
it.

**A `generic_rag` server SHALL name one**, and a configuration where it does not SHALL be
rejected. That server serves the documents a report cites by id and page, and such a citation is
only useful when the reader can open the cited page, which needs the copy this tool makes in the
reader's own storage; a document server without it delivers every document citation as plain text,
which is a broken server rather than a configuration choice. A `statgpt` server MAY leave the field
unset, having datasets to cite and no files to share.

Two consequences follow from the field being required on a document server, and both are
deliberate. Inline citation conversion is **not** switchable per instance any more: every
deployment configured with a document server converts its citations, so an instance whose reader
cannot render the marker tags — a DIAL Chat build without the `cit` rendering, or a relay that drops
`custom_content.annotations` — cannot be returned to plain markers by editing configuration, and
turning conversion off for it requires a code change. And a validation failure fails the turn (see
the properties-loading requirement), so a channel that has not added the field serves no requests
at all rather than serving reports without pills.

Configuration is the only way the app learns the name: there SHALL be no default value and no
fallback that guesses a tool from what the server advertises, so a server whose tool is called
something else is reached by editing this field rather than by changing code. Requiring the field
on a document server is therefore a requirement to **name** the tool, not a requirement that the
app know which tool it is.

Naming a tool the server does not in fact advertise SHALL remain a delivery-time failure rather
than a validation error: the advertised tool list is fetched per turn, and the
**report-citations** capability's rule that no citation failure costs the report continues to
govern it.

The field SHALL be a plain string field on `MCPClientSettings` rather than a nested model. The
DIAL application-type schema inlines each root property's model and rejects a model nested below
that (see the schema-generation requirement), and `mcp_servers` is already such a root property, so
a nested settings object under it could not be rendered as configuration. Further citation-related
contracts SHALL therefore be added as sibling string fields rather than as a nested group.

**No other server type may name one.** A `statgpt` server SHALL be rejected for setting the field:
a dataset citation has no file to open, so a tool named there would never be called; and were that
server to serve documents as well, their ids would collide with the document server's, which is the
ambiguity the one-server-per-type rule refuses.

Those two halves — a document server must name one, no other type may — together with at most one
server per type make **"at most one configured server names a file-sharing tool"** a consequence
rather than a rule of its own. There SHALL be no separate cross-server check for it: a document
citation carries an id and no server name, so two servers issuing ids could not be told apart, and
the configuration that would do so is already refused by the two rules above.

Naming the tool SHALL NOT add it to what the research agent may call, and SHALL NOT require it to
appear in that server's `tools_to_include` (see **report-citations** and **dial-agent-with-mcp**).

#### Scenario: A server configures its file-sharing tool

- **WHEN** `ApplicationProperties.model_validate` receives one MCP server that names a
  file-sharing tool
- **THEN** validation SHALL succeed and that name SHALL be available to the app as the tool to
  call at the citation step

#### Scenario: A document server naming no tool is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `generic_rag` server with no
  `file_sharing_tool`
- **THEN** validation SHALL raise a pydantic `ValidationError` saying that a document server must
  name one

#### Scenario: A dataset-only configuration names no tool

- **WHEN** `ApplicationProperties.model_validate` receives one `statgpt` server and no
  `generic_rag` server, with no `file_sharing_tool` anywhere
- **THEN** validation SHALL succeed, and reports SHALL be delivered with their citation markers
  as written

#### Scenario: An unreachable server is reported before its missing tool

- **WHEN** a `generic_rag` server entry sets neither `deployment_id` nor `connection` and names no
  file-sharing tool
- **THEN** the error SHALL be the missing connection mode, since a server that cannot be reached at
  all is the more fundamental misconfiguration

#### Scenario: A dataset server naming one is rejected

- **WHEN** an MCP server entry of type `statgpt` sets `file_sharing_tool`
- **THEN** validation SHALL raise a pydantic `ValidationError` stating that only a document server
  may set it

#### Scenario: No configuration can name two file-sharing tools

- **WHEN** `ApplicationProperties.model_validate` receives two MCP servers that each name a
  file-sharing tool
- **THEN** validation SHALL raise, whichever of the two rules the configuration breaks first

#### Scenario: The generated schema carries the field

- **WHEN** the DIAL application-type schema is generated from `ApplicationProperties`
- **THEN** the MCP server entry SHALL carry the file-sharing tool field with its description, and
  the committed schema artifact SHALL be regenerated to match
