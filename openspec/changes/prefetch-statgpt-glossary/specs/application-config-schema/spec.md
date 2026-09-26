## ADDED Requirements

### Requirement: A statgpt MCP server may declare its glossary tools

`MCPClientSettings` SHALL expose one optional field, `glossary`, with no default value. When set,
it SHALL be a nested object with three required fields, and it SHALL reject unknown fields, so a
misspelled field fails validation instead of being ignored:

- `list_terms_tool: str`, non-empty: the name of the server's tool that lists the glossary's
  terms.
- `definitions_tool: str`, non-empty: the name of the server's tool that returns the definitions
  of named terms.
- `max_terms_per_definitions_call: int`, constrained `ge=1`: the largest number of terms one call
  of the definitions tool may request.

The limit SHALL be configured rather than discovered, because the server states it only as prose in
the tool's argument description, and a request over it fails whole. The **glossary-prefetch**
capability owns how the app uses the three values.

**Only a `statgpt` server may set it**, and a configuration where any other server type does SHALL
be rejected with a validation error naming the offending server. The glossary is served by the
dataset server. Since at most one server of each type may be configured, at most one configured
server names a glossary, which follows from the two rules rather than needing a third check.

A `statgpt` server is **not** required to set it: a channel whose server exposes no glossary is a
valid channel.

Naming a tool the server does not advertise SHALL NOT be a validation error, because the advertised
tool list is only known at request time. It SHALL surface as failed glossary calls, which
**glossary-prefetch** turns into the failure text without failing the turn.

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

- **WHEN** a `glossary` object omits `max_terms_per_definitions_call`, or sets it to 0
- **THEN** validation SHALL fail with an error identifying that field

#### Scenario: A statgpt server without a glossary is valid

- **WHEN** a `statgpt` server entry sets no `glossary`
- **THEN** validation SHALL pass, and no glossary call SHALL be made for that channel
