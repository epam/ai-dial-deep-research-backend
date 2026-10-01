## RENAMED Requirements

- FROM: `### Requirement: MCP server declares its data-query meta key`
- TO: `### Requirement: MCP server declares its client meta key`

## MODIFIED Requirements

### Requirement: MCP server declares its client meta key

`MCPClientSettings` SHALL expose one string field, `client_meta_key`, naming the key under which
this server's tool results carry their client payload in the MCP result's `_meta`. Two tools of
the dataset server carry a payload under it: a data-query tool carries its data-query records, and
the list-datasets tool carries each dataset's data explorer link. The **report-citations**
capability owns what each payload must carry and what the app does with it; this field carries only
the key.

The key is configuration rather than a constant because a server builds it from a namespace that
belongs to one deployment's channel configuration — the MCP specification requires extension keys
in `_meta` to carry a reverse-DNS prefix, such as `acme.example.org/client` — so the same server
software emits a different key in each deployment. The app SHALL match the configured string
against a `_meta` key character for character, with no prefix or suffix matching and no
case-folding. **One key serves both tools**, so the dataset server's channel SHALL configure the
same namespace on its data-query tool and on its list-datasets tool. A list-datasets tool whose
namespace differs costs only the explorer links of dataset citations, which then open each
dataset's page.

**The key is the only part of either payload's contract that is configured.** The shapes under it
and the shape of the structured results — which fields carry the query id, the data explorer URLs,
the dataset URN, the series count and the filter — are defined by the dataset server software and
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
invalid properties delivers to the user as "application not configured". The field has no other
name, and a server entry ignores fields it does not define, so a `statgpt` server that still sets
`data_query_meta_key` and not `client_meta_key` SHALL fail validation for naming no client meta key.

There SHALL be no default value. A key that matches nothing a server sends SHALL remain a
delivery-time outcome rather than a validation error, because what a server puts in `_meta` is
known only once its tools have been called: every data-query citation then keeps its marker text,
every dataset citation opens its dataset's page, and the citation step records the data-query
outcome (see **logging-policy**).

`dial_conf/core/applications-template.json` SHALL keep setting exactly what each of its server
entries' types requires, which the list-datasets-tool requirement already states. The template
carries no `statgpt` server, so this field adds nothing to it.

#### Scenario: A statgpt server names its key

- **WHEN** a `statgpt` server entry sets `client_meta_key` to `acme.example.org/client`
- **THEN** validation SHALL pass, and the app SHALL read data-query records and dataset explorer
  links from that key and no other in the server's tool results

#### Scenario: A generic_rag server naming it is rejected

- **WHEN** a `generic_rag` server entry sets `client_meta_key`
- **THEN** validation SHALL fail with an error naming that server and stating that only a `statgpt`
  server may name a client meta key

#### Scenario: A statgpt server without the key is rejected

- **WHEN** a `statgpt` server entry sets `list_datasets_tool` and no `client_meta_key`
- **THEN** validation SHALL fail with an error naming that server and saying that a dataset server
  must name the key, because its data-query citations are resolved through it

#### Scenario: The old field name is rejected

- **WHEN** a `statgpt` server entry sets `data_query_meta_key` to `acme.example.org/client` and no
  `client_meta_key`
- **THEN** validation SHALL fail with the error a `statgpt` server without the key gets

#### Scenario: A channel serving no datasets needs no key

- **WHEN** a configuration carries a `generic_rag` server and no `statgpt` server
- **THEN** validation SHALL pass, and no client meta key SHALL be configured
