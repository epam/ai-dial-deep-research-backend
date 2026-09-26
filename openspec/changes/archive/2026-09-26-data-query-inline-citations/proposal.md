## Why

A fact the report draws from a data query is cited `[dataset <urn>]` today, and its pill opens the
dataset's portal page. A reader who wants to check "real GDP growth in 2023 was 2.9%" lands on a
page describing the whole dataset and has to rebuild the query by hand: pick the country, the
series and the period again. The pill names the right source but opens the wrong level of it.

The StatGPT data-query tool already reports what a pill needs to open the data itself. Every query
it runs carries a `queryId`, which the model sees in the tool's text content. The same `queryId`
appears in the tool result's `_meta`, under a namespaced key such as `<namespace>/client`, next to a
`dataExplorerUrl` that opens the data explorer on exactly that query. `_meta` is outside what the
model reads. A channel can also report the URL in the structured result, which the model reads as
text: the data-query tool config field `mcp_structured_content.data_explorer_url` decides when,
with the values `always` (the default), `only_when_no_data` and `never`. On a channel that sets
`never`, the model never sees the URL and never writes it into a report. Nothing in this
application reads `_meta` yet. The one thing standing between a data-query citation and a pill that
opens its series is therefore this application.

## What Changes

- **A new inline citation form, `[data_query <id>]`, for every fact taken from a data query.** The
  `<id>` is the `queryId` the data-query tool reported, written whole, for example
  `[data_query dq_0123abcd45]`. The report writer SHALL use this form for every fact drawn from a
  data query result. `[dataset <urn>]` stays, and is kept for statements about a dataset as a whole
  that come from no query, such as when a dataset was last updated or what it covers.

- **A `[data_query <id>]` citation becomes a pill that opens the data explorer on that query.** It
  converts on one condition: the query has an explorer link. That means that during this turn, a
  tool result carried a `_meta` payload under the server's configured key, and in that payload the
  query with this `queryId` carries a `dataExplorerUrl` that is an absolute `http` or `https` URL. A
  query id the app never saw, and one seen without such a URL, keeps its marker text and produces
  no annotation. There is no fallback to the dataset page. A constructed query that did not run is
  the ordinary case of an id seen without a URL. Whether the query returned data is not part of the
  condition: the report review catches that, and whatever it leaves in place is resolved as well as
  it can be.

- **The report review also checks cited dataset URNs and document ids against their servers.** A
  URN the dataset catalogue does not carry, or a document id the document-metadata resource does not
  know, raises a violation asking for the identifier exactly as the tool reported it. The review
  and the delivery share one set of lookups per turn, so the catalogue is still fetched once and a
  document is read once. A failed lookup flags nothing. Page indices are not checked; that is
  deferred. For the document check to work, the document-metadata resource must omit exactly the
  ids its channel does not know, which the Generic RAG resource already does.

- **The report review checks every cited query id against what the turn captured.** A query
  returned data when its structured result carries a `seriesCount` above zero, and only such a
  query may be cited. An id no tool reported gets a violation asking for the id the tool reported.
  An id of a query that did not return data — a candidate, a query that did not run, or one that
  returned nothing — gets a violation saying that only a query that returned data may be cited, and
  what to do instead: cite the dataset for a statement about the dataset itself, otherwise drop the
  citation or the statement. The check does not look at the explorer link: a query that returned
  data is usable evidence, and a missing link costs only the pill. The check is Python over the
  draft and the captured records, like the heading and hyperlink checks.

- **The app captures `_meta` itself, because the MCP adapter drops it.** `langchain-mcp-adapters`
  copies only `structuredContent` into the `ToolMessage` artifact and discards `CallToolResult._meta`.
  The research turn's MCP client gets a tool-call interceptor. The interceptor sees each raw
  result, and keeps each query's `_meta` element and structured-result element whole, joined by
  `queryId`, for the rest of the turn. One result may report several queries, and each becomes its
  own record. Nothing it keeps reaches a model. Only the explorer URL is read from `_meta`; the
  dataset URN, the series count, the filter and the period are read from the structured result.
  Both shapes are pinned in code, and only the `_meta` key is configured.

