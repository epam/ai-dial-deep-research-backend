## ADDED Requirements

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
