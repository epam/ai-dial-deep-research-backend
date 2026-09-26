## 1. Configuration

- [x] 1.1 Add `data_query_meta_key: str | None` to `MCPClientSettings` in `app_properties.py`, with a `Field(description=...)`, a validator that requires it on a `statgpt` server and refuses it on every other type (errors name the server), and a `data_query_meta_key` accessor on `ApplicationProperties` mirroring `dataset_metadata_tool`; add `data_query_card_filter_max_line_chars: int` to `ApplicationProperties` (default `80`, `ge=10`, not nullable) with a `Field(description=...)`
- [x] 1.2 Add the new field to every `statgpt` fixture in `tests/test_app_properties.py`, `tests/test_mcp_client.py` and `tests/test_report_delivery.py`, and add tests for the four `data_query_meta_key` scenarios, using `acme.example.org/client` as the key, and for the three `data_query_card_filter_max_line_chars` scenarios (default, a set value, and a value below the floor or null rejected)
- [x] 1.3 Run `make format` to regenerate `docs/generated-app-schema.json`, and update the README paragraph listing what a `statgpt` server must name

## 2. Data-query capture

- [x] 2.1 Create `app/research/data_queries.py` with the pinned models of design decision 12 (`ClientMeta`, `ClientMetaQuery`, `StructuredResult`, `CandidateDataset`, `StructuredQuery`, `QueryFilter`, `FilterValue`, `RequestedPeriod`), and `DataQueryRecord` (pydantic; `meta` aliased `_meta`, `structured_content`; both `dict[str, Any] | None`; dumps by alias as `{"_meta": ..., "structured_content": ...}`) with its read-time properties: `data_explorer_url` (web URL only) from `meta`; `dataset_urn`, `series_count`, `filters` (each validated on its own) and `requested_period` from `structured_content`; `has_explorer_link`; and `returned_data` (`series_count` above zero, independent of the link). A field that fails validation reads as absent
- [x] 2.2 Add `DataQueryStore` (`dict[str, DataQueryRecord]` keyed by `queryId`, plus an `unreadable_payloads` counter) and the interceptor: it awaits `handler(request)`, skips other servers and error results, and on a result whose `_meta` carries the configured key joins the payload's `queries[]`, the structured result's `queries[]` and its `candidateDatasets[].query` by `queryId`, keeps each element whole, lets a later record replace an earlier one, counts any exception as one unreadable payload, logs nothing above DEBUG, and returns the same result object
- [x] 2.3 In `app/mcp_tools.py`, have `build_mcp_client` install the interceptor with each `statgpt` server's key, and add the store to `LoadedMcpTools` with an empty default; update `tests/test_research_dispatch.py` and `tests/test_status_stages.py`, which build `LoadedMcpTools`
- [x] 2.4 Unit-test the interceptor with synthetic `CallToolResult`s: two queries listed in different orders in the two parts, a constructed query with no URL, candidates, a query only in the structured result, another `_meta` key, no `_meta`, an unreadable payload, an error result, and a check that the returned result is unchanged

## 3. Citation lookups shared by review and delivery

- [x] 3.1 Create `app/research/citation_lookups.py` with `CitationLookups`: the catalogue answer, cached only after a successful call; a document-id → metadata cache where an id absent from a successful answer is recorded as unknown; `prefetch(draft)`, which fetches only what the draft cites (dataset URNs, the `datasetUrn` of each cited query with an explorer link, document ids) and the cache lacks, in one catalogue call and one resource read at most; and lookups that report "not looked up" after a failure
- [x] 3.2 Log a failed review-time lookup as one WARNING carrying the delivery's failure kind and a during-review marker, with no ids
- [x] 3.3 Unit-test the cache: one catalogue call across several drafts and the delivery, no re-read of documents already looked up, a failed call not cached and retried, and an omitted document id recorded as unknown

## 4. Marker parsing and annotations

