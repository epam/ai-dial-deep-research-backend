## Context

See `proposal.md` (Why) for the motivation. This section states only the facts that constrain the
approach. Each one was checked against the installed code or a live server, not inferred.

- **The data-query tool's result has three parts, and the model sees one of them.** A probe of a
  StatGPT MCP deployment returned a text content block and an embedded CSV resource, which the
  model sees, plus a structured result and a `_meta` object. The model never reads `_meta`. The
  text content is the structured result serialized as JSON (the backend's
  `MCP_DATA_QUERY_RESPONSE.md`), so the model reads what the structured result carries. The
  data-query tool config field `mcp_structured_content.data_explorer_url` decides when the
  structured result also carries `dataExplorerUrl`: `always` (the default), `only_when_no_data` or
  `never`. A channel that sets `never` carries the URL in `_meta` only. The text and the
  structured result both carry `queries[]`, whose elements hold `queryId`, `datasetUrn`, `filters`
  (each with `dimensionId`, `operator` and `values[].id`), `requestedPeriod` and `factualPeriod`.
  The backend's `MCP_DATA_QUERY_RESPONSE.md` also lists, in each element, `seriesCount` (absent
  when the query returned no data), `datasetName` and `datasetLastUpdated`. The structured
  `seriesCount` was read in that document and not yet observed in a probe; task 10.3 checks it.
  The `startPeriod` and `endPeriod` in the data explorer URL are the requested period's. `_meta["<namespace>/client"]` carries
  `{status, queries: [{queryId, urn, datasetName, dataExplorerUrl, datasetUrl, resourceUris,
  seriesCount}], version: 3}`. The backend builds this in `statgpt/app/mcp/attachments.py`
  (`_client_meta`), and its schema is `ClientQueryRecord` in `statgpt/app/schemas/mcp.py`. Only
  executed queries carry `dataExplorerUrl`; a constructed query that did not run carries
  `queryId`, `urn` and `datasetUrl`.
- **The namespace is per deployment.** `DataQueryMcpMeta.namespace` in the backend has a
  default, and a channel config overrides it. The `/client` payload is off by default
  (`mcpMeta.client.enabledStr: "False"`), and a channel must enable it.
- **The adapter drops `_meta`.** In `langchain-mcp-adapters` 0.3.0,
  `tools.py::_convert_call_tool_result` builds the tool content from `content` and the artifact
  from `structuredContent` alone, and never reads `CallToolResult.meta`. The tool coroutine runs
  the call through `_build_interceptor_chain(execute_tool, tool_interceptors)`, so each interceptor
  in `MultiServerMCPClient(tool_interceptors=[...])` receives the raw `CallToolResult`, with `meta`
  and `structuredContent`, before the conversion runs. `MCPToolCallRequest` carries
  `server_name`.
- **A query id is stable per query and day.** The backend's `QueryRecord.query_id` description
  says so, and two separate calls running the same query on the same day returned the same id.
- **One MCP client per research request.** `ResearchRunner.run` calls `load_mcp_tools` once
  (`research/runner.py`), which builds the client with `build_mcp_client`. The graph runs, and then
  `_deliver_report` runs the citation step on the same `LoadedMcpTools`. The preparation agent
  loads no MCP tools. The playground runner also calls `load_mcp_tools`.
- **`MCPClientSettings` ignores unknown fields** (it sets no `extra="forbid"`), so an image that
  predates this change accepts a config that already sets `data_query_meta_key`.

- **Assumptions the plan rests on** are stated in the report-citations capture requirement
  ("Assumptions about the data-query server"): a query that returned data carries a positive
  `seriesCount` in its structured element and a data explorer URL in its `_meta` element; a query
  without data may carry a URL but is not worth citing; a query that did not run carries no URL.
  The URL of a query that returned data was observed in live probes. The rest was read in the
  backend code and documentation, not observed: `_client_meta` sets the URL for every executed
  query, `_series_count` returns `None` for an empty response, and the NOT_EXECUTED branch sets no
  URL.

