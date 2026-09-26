## ADDED Requirements

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
ids would make a citation ambiguous — the same reason `dataset_metadata_tool` belongs to the
dataset server alone.

**A `statgpt` server SHALL name it**, and a configuration where one does not SHALL be rejected with
a validation error naming that server. The report writer is told to cite every fact drawn from a
data query as `[data_query <id>]` (**research-execution**), and the key is the only thing that turns
such an id into a page the reader can open and into the dataset the References section lists. A
dataset server without it would deliver every data-query citation as a bare id in square brackets
and list none of the datasets those citations drew on.

The cost is the one `dataset_metadata_tool` pays, paid at configuration: an existing channel with a
`statgpt` server that has not set the field fails validation until it does, which the rule on
invalid properties delivers to the user as "application not configured".

There SHALL be no default value. A key that matches nothing a server sends SHALL remain a
delivery-time outcome rather than a validation error, because what a server puts in `_meta` is
known only once its tools have been called: every data-query citation then keeps its marker text,
and the citation step records it (see **logging-policy**).

`dial_conf/core/applications-template.json` SHALL keep setting exactly what each of its server
entries' types requires, which the dataset-metadata-tool requirement already states. The template
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

- **WHEN** a `statgpt` server entry sets `dataset_metadata_tool` and no `data_query_meta_key`
- **THEN** validation SHALL fail with an error naming that server and saying that a dataset server
  must name the key, because its data-query citations are resolved through it

#### Scenario: A channel serving no datasets needs no key

- **WHEN** a configuration carries a `generic_rag` server and no `statgpt` server
- **THEN** validation SHALL pass, and no data-query meta key SHALL be configured

### Requirement: The data-query card's filter-line budget is per channel

`ApplicationProperties` SHALL expose an integer field, `data_query_card_filter_max_line_chars`,
saying how long one filter item on a data-query citation's card may be, the ellipsis counted within
it. **report-citations** owns what a filter item is and how it is cut.

**The field SHALL default to `80`**, which fits a filter on a few values whole and cuts a filter on
dozens of values to a line a reader can take in. It SHALL NOT be nullable: a filter on 35 countries
always needs a cut, so a setting that switched cutting off would only produce a card no client has
room for. The field SHALL have a floor of `10`, below which a cut item conveys nothing.

It is a **channel** setting rather than a server one, for the reason the pill budget is: what fits
on a card depends on the client the channel's readers use, not on which server reported the query.
It has a default, so `dial_conf/core/applications-template.json` SHALL NOT set it.

#### Scenario: A channel naming nothing gets 80-character items

- **WHEN** `ApplicationProperties.model_validate` receives properties with no
  `data_query_card_filter_max_line_chars`
- **THEN** validation SHALL succeed, and the field SHALL be `80`

#### Scenario: A channel sets its own budget

- **WHEN** a channel sets `data_query_card_filter_max_line_chars` to `120`
- **THEN** validation SHALL succeed, and every filter item longer than 120 characters SHALL be cut to
  120

#### Scenario: A budget below the floor, or null, is rejected

- **WHEN** a channel sets `data_query_card_filter_max_line_chars` to `5`, or to null
- **THEN** validation SHALL raise a pydantic `ValidationError`