- **A data-query pill reads like a dataset pill, and its card shows the query's filter.** The pill
  reads `<dataset name> dataset`. The name comes from the dataset catalogue record for the query's
  dataset URN, falls back to `<urn> dataset` when the catalogue has none, and falls back to the
  marker's own text, `data_query <id>`, when the query reports no dataset URN. The pill opens the
  data explorer, never the dataset's portal page. The card's title adds the dataset's last-update
  date when the catalogue reports one:
  `World Economic Outlook dataset - last update 2025-04-30`. The card's `body.quote` is a Markdown
  list with one item per filtered dimension, in display names, such as
  `* Country: United States, Germany`, each item cut to the channel's
  `data_query_card_filter_max_line_chars` (80 by default), the ellipsis counted within it. It ends
  with one period
  item, such as `* From 2020-01-01 until 2024-12-31`, or `* Until 2030-01-01` when only one bound
  was requested, and no period item when none was. The filter and the period are taken from the
  data-query tool's structured result for that `queryId`.

- **A data query is its own source.** Two citations of one query id are one source, so they fold
  into one popup entry. Two different queries of one dataset are two sources, and a run citing both
  yields one pill whose popup steps through both, as two pages of one publication do today.

- **A dataset citation's card changes to match.** Its title becomes
  `<name> dataset - last update <date>`, or `<name> dataset` when the catalogue reports no date, and
  it loses its `body.quote`: the `* URN:` and `* Last update:` items go. The pill is unchanged. A
  dataset's References row keeps its labels, which read the dataset's title alone, with no
  ` dataset` and no date, and it no longer carries a quote either.

- **The References section still lists datasets.** A cited query with an explorer link
  contributes its dataset, found through the structured result's `datasetUrn`, to the existing
  dataset table. That row is the same row a `[dataset <urn>]` citation of the same dataset would
  produce, and it opens the dataset's portal page. A dataset cited both ways is listed once, at the
  position of its first citation of either form. A query with an explorer link and no dataset URN
  gets a plain-text row reading `data_query <id>`. A query without an explorer link contributes no
  row, so a data-query citation is either a pill with a row or plain text with neither.

- **A new configuration field, `data_query_meta_key`, names the `_meta` key on a `statgpt`
  server, and a `statgpt` server must name it.** The key's namespace belongs to one deployment's
  channel configuration, so it cannot be a constant in this code. It is required for the reason
  `dataset_metadata_tool` is: the report writer is told to cite every data-query fact by query id,
  so a dataset server without the key would deliver every such citation as text and list none of
  their datasets. Only a `statgpt` server may set it. **BREAKING**: a channel with a `statgpt`
  server that does not set this field fails validation, and its turns are delivered as
  "application not configured" until its properties are edited.

- **A second new field, `data_query_card_filter_max_line_chars`, is a channel setting** with a
  default of 80 and a floor of 10. It sets how long one filter item on a data-query card may be.

- **The dataset-metadata tool is also called when the report cites only data queries**, because
  a query citation's label and its References row both read the catalogue record of its URN.

- **The citation step's INFO event gains two counts**: how many distinct query ids the report
  cited, and how many of them resolved a usable data explorer URL. The step also warns once when
  nothing was captured, once when cited ids match no captured query (unless nothing was captured),
  and once when payloads could not be read. No warning carries a query id.

- **The word count and the review's citation check recognise the new form.** A `[data_query …]`
  marker is excluded from the report's word count, as the other two forms are. The review
  prompt's citation-format check accepts it.

- **The annotations demo is untouched.** It cites the caller's attachments and has no data query
  to cite.

## Capabilities

### New Capabilities

None. Every requirement this change adds belongs to a capability that already owns the surrounding
behavior.

### Modified Capabilities

- `report-citations`: a new conversion requirement for `[data_query <id>]` with its condition and
  failure modes; a new requirement for how query records are captured from tool results' `_meta`
  and structured results during the turn; the annotation payload requirement gains the data-query
  entry, with its URL, labels and filter quote; the run requirement gains the data-query source
  identity; the References requirement adds the datasets that cited queries name; the
  dataset-metadata call runs when only queries are cited. Two existing requirements are modified:
  the annotation payload requirement moves a dataset card's last-update date into its title and
  drops its `body.quote`, and the References requirement stops copying that quote onto a row. A new requirement makes the review and the delivery share
  one set of catalogue and document-metadata lookups per turn, and states that the resource omits
  exactly the ids its channel does not know.
- `source-attribution`: the dataset-server requirement stops deferring series-level attribution.
  A data-query fact is attributed to the query that produced it, and the query id resolves verbatim
  against what the same server reported during the turn.
- `research-execution`: the report node's citation contract gains the third form, what identifies
  its source, and the rule that every data-query fact uses it.
- `report-composition`: the app-owned checks gain the data-query citation check and its two
  violation wordings, and the dataset and document identifier checks; the review's citation-format check shows the model a well-formed data-query
  citation and accepts it. The word count needs no spec change, because it already
  excludes every inline citation form **research-execution** defines.