## Goals / Non-Goals

**Goals:**

- Resolve a `[data_query <id>]` marker to the data explorer URL the server reported for that id in
  this turn, with nothing in the model's input changed.
- Keep every existing citation behavior as it is: document and dataset conversion, the run rule,
  and References rows.
- Keep the capture free of failure modes: a bad payload costs its own records and never a tool
  call.

**Non-Goals:**

- Checking cited page indices. The review checks that a cited document exists, not that the cited
  page does; deferred by the user.
- Checking that the research retrieved a cited dataset or document in this turn. "Invalid" means
  unknown to the server; the user chose that over parsing each search tool's model-facing
  attribution text, which `source-attribution` forbids.
- Detecting a channel's configuration faults: a dataset whose data explorer link is disabled
  (`view_in_data_explorer: false`, so an executed query carries no URL), a data source with no
  explorer base URL (the backend then reports the raw SDMX request URL, which passes the web-URL
  check and opens an API response), and a `data_query_meta_key` that matches nothing. The user
  decided these are checked once per deployment, not handled in code. The nothing-captured warning
  (decision 8) is the one diagnostic kept.

- Citing an individual series inside a query's result. The explorer link opens the whole query,
  and a query that returned 8 series is cited as one source.
- Showing the data explorer link in the References section. Rows stay dataset rows, as decided.
- Carrying captured records across turns. Deep Research delivers its report in the turn that ran
  the research, and a query id is only resolvable in the turn that reported it.
- Using the backend's `querySummary` in the card. See decision 6.
- Reading the explorer URL from the model-visible content when a channel emits it there
  (`dataExplorerUrl` reporting other than `never`). The contract is `_meta`, and one read path is
  enough.

## Decisions

### 1. Capture `_meta` with a tool-call interceptor on the per-request MCP client

