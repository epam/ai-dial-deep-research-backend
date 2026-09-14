## ADDED Requirements

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

**The field is optional**, and this is where it departs from `file_sharing_tool`, which a
`generic_rag` server must name. The two are asymmetric because what they are worth to a deployment
is asymmetric. A document server exists in this application to serve documents that get cited by id
and page, and without file sharing every one of those citations is delivered as text, which is a
broken server rather than a choice. A dataset server earns its place by answering research questions
through its data-query tool, and a channel may expose no catalogue tool at all; rejecting such a
configuration would refuse a working research deployment in order to protect a label. An instance
that names no dataset-metadata tool delivers every dataset marker as text and is a supported,
ordinary deployment — which is why that case is recorded at DEBUG rather than warned about on every
turn (see **logging-policy**).

Configuration is the only way the app learns the name: there SHALL be no default value and no
fallback that guesses a tool from what the server advertises, so a server whose tool is called
something else is reached by editing this field rather than by changing code.

Naming a tool the server does not in fact advertise SHALL remain a delivery-time failure rather than
a validation error, for the reason the file-sharing tool's does: the advertised tool list is fetched
per turn, and the **report-citations** rule that no citation failure costs the report continues to
govern it.

Because the field is optional, `dial_conf/core/applications-template.json` SHALL NOT carry it: that
template sets exactly the properties a channel is required to set, and a value copied into it would
pin every seeded channel to whatever tool name was current when it was seeded.

#### Scenario: A statgpt server names the tool

- **WHEN** a `statgpt` server entry sets `dataset_metadata_tool` to the name of a tool it advertises
- **THEN** validation SHALL pass and the app SHALL call exactly that tool at the citation step

#### Scenario: A generic_rag server naming it is rejected

- **WHEN** a `generic_rag` server entry sets `dataset_metadata_tool`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a dataset-metadata tool

#### Scenario: A statgpt server without the field is valid

- **WHEN** a `statgpt` server entry sets no `dataset_metadata_tool`
- **THEN** validation SHALL pass, and every dataset citation in every report SHALL be delivered as
  the marker text the report writer wrote

#### Scenario: The committed template stays free of the field

- **WHEN** the application-properties model gains this field
- **THEN** `dial_conf/core/applications-template.json` SHALL remain unchanged, the field being
  optional

## MODIFIED Requirements

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
- **THEN** validation SHALL raise, even though no dataset citation is converted today

#### Scenario: The generated schema carries the type as an enumeration

- **WHEN** the DIAL application-type schema is generated from `ApplicationProperties`
- **THEN** the MCP server entry SHALL carry `server_type` as a required string enumeration of the
  supported values, inlined rather than referenced through `$defs`, and the committed schema
  artifact SHALL be regenerated to match

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
