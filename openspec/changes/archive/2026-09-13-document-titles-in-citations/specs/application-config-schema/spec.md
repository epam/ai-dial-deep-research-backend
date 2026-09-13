## ADDED Requirements

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

**Both fields are optional, and they SHALL be set together or not at all.** A configuration setting
one without the other SHALL be rejected — a URI with no key names nothing to take, and a key with no
URI has nothing to take it from. Leaving both unset SHALL be valid on any server type.

They are optional where `file_sharing_tool` is required on a document server, and the difference is
deliberate. A document server without a file-sharing tool loses every pill, which is a broken server;
a document server without a title resolves plainer labels, which costs the reader a publication name
and nothing else. A channel whose metadata schema genuinely carries no title has nothing to name, and
must still be configurable.

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

#### Scenario: A document server configuring neither is valid

- **WHEN** `ApplicationProperties.model_validate` receives a `generic_rag` server that names a
  file-sharing tool and neither metadata field
- **THEN** validation SHALL succeed, and that instance's citations SHALL be labelled from their
  markers

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

### Requirement: The citation pill's title budget is per channel

`ApplicationProperties` SHALL expose a nullable integer field, `max_pill_title_chars`, saying how
much of a cited document's title the inline citation pill shows, the ellipsis counted within it. It
SHALL carry a default, so a channel that names nothing still gets pills that fit, and SHALL have a
floor below which a shortened title conveys nothing.

It is a **channel** setting rather than a server one: what fits on a pill depends on the client the
channel's readers use, not on which server the document came from. **report-citations** owns what
the app does with it — the popup card keeps the whole title whatever this says, and the cited page
is appended after the shortening.

**Null SHALL mean no shortening**, showing every title whole — for a client with the room, or one
that shortens labels itself. That is the supported way to switch it off, and there SHALL be no
separate flag for it.

#### Scenario: A channel narrows the pill label

- **WHEN** a channel sets `max_pill_title_chars` below the default and a report cites a document
  whose title is longer than that
- **THEN** the pill's label SHALL be shortened to that budget, and the citation card's SHALL still
  carry the whole title

#### Scenario: A channel naming nothing gets the default

- **WHEN** `ApplicationProperties.model_validate` receives properties with no `max_pill_title_chars`
- **THEN** validation SHALL succeed and the field SHALL hold the code's default

#### Scenario: A channel switches shortening off

- **WHEN** a channel sets `max_pill_title_chars` to null
- **THEN** validation SHALL succeed, and every pill SHALL carry its title whole

#### Scenario: A budget too small to be useful is rejected

- **WHEN** a channel sets `max_pill_title_chars` to a number below the floor
- **THEN** validation SHALL raise a pydantic `ValidationError`