`build_mcp_client` gains a `tool_interceptors=[capture]` argument. `capture` is a small callable
object that awaits `handler(request)` and gets back the `CallToolResult`. It checks that
`request.server_name` is the `statgpt` server that has a `data_query_meta_key`, and that the result
is not an error. If both hold and `_meta` carries the configured key, it walks the `queries`
array of the payload and of the structured result, joins their elements by `queryId`, stores one
`DataQueryRecord` per id, and returns the **same** result object unchanged. One result can report
several queries (the backend's `DataQueryClientMeta.queries` is "one per dataset"), so the join is by
id and never by position. Everything that reads the payload runs inside `try/except Exception`, so
any exception counts as one unreadable payload and nothing more.

The store is `dict[str, DataQueryRecord]` keyed by `queryId`. `DataQueryRecord` is a pydantic model
with two fields, `meta: dict[str, Any] | None` (alias `_meta`, since a pydantic field name cannot
start with an underscore) and `structured_content: dict[str, Any] | None`, so a record dumps by
alias as `{"_meta": {...}, "structured_content": {...}}`, the schema the user specified. Each holds
its element whole, the way `DatasetSource.raw_fields` holds a catalogue record.
Properties read what a citation needs, through the pinned models of decision 12:
`data_explorer_url` from `meta` (`None` unless it is a web URL), and `dataset_urn`, `series_count`,
`filters` and `requested_period` from `structured_content`. Two predicates carry the spec's terms:
`has_explorer_link`, true when `data_explorer_url` is set, and `returned_data`, true when
`series_count` is above zero. They are independent of each other. Conversion and the References
section read `has_explorer_link`; only the review check (decision 10) reads `returned_data`, per the
user's rule that whatever the review leaves in place is resolved as well as it can be. The backend
sends a `_meta` element for every query that reached the data source or was constructed to run,
and sends `dataExplorerUrl` even for a query that returned nothing (`_client_meta` in
`statgpt/app/mcp/attachments.py`), so a record with no `meta` element has no explorer link.

The interceptor also keeps each `candidateDatasets[].query` element, as the `structured_content` of
a record with no `meta`. No candidate flag is needed: a candidate and a constructed query whose
period the server rejected both look like that, and the review check treats both alike — known, no
data. A candidate has no explorer link and did not return data. It is kept so the review check can
tell a writer who cited it that the query returned no data, instead of calling its id unknown.
Validation happens at read time, not at capture, so a field the app does not read can never make a
record unreadable.

Alternative considered: **store only the fields the app reads.** Rejected by the user in favour of
storing the elements whole: the card's content has changed three times during planning, and a
record that holds everything lets the next change read a new field without touching the capture.

The store is a plain object owned by the interceptor (`DataQueryStore`: a `dict[str,
DataQueryRecord]` plus an `unreadable_payloads` counter). `LoadedMcpTools` returns it, and the
runner passes it to the citation step. Tool calls in one turn run on one event loop, so the dict
needs no lock.

Alternatives considered:

- **Wrap each MCP tool's coroutine.** A wrapper sees only the converted `(content, artifact)` pair,
  and `_meta` is already gone by then, so this cannot work.
- **Patch `_convert_call_tool_result` to copy `meta` into the artifact.** This would put `_meta` in
  the `ToolMessage` artifact, which graph state already carries, and the citation step could read
  it from the messages. Rejected: it patches a private function of a dependency, so an adapter
  upgrade breaks it silently. It also puts every server's `_meta` into graph state for a feature
  that needs one key.
- **Have the interceptor return a `ToolMessage` carrying `meta` in its artifact.** The adapter
  accepts a `ToolMessage` from an interceptor, but it then returns that message as the content
  with artifact `None` (`_convert_call_tool_result`, first branch). That bypasses the content-block
  conversion and the error handling the agent relies on. Rejected: it changes what the agent
  receives, which the spec forbids.
- **Ask the backend to put `dataExplorerUrl` into `structuredContent`.** Rejected: the channel keeps
  the URL out of every part a model might read on purpose, and other MCP hosts show the structured
  result to their model. `_meta` is the part the backend designed for programmatic clients.
- **Upgrade `langchain-mcp-adapters` to 0.3.2, or switch to `langchain.mcp` in `langchain` 1.4.2.**
  Rejected: neither keeps the result's `_meta`. Both build the artifact from structured content
  only. Adapter PR 612, which would have kept it, was closed unmerged on 2026-09-16, because the
  adapter repository is winding down in favour of `langchain.mcp`. `langchain.mcp` is beta, and no
  interceptor hook was found in it. Moving to it is a separate change, and that change must solve
  the `_meta` capture again.

### 2. The store lives for one request, outside graph state

The records live on the object `load_mcp_tools` returns, and they die with the request. Nothing is
written to `custom_content.state` or to graph state.

Alternative considered: **put records into graph state** so a later node or turn could read them.
Rejected: the report is delivered in the same request, and no node besides the citation step needs
the records. Persisting them would also mean serializing URLs into the conversation state, which
has its own merge hazards (the DIAL SDK's `index` rule in `CLAUDE.md`).

### 3. The marker is `[data_query <id>]` and parses like a dataset marker

`_MARKER_RE` in `citations.py` gains a third alternative,
`\[[ \t]*data_query[ \t]+(?P<data_query_id>[^\[\]\n]+?)[ \t]*\]`. The keyword is case-insensitive
like the other two keywords, and the id is taken verbatim like a URN. `CitationMarker` gains
`data_query_id`, and `cited_data_query_ids(text)` mirrors `cited_dataset_ids`. The id pattern
accepts anything but a bracket or a line break. Constraining it to the backend's current shape
(`dq_` plus hex) would make this app depend on how one server spells its ids, which
`source-attribution` forbids for the same reason it forbids fixing an attribution spelling.

`report_length._CITATION_RE` adds `data_query` to its keyword list, so the word count keeps
excluding every inline form.

The marker form was the user's decision. Alternatives the user did not pick: `[data <id>]`,
`[query <id>]` and `[series <id>]`.

### 4. `data_query_meta_key` is a required per-server field

This is the user's decision (configured key rather than detection by shape). It is required on a
`statgpt` server, like `dataset_metadata_tool`. It is the only configured part of the data-query
contract: everything under the key, and the structured result, is pinned in code (decision 12).

Alternatives considered:

- **Detect the payload by shape**, as any `_meta` key ending in `/client` with a `queries` array.
  The user rejected this: it ties the app to how one backend names its keys.
- **Make the field optional.** Rejected: the prompt is the same for every channel and tells the
  writer to cite every data-query fact by query id. A `statgpt` server with no key would therefore
  deliver every such citation as text and drop their datasets from References, and nothing would
  fail. Requiring the key moves that loss to configuration time, where someone sees it. A key that
  is set but matches nothing is still possible, and the nothing-captured warning (decision 8)
  covers it.
- **Configure the field names under the key too**, such as where `queries`, `dataExplorerUrl` or
  `datasetUrn` sit. Rejected with the user: the names are defined by the backend and are the same
  in every deployment, only the namespace differs. A configured name protects only against a
  rename that comes alone, while a real change of the payload bumps its `version` and needs code
  anyway, and a per-channel setting could drift away from the server it describes.

### 5. A data-query citation is a fourth convertible kind, with dataset-shaped labels

`ConvertibleDataQueryCitation` carries `query_id`, `url` (the explorer URL), `urn` (the
structured `datasetUrn`, or `None`), the captured `DataQueryRecord`, and the `DatasetSource` of its
URN if the catalogue reported one. Its `source_key` is `("data_query", query_id)`. The union
`ConvertibleCitation` gains it, and `_build_annotation` and `_annotation` gain a branch. The labels
reuse the dataset code path, taking the name from the catalogue source or falling back to the URN,
with ` dataset` appended after shortening. When `urn` is `None` the label is the marker's own text,
`data_query <id>`, unshortened, as an unresolved document's `doc <id>, page <ix>` is. The URL is
always the explorer URL, never the catalogue's page URL.

`convert_citations` gains `data_queries: Mapping[str, DataQueryRecord] | None = None`. When it is
omitted, every data-query marker keeps its text, so the annotations demo keeps calling the function
unchanged.

Alternatives considered:

- **Label a pill from the `_meta` `datasetName`, or the structured `datasetName`.** Rejected: on
  the probed server the `_meta` value carries the URN in brackets after the name, and either one
  can differ from the catalogue's name, so a pill and a References row would name one dataset in
  two different ways. The catalogue is the one source of dataset names and dates.
- **Take the URN from `_meta.urn`.** Rejected by the user in favour of the structured `datasetUrn`:
  it is the spelling the writer saw, so the URN the catalogue is searched for is the one a
  `[dataset <urn>]` citation of the same dataset would carry.
- **Give it its own trailing word** (`<name> data`). The user rejected this and kept the dataset
  format.
- **Fall back to the dataset pill when the query has no URL.** The user rejected this twice. It
  would need its own answers for the card's title and body and for the References row, which makes
  the flow harder to follow for little gain.

### 6. The card shows the filter in names, one line per dimension, and the date in its title

This is the format the user specified. `_data_query_quote` builds one item per `in` filter,
`* <dimensionName>: <name>, <name>, …`, with the id standing in for a missing name, and cuts each
item to the channel's `data_query_card_filter_max_line_chars` (default `80`, floor `10`, not
nullable) with `_shorten_for_pill`'s rule: the ellipsis counts within the budget, so a cut item is
exactly that long, and whitespace at the cut is dropped. The value reaches the conversion the way
`max_pill_title_chars` does. It then adds one period item from the requested
period (`From <start> until <end>`, `From <start>` or `Until <end>`), and no period item when
neither bound was reported. The requested period is used rather than the factual one because it is
the period the data explorer link opens. The last-update date moves from the list into
`body.title` (`<name> dataset - last update <date>`). The URN leaves the card, since the dataset's
References row names it. A filter with any operator other than `in`, `excluded` included, is left
out, because a list of names would misstate a range or an exclusion.

A dataset citation's card takes the same title, `<name> dataset - last update <date>`, and loses
its quote: `_dataset_quote` is removed, and the dataset branch of `_dataset_body` sends no
`body.quote`. The user asked for both cards to match. The References row labels are unchanged: a
row's pill and card read the dataset's title alone, with no ` dataset` and no date, which
`build_row_annotation` already does. The one change there is that a dataset row stops copying the
inline citation's quote, since there is none left to copy.

Alternatives considered:

- **One line of codes**
  (`* Filter: COUNTRY=[DE,US],INDICATOR=[NGDP_RPCH],startPeriod=2020-01-01,endPeriod=2024-12-31`).
  This was an intermediate draft. The user replaced it with names, one line per dimension, which a
  reader can take in without knowing the dataset's code lists.
- **Put the data explorer URL itself in the body.** The user considered it and chose the filter
  instead. The URL already sits in `body.source.attachment.url`, where the card's open-in-browser
  action follows it.
- **List every value however long the line gets.** Replaced by the user's 80-character cut on the
  whole line: a filter on 35 countries would otherwise fill the card, and the link opens the whole
  selection anyway.
- **Cut to the first few values plus a count** (`and 30 more`). Not chosen: the user specified a
  cut by characters, which keeps every line the same maximum width.
- **A module constant.** Replaced by the user with the channel setting, for the reason the pill
  budget is one: what fits on a card depends on the channel's client.
- **Make the setting nullable**, as `max_pill_title_chars` is. Not chosen: a filter on 35 countries
  always needs a cut, so switching cutting off would only produce a card no client has room for.
- **The backend's `querySummary` sentence.** Rejected: the user asked for the filter. The summary
  is a sentence that can run long in a narrow card.
- **Leave out filters marked `isDefault`.** Rejected: a default filter still bounds the data the
  link opens, and a reader comparing the card with the explorer would see a mismatch.

### 7. References: cited queries add their URNs to the dataset rows

The runner computes one ordered URN list, `cited_dataset_urns`, by walking the markers in report
order. A dataset marker contributes its URN. A data-query marker contributes the structured
`datasetUrn` of its record, if the query has an explorer link and a `datasetUrn`. Duplicates are
dropped. A query with an explorer link and no `datasetUrn` contributes a row of its own instead,
at the position of its first citation: its first cell reads `data_query <id>` as text, its other
cells are empty, and it is not openable, because a References row opens a dataset's page and this
query names no dataset. That list feeds both
`_read_dataset_sources` and `dataset_rows`, so the catalogue call and the table see one definition
of "cited dataset". Both dataset counts on the (8c) event keep counting **dataset markers** only:
`datasets_requested` is the number of distinct dataset-marker URNs, and `datasets_resolved` counts
the sources with a page URL among those URNs, not among every source the merged read returned. The
new `data_queries_requested` and `data_queries_resolved` count query ids and queries with an
explorer link.

A query without an explorer link contributes no row, so a data-query citation is either a pill with
a row or plain text with neither.

Alternative considered: **one References row per query, opening the explorer.** The user rejected
this twice: References lists datasets, and each row opens its dataset's portal page. The portal
page is used by a dataset citation and a dataset's row only, never by a data-query pill.

### 8. Diagnostics live at the citation step, as counts and three warnings

The interceptor logs nothing above DEBUG, and it never logs a payload. The citation step logs each
warning with its own message, which states the outcome in words. None of them goes through
`_log_citation_failure`: that helper's `kind=` token tells apart call failures that share one
message, and these are outcomes of the turn, each with a message of its own.

| When it fires | Message |
|---|---|
| The report cites at least one query id, and the store is empty. | `Report cites data queries, but the turn captured no data-query records: cited_ids=%d` |
| The store is not empty, and at least one cited id is not in it. Not logged when the line above is. | `Report cites data query ids that match no captured query: unmatched_ids=%d` |
| The store counted unreadable payloads. | `Tool results carried an unreadable data-query payload in _meta: tool_results=%d` |

The first message has three causes: a key that matches nothing, a channel that does not enable the
payload, and a research turn that ran no data query while the report still cites ids. The docstring
of the code that logs it names all three, since the message cannot tell them apart. The second is
suppressed whenever the first is logged, so one cause yields one warning. No warning carries a
query id. `log_citations_resolved` gains `data_queries_requested` and `data_queries_resolved`.

Alternative considered: **warn in the interceptor on each unreadable payload.** Rejected: it fires
on turns whose report cites nothing, and a research turn runs many queries, so it would also flood.

### 9. Prompt wording

The writer's citation section in `research/prompts.py` gains a third bullet: a fact from a data
query is cited `[data_query <id>]` with the id the tool reported for that query, and every such
fact uses this form. The rule that only a query that returned data is cited — never the id of a
candidate, of a query that did not run, or of one that returned nothing — is **not** written here: it is
`ReportDataQueryRule.writer_instruction()` (decision 10), which `render_writer_instructions` already
renders into the writer's prompt, so the instruction and its check stay in one place.
`[dataset <urn>]` is re-scoped to statements about a dataset as a whole, such
as its last update or its coverage. The "Match the citation to the source" bullet is updated to
cover all three forms. As `source-attribution` requires, the prompt describes the id as "the
identifier the tool reports for the query", and gives `queryId` only as one example of where it
may appear. The review prompt's check 5 gains the form and a well-formed example.

### 10. The review loop checks cited query ids against the store

`report_rules.py` gains `ReportDataQueryRule(ReportRule)`, built by `build_report_rules` from the
turn's `DataQueryStore`, which `build_research_graph` receives from the runner beside the tools.
Its `violations(draft)` walks `cited_data_query_ids(draft)` and reports, per id, the wording the
report-composition spec gives: an unknown id asks for the id the tool reported; a known id whose
record is not `returned_data` (a candidate, a query that did not run, or one that returned nothing)
says only queries that returned data are cited, then directs dataset statements to `[dataset <urn>]`, and any other
statement to dropping the citation or the statement. A query without data backs no value, so a fact
about the dataset is the only thing such a citation can stand for. The check does not read
`has_explorer_link`: a query that returned data is usable evidence, the writer cannot see the link,
and a missing one costs only the pill. Its `writer_instruction()` carries the returned-data citing
rule, so the instruction and the check live
in one class, as the other rules' do (`report_rules.py` module docstring).

The store is read while the research turn is still running. That is safe because every tool call
has finished by the time the report node runs, and the store is only ever appended to.

Alternatives considered:

- **One violation saying "remove this citation".** Rejected with the user: for a statement about
  the dataset itself, removal loses a citation the report needs, where `[dataset <urn>]` keeps it. The wording
  says what to do instead.
- **Prompt only, no check.** Rejected by the user: a mistaken id would reach the reader as a bare
  marker.
- **Refuse to convert a citation of a query without data.** Rejected by the user: the review is
  where it is caught, and whatever survives the review is resolved as well as it can be.

### 11. One lookup cache per turn serves the identifier checks and the delivery

The runner builds a `CitationLookups` object per request, beside the data-query store, and passes
it to `build_research_graph` (for the rules) and to the citation step. It holds the catalogue
answer once fetched, and a map from document id to its metadata answer, where an absent id is
recorded as unknown. `ReportDatasetIdRule` and `ReportDocumentIdRule` in `report_rules.py` read it.

`ReportRule.violations` is synchronous, and the lookups are MCP calls, so `report_review` in
`nodes.py` first awaits `lookups.prefetch(draft)` — fetching only what the draft cites and the cache
lacks, a cited query contributing the `datasetUrn` of its record when it has an explorer link —
concurrently with the review model call, and then runs the rules. The review gains no
latency beyond the slower of the two. A failed prefetch leaves those ids out of the cache, so the
rules treat them as not looked up and raise nothing.

At delivery, `_run_citation_step` reads the catalogue and document metadata through the same object,
so ids already looked up cost nothing and the dataset tool is still called once per turn when it
succeeds. The file-sharing call is untouched: it copies files into the user's bucket, which only the
delivered report needs.

Alternatives considered:

- **Validate against this turn's tool results instead of the servers.** Rejected by the user: for
  documents it means parsing each search tool's model-facing attribution text.
- **Look ids up at delivery only, and drop unknown citations there.** Rejected: delivery cannot ask
  the writer for a fix, so an invented id would reach the reader as a bare marker, which is exactly
  what the review loop exists to prevent.
- **Validate documents through the file-sharing tool.** Rejected: it copies every cited file into
  the user's bucket on each review round.

### 12. The payload shapes are pinned in code; only the `_meta` key is configured

The `_meta` payload and the structured result are defined by the StatGPT backend
(`ClientQueryRecord` and the structured result's schema in `statgpt/app/schemas/mcp.py`, described
in `statgpt/app/MCP_DATA_QUERY_RESPONSE.md`). Only the namespace of the `_meta` key differs between
deployments, so that key is the one configured value (decision 4), and the fields under it are
pinned by these models in `app/research/data_queries.py`. The models read only what a citation
uses; every other field is ignored, and the record keeps each element whole regardless.

```python
_LENIENT = ConfigDict(extra="ignore", populate_by_name=True)


class FilterValue(BaseModel):
    model_config = _LENIENT
    id: str
    name: str | None = None


class QueryFilter(BaseModel):
    """One element of `StructuredQuery.filters`."""

    model_config = _LENIENT
    dimension_id: str = Field(alias="dimensionId")
    dimension_name: str | None = Field(default=None, alias="dimensionName")
    operator: str
    values: list[FilterValue] = []


class RequestedPeriod(BaseModel):
    model_config = _LENIENT
    start_period: str | None = Field(default=None, alias="startPeriod")
    end_period: str | None = Field(default=None, alias="endPeriod")


class StructuredQuery(BaseModel):
    """One element of `StructuredResult.queries`, or a `CandidateDataset.query`."""

    model_config = _LENIENT
    query_id: str = Field(alias="queryId")
    dataset_urn: str | None = Field(default=None, alias="datasetUrn")
    series_count: int | None = Field(default=None, alias="seriesCount")
    filters: list[dict[str, Any]] = []
    requested_period: RequestedPeriod | None = Field(default=None, alias="requestedPeriod")


class CandidateDataset(BaseModel):
    """One element of `candidateDatasets`: the query the server offers to run on that dataset."""

    model_config = _LENIENT
    query: dict[str, Any] | None = None


class StructuredResult(BaseModel):
    """The tool result's `structuredContent`."""

    model_config = _LENIENT
    queries: list[dict[str, Any]] = []
    candidate_datasets: list[CandidateDataset] = Field(default=[], alias="candidateDatasets")


class ClientMetaQuery(BaseModel):
    """One element of `ClientMeta.queries`: where the query opens in the data explorer."""

    model_config = _LENIENT
    query_id: str = Field(alias="queryId")
    data_explorer_url: str | None = Field(default=None, alias="dataExplorerUrl")


class ClientMeta(BaseModel):
    """The payload at `_meta[<data_query_meta_key>]`."""

    model_config = _LENIENT
    queries: list[dict[str, Any]]
```

Where each model is applied decides what a bad value costs:

- **At capture**, `ClientMeta` validates the payload under the key, and `StructuredResult` the
  structured result. A payload that fails `ClientMeta` is one unreadable payload and yields no
  records. A structured result that fails `StructuredResult` is read as absent, so its queries keep
  their `_meta` element and lose the structured one. Within each array, an element whose `queryId`
  is not a string is skipped, and every other element is stored whole as a dict.
- **At read time**, `ClientMetaQuery` and `StructuredQuery` validate a record's two elements. An
  element that fails reads as absent: a bad `_meta` element costs the explorer link, and a bad
  structured element costs the dataset, the series count and the filter.
- **Each filter** is validated with `QueryFilter` on its own, so a bad filter costs its own card
  item and nothing else. `filters` stays a list of dicts on `StructuredQuery` for that reason.

A `seriesCount` that is not an integer fails `StructuredQuery` like any other bad field, so its
record did not return data. A backend change to these shapes is a change to this code, detected by
the tests that pin the models against a synthetic payload of each shape.

Alternative considered: **configure the field names.** Rejected; see decision 4.

## Risks / Trade-offs

- [The writer cites `[dataset <urn>]` for a fact from a data query, out of habit or because the
  URN is more visible in the tool text] → The prompt states the rule as an absolute, with an
  example. The review model cannot check it (report-composition), so the cost is a dataset pill
  where a query pill was due, which is still a correct citation. Eval runs should watch the ratio.
- [The writer cites the id of a constructed query that never ran] → Its marker stays as text. The
  prompt says a query that did not run has no data to cite.
- [The backend changes the `/client` payload shape (it is `version: 3` today)] → The read is
  validated per result and costs only that result (decision 12). Only `queryId` and
  `dataExplorerUrl` in `_meta`, and `queryId`, `datasetUrn` and `seriesCount` in the structured
  result, are load-bearing, and the other fields are optional.
- [A long research turn captures hundreds of records] → Each record is a few short strings, and the
  records are released with the request.
- [The configured namespace leaks into the repository through tests or docs] → Tests and the
  template use `acme.example.org/client`. The real key lives only in DIAL Core application
  properties. `scripts/check_sensitive_info.sh` runs on staged diffs.
- [The interceptor also runs on the app's own calls: file sharing and the catalogue] → Those
  results carry no payload under the key, so they contribute nothing.

## Migration Plan

1. Set `data_query_meta_key` on the `statgpt` server of every channel's application properties in
   DIAL Core. Images that predate this change ignore the field, so this is safe to do first.
2. Make sure the StatGPT channel behind that server enables its `mcpMeta.client` payload. If it
   does not, reports deliver data-query citations as text, and the nothing-captured warning
   appears.
3. Deploy the new image.

Rollback is redeploying the previous image. The field can stay in config. Reports written by the
new image carry `[data_query …]` markers, and the old image does not convert them, but a delivered
report is never re-rendered, so nothing already delivered changes.

## No changes required

- `dial_conf/core/applications-template.json` carries no `statgpt` server, so it has nothing new to
  set.
- `app/annotations_demo/*` calls `convert_citations` without `data_queries` and cites attachments
  only. It does call `log_citations_resolved`, so the two new count parameters default to `0` and
  the demo keeps its call unchanged.
- `app/preparation/*` loads no MCP tools, so no query id can come from preparation.
- `research/file_sharing.py`, `research/document_metadata.py` and `research/dataset_metadata.py`
  keep their contracts. The runner passes `dataset_metadata.read_dataset_sources` a longer id list,
  and nothing else changes in it.
- `citations.remove_hyperlinks` needs no change: `[data_query x]` is a reference-style link only
  when a matching `[data_query x]: url` definition exists, which is the rule that already protects
  the other two forms.
- The README environment-variable table needs no change: no environment variable is added.
- `app/tool_failures.py` needs no change: an error result raises after the interceptor returns,
  and the interceptor skips error results.