- `application-config-schema`: the new `data_query_meta_key` field, its `statgpt`-only
  restriction, the rule that a `statgpt` server must name it, and the rule that it is the only
  configured part of the data-query contract; the new channel field
  `data_query_card_filter_max_line_chars`.
- `logging-policy`: the (8c) citation event carries the two data-query counts, and the citation
  step's three data-query warnings.

## Impact

- **`src/dial_deep_research/app_properties.py`**: the `data_query_meta_key` field on
  `MCPClientSettings`, its validator (required on `statgpt`, refused on every other type), and an
  accessor on `ApplicationProperties` mirroring `dataset_metadata_tool`; the
  `data_query_card_filter_max_line_chars` field on `ApplicationProperties`.
- **`src/dial_deep_research/app/mcp_tools.py`**: `build_mcp_client` installs the capturing
  interceptor, and `LoadedMcpTools` carries the per-request store of captured query records.
- **`src/dial_deep_research/app/research/data_queries.py`** (new): the interceptor, the pinned
  models of the payload and the structured result, the record that keeps each query's `_meta`
  element and structured-result element whole, and the store keyed by `queryId`. Nothing in it logs a URL, a filter value or a query id.
- **`src/dial_deep_research/app/research/citations.py`**: the `[data_query <id>]` marker in
  `_MARKER_RE` and `CitationMarker`; `cited_data_query_ids`; a `ConvertibleDataQueryCitation` with
  its source key; the data-query branch of `convert_citations` and of the annotation builders;
  the filter quote; the dataset card's title with the last-update date, and the removal of
  `_dataset_quote`; the two new counts on `log_citations_resolved`.
- **`src/dial_deep_research/app/research/references.py`**: `dataset_rows` takes the datasets that
  cited queries name, merged with the directly cited datasets in first-citation order.
- **`src/dial_deep_research/app/research/runner.py`**: the citation step reads the captured
  records, adds the URNs of cited queries to the catalogue read, passes both to the conversion and
  the References build, and fills the new counts on `_ReportDelivery`.
- **`src/dial_deep_research/app/research/report_length.py`**: `_CITATION_RE` matches
  `data_query`.
- **`src/dial_deep_research/app/research/report_rules.py`**: `ReportDataQueryRule`, its writer
  instruction and its two violations; `ReportDatasetIdRule` and `ReportDocumentIdRule`;
  `build_report_rules` takes the store and the lookups.
- **`src/dial_deep_research/app/research/citation_lookups.py`** (new): the per-turn cache of the
  catalogue answer and of document metadata, shared by the review checks and the citation step.
- **`src/dial_deep_research/app/research/graph.py`** and **`nodes.py`**: the store reaches the
  report nodes that build the rules.
- **`src/dial_deep_research/app/research/prompts.py`**: the report writer's citation section and
  the review prompt's citation-format check.
- **`docs/architecture.md`**: the report-delivery section's list of what converts and when; the
  MCP-tools paragraph, which gains the interceptor; and the report-review section's list of the
  app-owned checks, which gains the data-query check.
- **`docs/generated-app-schema.json`**: regenerated by `make format` from the new field.
- **`README.md`**: the MCP server configuration paragraph that lists what a `statgpt` server must
  name.
- **Tests**: fixtures that build a `statgpt` server gain the new field, in
  `tests/test_app_properties.py`, `tests/test_mcp_client.py` and `tests/test_report_delivery.py`;
  `tests/test_research_dispatch.py` and `tests/test_status_stages.py` build `LoadedMcpTools` and
  gain the store; the assertions on the dataset quote (`* URN: …`) in `tests/test_citations.py`,
  `tests/test_dial_annotations.py`, `tests/test_references_section.py` and
  `tests/test_report_delivery.py` change to the title with the last-update date and no quote. New
  tests cover the capture, the conversion, the filter quote and the References merge.
- **Not touched**: `dial_conf/core/applications-template.json`, which carries no `statgpt` server;
  the README environment-variable table, since no environment variable is added; the annotations
  demo, whose `log_citations_resolved` call keeps working because the two new counts default to
  `0`.
- **Dependencies**: none added. The interceptor hook is part of the installed
  `langchain-mcp-adapters` 0.3.0 (`MultiServerMCPClient(tool_interceptors=...)`).
- **Servers**: the StatGPT MCP emits the `<namespace>/client` payload only when its data-query tool
  config enables it (`mcpMeta.client`). A channel that does not enable it delivers every
  `[data_query <id>]` citation as text and lists none of their datasets, with nothing failing.