- [x] 4.1 In `citations.py`, add the `[data_query <id>]` alternative to `_MARKER_RE`, `data_query_id` to `CitationMarker`, and `cited_data_query_ids`; in `report_length.py`, add `data_query` to `_CITATION_RE`
- [x] 4.2 Add `ConvertibleDataQueryCitation` (source key `("data_query", query_id)`) to the `ConvertibleCitation` union, and a `data_queries` parameter to `convert_citations` (default: none), converting a marker when its record `has_explorer_link`
- [x] 4.3 Build the data-query annotation: `text/html`, the explorer URL verbatim (never the catalogue's page URL), the pill `<name> dataset` (catalogue name for the structured `datasetUrn`, then `<urn> dataset`, both shortened before ` dataset`, then the unshortened marker text `data_query <id>` when there is no `datasetUrn`), the card title with the same fallbacks, no selector, and `body.quote` with one `* <dimensionName>: <names>` item per `in` filter (ids for missing names, each line cut to `data_query_card_filter_max_line_chars` with the ellipsis counted, the value passed in the way `max_pill_title_chars` is) plus one `From … until …` / `From …` / `Until …` item from the requested period; omit `body.quote` when the list is empty
- [x] 4.4 Give dataset and data-query cards the title `<name> dataset - last update <date>` (no date part when none was reported), remove `_dataset_quote` so a dataset citation sends no `body.quote`, and keep the pill free of the date
- [x] 4.5 Update the existing `* URN: …` assertions in `tests/test_citations.py`, `tests/test_dial_annotations.py`, `tests/test_references_section.py` and `tests/test_report_delivery.py`, and add tests for the data-query scenarios: conversion, verbatim id match, no-URL and unknown ids kept as text, a no-data query with a URL still converting, a query with no `datasetUrn` labelled `data_query <id>`, the page URL never used, run folding of two queries of one dataset, the filter quote, long lines at the default and at a configured budget, the period item forms, and a non-`in` operator left out

## 5. References section

- [x] 5.1 Compute `cited_dataset_urns` in report order from dataset markers and the structured `datasetUrn` of each cited query with an explorer link, without duplicates, and feed it to the catalogue read and `dataset_rows`; add a plain-text row reading `data_query <id>`, with empty other cells, for each cited query with an explorer link and no `datasetUrn`, at its first citation
- [x] 5.2 Stop copying a quote onto dataset row annotations; keep row labels as the dataset title alone
- [x] 5.3 Test a dataset cited only through queries, a dataset cited both ways listed once at its first citation, an uncaptured id and a query without an explorer link adding no row, the `data_query <id>` text row, and a row carrying no quote

## 6. Citation step

- [x] 6.1 In `research/runner.py`, build the `CitationLookups` beside the store, pass both to `build_research_graph`, and have `_run_citation_step` read the catalogue and document metadata through the lookups, pass the store to `convert_citations`, and keep the file-sharing call as it is
- [x] 6.2 Add `data_queries_requested` and `data_queries_resolved` to `_ReportDelivery` and to `log_citations_resolved` (defaulting to `0`, so the annotations demo's call is unchanged), keep both dataset counts over dataset-marker URNs only, and log the three data-query warnings with the messages in design decision 8 (the nothing-captured one documenting its three causes in its docstring, the unmatched-ids one suppressed when nothing was captured), not through `_log_citation_failure`
- [x] 6.3 Test the (8c) counts for a report citing only data queries, the nothing-captured warning without the ids-not-captured one, the ids-not-captured warning with its count, a captured query without a link counted without a warning, and that no log record carries a query id, URL or filter value

## 7. Report review checks

- [x] 7.1 In `report_rules.py`, add `ReportDataQueryRule` (its writer instruction states that only queries that returned data are cited, never candidate, not-run or empty ones; its violations follow the two report-composition wordings, judged on `returned_data` alone and never on the explorer link), and `ReportDatasetIdRule` and `ReportDocumentIdRule` (violations for URNs and document ids the lookups record as unknown; silent for ids not looked up and on channels without that server); extend `build_report_rules` to take the store and the lookups
- [x] 7.2 Thread the store and the lookups through `graph.py` and `nodes.py` to both places that build the rules, and in `report_review` await `lookups.prefetch(draft)` concurrently with the review model call before running the rules
- [x] 7.3 Test each report-composition scenario: a mistyped query id, a query without data (dataset-statement and other-statement guidance), a query that ran and returned nothing despite its link, a query with data, a query with data and no explorer link passing, an unknown URN, an unknown document id with the page left unchecked, an available but unretrieved id passing, and a failed lookup raising nothing

## 8. Prompts

- [x] 8.1 In `research/prompts.py`, add the `[data_query <id>]` form to the writer's citation section (the id the tool reported for the query, with `queryId` given as one example among others), re-scope `[dataset <urn>]` to statements about a dataset as a whole, and cover all three forms in "Match the citation to the source"
- [x] 8.2 Add the data-query form and a well-formed example to the review prompt's citation-format check, and tell the review model that the app checks the cited query, dataset and document ids

## 9. Documentation

- [x] 9.1 Update `docs/architecture.md`: what converts and when at report delivery, the interceptor in the MCP-tools paragraph, and the data-query and identifier checks among the app-owned review checks

## 10. Verification

- [x] 10.1 Run `make format`, `make lint` and `make test`, and fix what they report
- [x] 10.2 Grep the diff for client names, hosts, `_meta` namespaces and probe query ids, and confirm that only generic placeholders (`ACME`, `acme.example.org/client`, `IMF:WEO(1.0.0)`) appear
- [x] 10.3 Probe a data-query result and confirm that its structured result carries `seriesCount` and `datasetUrn` as decision 12 pins them. Then, with the local server running and a channel configured with the real key, drive one research turn with `scripts/send_conversation.py` (artifacts under `$TMPDIR`), and confirm that a `[data_query …]` pill opens the data explorer and its dataset appears once in References
