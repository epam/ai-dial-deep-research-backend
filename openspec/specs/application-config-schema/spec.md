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
therefore the honest statement of what this application works with; the open contracts are the
file-sharing tool and the dataset-metadata tool below, whose **names** any server may choose.

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
the same reason it is the `dataset_metadata_tool` rule: a document citation carries an integer id
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

### Requirement: MCP server declares its dataset-metadata tool

`MCPClientSettings` SHALL expose one string field, `dataset_metadata_tool`, naming the tool this
server advertises for the app to call in order to learn a cited dataset's name and the address of
its page. The **report-citations** capability owns what that tool must do; this field carries only
its name, and the name is the only thing the app knows about the tool before calling it.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. Datasets are what a dataset server
serves, and a `[dataset <id>]` marker names no server, so a second server answering about dataset
ids would make a citation ambiguous — the same reason `file_sharing_tool` belongs to the document
server alone. Since at most one server of each type may be configured, at most one configured server
names a dataset-metadata tool, and that is a consequence of the two rules rather than a third check.

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
dataset-metadata tool, and a contributor's seeded channel validates as it stands.

#### Scenario: A statgpt server names the tool

- **WHEN** a `statgpt` server entry sets `dataset_metadata_tool` to the name of a tool it advertises
- **THEN** validation SHALL pass and the app SHALL call exactly that tool at the citation step

#### Scenario: A generic_rag server naming it is rejected

- **WHEN** a `generic_rag` server entry sets `dataset_metadata_tool`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a dataset-metadata tool

#### Scenario: A statgpt server without the field is rejected

- **WHEN** a `statgpt` server entry sets no `dataset_metadata_tool`
- **THEN** validation SHALL fail with an error naming that server and saying that a dataset server
  must name the tool, because its datasets are cited by URN and nothing else turns a URN into a
  page the reader can open

#### Scenario: A channel serving no datasets needs no such tool

- **WHEN** a configuration carries a `generic_rag` server and no `statgpt` server
- **THEN** validation SHALL pass, no dataset-metadata tool SHALL be configured, and a dataset
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
server its dataset-metadata tool. The report structure has no say in it: the References section is
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

### Requirement: The citation pill's title budget is per channel

`ApplicationProperties` SHALL expose a nullable integer field, `max_pill_title_chars`, saying how
much of a citation's **leading part** the inline citation pill shows, the ellipsis counted within it.
It SHALL carry a default, so a channel that names nothing still gets pills that fit, and SHALL have a
floor below which a shortened label conveys nothing.

The budget governs the leading part of every pill label, whatever kind of source it names: a cited
document's publication title, and a cited dataset's name — or its URN, where no name resolved. It
does **not** govern the whole label. The field keeps the name `max_pill_title_chars` although it now
covers more than a title, because renaming a channel property breaks every configuration that sets
it, and the cost of the slightly narrow name is smaller than the cost of that break.

It is a **channel** setting rather than a server one: what fits on a pill depends on the client the
channel's readers use, not on which server the source came from. **report-citations** owns what the
app does with it — the popup card keeps the whole leading part whatever this says, and each kind of
citation's fixed trailing part, a document's cited page or a dataset's `dataset`, is appended after
the shortening so it is never lost to a long leading part.

**Null SHALL mean no shortening**, showing every title whole — for a client with the room, or one
that shortens labels itself. That is the supported way to switch it off, and there SHALL be no
separate flag for it.

#### Scenario: A channel narrows the pill label

- **WHEN** a channel sets `max_pill_title_chars` below the default and a report cites a document
  whose title is longer than that
- **THEN** the pill's label SHALL be shortened to that budget, and the citation card's SHALL still
  carry the whole title

#### Scenario: The budget applies to a dataset's name and to its URN

- **WHEN** a channel sets `max_pill_title_chars` and a report cites a dataset whose name is longer
  than that, and another whose name did not resolve and whose URN is longer than that
- **THEN** both pills SHALL carry their leading part shortened to that budget with `dataset` appended
  after the shortening, and both cards SHALL carry their leading part whole

#### Scenario: A channel naming nothing gets the default

- **WHEN** `ApplicationProperties.model_validate` receives properties with no `max_pill_title_chars`
- **THEN** validation SHALL succeed and the field SHALL hold the code's default

#### Scenario: A channel switches shortening off

- **WHEN** a channel sets `max_pill_title_chars` to null
- **THEN** validation SHALL succeed, and every pill SHALL carry its leading part whole, a dataset's
  name or URN as well as a document's title

#### Scenario: A budget too small to be useful is rejected

- **WHEN** a channel sets `max_pill_title_chars` to a number below the floor
- **THEN** validation SHALL raise a pydantic `ValidationError`
