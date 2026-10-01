## Context

Every dataset link the report carries opens `DatasetSource.url`: the inline `[dataset <urn>]` pill,
the first cell of a dataset's References row, and the dataset row a cited data query adds. That
field is filled from the `url` of the list-datasets record (`parse_catalogue` in
`app/research/dataset_metadata.py`).

The catalogue is read in two places:

- The data-sources fetch (`app/data_sources.py`) calls the tool through
  `data_source_calls.call_with_attempts`, which opens an MCP session and gets the raw
  `CallToolResult`. Today it passes only `structuredContent` to its reader.
- `CitationLookups.dataset_sources` falls back to `read_catalogue` when the turn-start fetch failed.
  That function invokes the LangChain tool, and the adapter builds a `ToolMessage` whose artifact
  carries `structured_content` only (`langchain_mcp_adapters/tools.py`, `MCPToolArtifact`), so
  `_meta` never reaches it.

The StatGPT backend (commit `d8b61de`, "add mcpMeta client payload to the Available Datasets tool")
sends `_meta["<namespace>/client"] = {"datasets": [{"id", "dataExplorerUrl"?, "citationUrl"?}]}`.
A probe confirmed this shape, and confirmed that the list-datasets tool and the data-query tool
use the same key.

`DataQueryCapture` treats any result of the dataset server that carries a payload under the key as a
data-query result, and `ClientMeta` requires `queries`. A list-datasets call made by the research
agent therefore counts today as an unreadable data-query payload.

## Goals / Non-Goals

**Goals:**

- One rule decides a dataset's URL, applied once where the catalogue is parsed, so the pill, the
  References row and the (8c) `datasets_resolved` count cannot disagree.
- Both catalogue reads see `_meta`.

**Non-Goals:**

- Building or rewriting explorer URLs in the app. The server owns the URL format.
- Showing the explorer link to any model, or adding it to the datasets section.
- Making the `_meta` element available to References columns. A row's columns read the structured
  record, as before.

## Decisions

**D1. Resolve the URL at parse time.** `parse_catalogue` takes the `_meta` payload next to the
structured result, and sets `DatasetSource.url` to the element's `dataExplorerUrl` when it is a web
URL, and to the record's `url` otherwise. The alternative was to keep both URLs on `DatasetSource`
and choose in `citations.py`. That puts the same choice in three readers (the conversion, the row
target and the resolved count), while nothing needs the unchosen URL. The payload is read leniently,
element by element: an unreadable payload or element yields no links, never an exception.

**D2. `call_once` hands the reader the whole `CallToolResult`.** The list reader needs
`structuredContent` and `meta`. The structure and glossary readers keep their signature over the
structured content, wrapped by a small adapter at their call sites. The alternatives were a second
optional callback, or a `meta_key` parameter on `call_once` that changes how `read` is called. Both
make the helper's contract depend on its arguments. The check that `structuredContent` is present
stays in `call_once`, so every reader still gets a result that has one.

**D3. The fallback call opens its own session on the turn's client.** `read_catalogue` becomes a
call through `client.session(server_name)` and `session.call_tool(tool_name, {})`, the way the
data-sources fetch calls tools. `CitationLookups` receives what that call needs (the server name,
the tool name and the client meta key) instead of a `BaseTool`. The runner still passes it only
when the tool was advertised, so the "tool not advertised" warning is unchanged. The failure kinds
stay the same three: an MCP error is `dataset_call_failed`, a result with no structured content is
`dataset_no_structured_result`, and an unreadable structured result is
`dataset_unreadable_result`. Any exception the session raises still reaches the runner, which
reports it as `dataset_call_failed`. The alternative was an interceptor capturing list-datasets
results on the turn's client. It would also capture the research agent's calls, and it would make
the fallback read depend on a side channel instead of on its own result.

**D4. A payload without `queries` is not a data-query payload.** `DataQueryCapture` returns the
result untouched when the payload under the key is a JSON object without a `queries` field. A
payload that is not an object, or whose `queries` is not an array, still counts as unreadable.

**D5. Rename `data_query_meta_key` to `client_meta_key`, with no alias.** The user chose a breaking
rename. `MCPClientSettings` ignores unknown fields, so an old configuration fails with the existing
"must name its client_meta_key" error, which names the new field. An alias would leave two
spellings of one setting in the channel configurations indefinitely.

## Risks / Trade-offs

- [A deployed channel still sets `data_query_meta_key`] → It fails validation and is delivered as
  "application not configured". The private channel configurations are edited in the same change.
  The deployment repositories outside this workspace's writable folders must be edited before this
  version is deployed.
- [The dataset server configures a different namespace on the list-datasets tool] → Dataset pills
  open the portal page. Nothing warns, because a channel without the payload is valid.
- [The explorer link opens an explorer page that the portal cannot render for that dataset] → Out
  of the app's control; the server reports the link only when its data source configures an
  explorer.

## Migration Plan

1. Rename the field in every channel configuration: the private client configurations and their
   generated `applications.json` files, the local `dial_conf/core/applications.json`, and the
   deployment repositories.
2. Enable `mcpMeta.client` on the dataset server channel's list-datasets tool, with the same
   namespace as the data-query tool.
3. Rollback: revert the app; the old field name must be restored in the configurations with it.
