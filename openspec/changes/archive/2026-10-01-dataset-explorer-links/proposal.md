## Why

A dataset citation opens the dataset's portal page, while a data-query citation opens the data
explorer. Readers should land in the data explorer from every data citation. The StatGPT
list-datasets tool now reports each dataset's data explorer link in the tool result's `_meta`,
under the same `<namespace>/client` key the data-query tool uses, so the app can open the explorer
without building any URL itself.

## What Changes

- A `[dataset <urn>]` pill, and the first cell of a dataset's References row, open the dataset in
  the data explorer: the `dataExplorerUrl` the list-datasets tool reports for that URN in its
  `_meta` payload. When the payload carries no usable explorer link for a dataset, the citation
  opens the catalogue's `url` (the dataset's page), as before. This covers the dataset row a cited
  data query adds to the References section, because that row is a dataset row.
- The `_meta` payload is read wherever the catalogue is read: by the data-sources fetch at the
  start of the turn, and by the fallback call the report review or the delivery makes when that
  fetch failed. The fallback call reads the raw MCP result instead of going through the LangChain
  tool, which drops `_meta`.
- **BREAKING**: the server property `data_query_meta_key` is renamed `client_meta_key`, because
  the same key now carries the payload of two tools. A channel configuration that still sets the
  old name fails validation until it is edited.
- A tool result whose `_meta` payload under the key carries no `queries` array (a list-datasets
  result) contributes no data-query records and no longer counts as an unreadable data-query
  payload.
- Data-query pills are unchanged: they keep opening the explorer filtered on the cited query.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `report-citations`: the dataset pill's URL comes from the list-datasets tool's `_meta` explorer
  link first and from the record's `url` second; the list-datasets contract gains the optional
  `_meta` payload; the fallback catalogue call reads the raw MCP result; a `_meta` payload without
  `queries` is not a data-query payload.
- `application-config-schema`: `data_query_meta_key` becomes `client_meta_key`, the key of the
  payload both the data-query tool and the list-datasets tool carry.
- `data-sources-discovery`: the turn-start list call also reads the result's `_meta` payload, so
  the catalogue it seeds carries the explorer links.
- `logging-policy`: the "nothing captured" warning names the renamed field.

## Impact

- Code: `app_properties.py` (field rename and validator), `app/mcp_tools.py`,
  `app/data_source_calls.py`, `app/data_sources.py`, `app/glossary.py`,
  `app/research/dataset_metadata.py`, `app/research/citation_lookups.py`,
  `app/research/data_queries.py`, `app/research/runner.py`, and their tests.
- Docs: `README.md` core-config snippets, `docs/architecture.md`, and the regenerated
  `docs/generated-app-schema.json`.
- Configuration: every channel's application properties that set `data_query_meta_key` must rename
  it, including the configurations kept outside this repository and the local
  `dial_conf/core/applications.json`.
- The dataset server's channel must enable the `mcpMeta.client` payload on its list-datasets tool;
  without it the dataset pills keep opening the portal page.
