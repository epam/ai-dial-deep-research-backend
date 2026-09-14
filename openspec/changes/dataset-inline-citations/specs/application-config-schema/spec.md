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
