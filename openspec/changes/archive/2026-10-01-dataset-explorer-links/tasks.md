## 1. Configuration

- [x] 1.1 Rename `MCPClientSettings.data_query_meta_key` to `client_meta_key`, with its description, its validator and the `ApplicationProperties` accessor; update every caller (`mcp_tools.py`, `runner.py`, `data_queries.py`)
- [x] 1.2 Update the tests that set the field, and add a test that an entry setting only the old name fails with the missing-key error
- [x] 1.3 Regenerate `docs/generated-app-schema.json` and update the README core-config snippets

## 2. Reading the explorer links

- [x] 2.1 Make `parse_catalogue` take the `_meta` payload and resolve `DatasetSource.url` to the usable `dataExplorerUrl`, falling back to the record's `url`; read the payload leniently, element by element
- [x] 2.2 Pass the whole `CallToolResult` to the `call_once` reader, with an adapter for the structure and glossary readers
- [x] 2.3 Read the payload under the server's `client_meta_key` in the data-sources list reader, keeping the datasets section unchanged
- [x] 2.4 Replace the LangChain-tool fallback in `read_catalogue` with a raw MCP session call, and give `CitationLookups` the server name, tool name and key instead of a `BaseTool`
- [x] 2.5 Make `DataQueryCapture` skip a payload that has no `queries` field without counting it as unreadable

## 3. Tests

- [x] 3.1 Unit tests for the URL rule: explorer link wins, missing or non-web link falls back to `url`, link alone makes a dataset citable, unreadable payload costs only the links
- [x] 3.2 Data-sources fetch test: links reach the catalogue, not the datasets section, and a result without a payload is not retried
- [x] 3.3 Fallback-call test: the citation-step catalogue carries the explorer links, and the three failure kinds are kept
- [x] 3.4 Capture test: a list-datasets payload under the key yields no record and no unreadable count

## 4. Docs and verification

- [x] 4.1 Update `docs/architecture.md` and module docstrings that describe the dataset link or the meta key
- [x] 4.2 Rename the field in the private channel configurations and the local `dial_conf/core/applications.json`
- [x] 4.3 Run `make format`, `make lint` and the test suite
- [x] 4.4 Run a report against the local server on a channel whose dataset server sends the payload, and check that dataset pills and References rows open the data explorer
