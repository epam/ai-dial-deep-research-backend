## ADDED Requirements

### Requirement: MCP server declares its file-sharing tool

`MCPClientSettings` SHALL expose one optional string field, `file_sharing_tool`, naming the tool
this server advertises for the app to call in order to make cited documents readable by the person
reading the report. The **report-citations** capability owns what that tool must do; this field
carries only its name, and the name is the only thing the app knows about the tool before calling
it. The field SHALL default to unset, and unset SHALL mean this server's documents produce no
inline citation annotations.

Configuration is the only way the app learns the name: there SHALL be no default value and no
fallback that guesses a tool from what the server advertises, so a server whose tool is called
something else is reached by editing this field rather than by changing code.

The field SHALL be a plain string field on `MCPClientSettings` rather than a nested model. The
DIAL application-type schema inlines each root property's model and rejects a model nested below
that (see the schema-generation requirement), and `mcp_servers` is already such a root property, so
a nested settings object under it could not be rendered as configuration. Further citation-related
contracts SHALL therefore be added as sibling string fields rather than as a nested group.

`ApplicationProperties` SHALL reject a configuration in which **more than one** server names a
file-sharing tool, with a validation error naming the offending servers. A document citation in a
report carries a document id and no server name, so ids coming from two servers could not be told
apart.

Naming the tool SHALL NOT add it to what the research agent may call, and SHALL NOT require it to
appear in that server's `tools_to_include` (see **report-citations** and **dial-agent-with-mcp**).

#### Scenario: A server configures its file-sharing tool

- **WHEN** `ApplicationProperties.model_validate` receives one MCP server that names a
  file-sharing tool
- **THEN** validation SHALL succeed and that name SHALL be available to the app as the tool to
  call at the citation step

#### Scenario: No server configures one

- **WHEN** `ApplicationProperties.model_validate` receives MCP servers none of which names a
  file-sharing tool
- **THEN** validation SHALL succeed, and reports SHALL be delivered with their citation markers
  as written

#### Scenario: Two servers naming one is rejected

- **WHEN** `ApplicationProperties.model_validate` receives two MCP servers that each name a
  file-sharing tool
- **THEN** validation SHALL raise a pydantic `ValidationError` stating that at most one server may
  name one, and naming the servers that did

#### Scenario: The generated schema carries the field

- **WHEN** the DIAL application-type schema is generated from `ApplicationProperties`
- **THEN** the MCP server entry SHALL carry the file-sharing tool field with its description, and
  the committed schema artifact SHALL be regenerated to match
