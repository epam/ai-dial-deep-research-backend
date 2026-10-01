## 1. Configuration model

- [x] 1.1 Remove `data_sources_descriptions` from `Prompts`, and make `Prompts` forbid unknown fields
- [x] 1.2 Add the optional `description` field to `MCPClientSettings`, with the field description the spec requires
- [x] 1.3 Add the `DocumentStats` model (`list_documents_tool`, `document_date_key`, `document_type_key`, `page_size`) and the optional `document_stats` field on `MCPClientSettings`, rejected on a non-`generic_rag` server
- [x] 1.4 Add `ApplicationProperties.document_server`, the counterpart of `dataset_server`
- [x] 1.5 Drop `data_sources_descriptions` from `dial_conf/core/applications-template.json`, and regenerate `docs/generated-app-schema.json` with `make format`

## 2. Document statistics

- [x] 2.1 Create `app/document_stats.py` with the page reader, the sequential listing with three attempts per page, and the incomplete-listing rules
- [x] 2.2 Implement the pure aggregation: count, valid dates, and per-type groups
- [x] 2.3 Implement the pure renderer of the document statistics block
- [x] 2.4 Log the INFO event and the incomplete-listing WARNING the spec requires

## 3. Data-sources assembly

- [x] 3.1 Rework `join_data_sources` to take the five optional parts in the spec's order
- [x] 3.2 Rework `fetch_data_sources` to run the documents part concurrently with the datasets and glossary parts, with one MCP client per server, and to make no call when no part has work
- [x] 3.3 Add the documents result to `DataSources`
- [x] 3.4 Rename the `{data_sources_descriptions}` template slot and its fill-ins in the preparation and playground code to `{data_sources}`

## 4. Tests

- [x] 4.1 Replace `data_sources_descriptions` in every test fixture, and add tests for the removed field, `description` and `document_stats` validation
- [x] 4.2 Add tests for the listing: one page, several sequential pages, a retried page, a page failing three times, an empty page, an answer without `total_count`, and cancellation
- [x] 4.3 Add tests for the aggregation and the renderer, covering the spec's scenarios
- [x] 4.4 Add tests for the assembly order, the absence rules and the empty string, and for the concurrency of the documents and datasets parts

## 5. Docs

- [x] 5.1 Update the data-sources diagram and prose in `docs/architecture.md`
- [x] 5.2 Update the module docstrings of `data_sources.py` and the field descriptions that name the removed field
- [x] 5.3 At archive time, update the Purpose of the `data-sources-discovery` main spec to cover the documents part

## 6. Verification

- [x] 6.1 Run `make format`, `make lint` and `make test`
- [x] 6.2 Run a local turn against a Generic RAG server with `document_stats` set, and check the rendered block in the traced prompt
- [x] 6.3 Move the topics map of each channel configuration in the private configuration repository into its document server's `description`, outside this repository

## 7. Revised assembly

- [x] 7.1 Reorder `join_data_sources` to document statistics, document description, datasets section, dataset description, glossary, and wrap each description in its own tag
- [x] 7.2 Reject a `generic_rag` server that sets neither `description` nor `document_stats`, and update the `description` field description
- [x] 7.3 Set the ACME topics map as the `description` of the template's document server
- [x] 7.4 Update the tests for the order, the tags and the new validation
- [x] 7.5 Update `docs/architecture.md` and the `data_sources.py` docstrings
- [x] 7.6 Drop the instruction to find a type's date span with list calls from the private channel's client rule, outside this repository
- [x] 7.7 Rerun a local turn and check the traced prompt

## 8. Review fixes

- [x] 8.1 Render an incomplete listing as the heading and `failed to obtain list of documents`, so the data-sources string is never empty
- [x] 8.2 Cap the listing at `MAX_DOCUMENT_PAGES` pages, log the `page_limit` failure kind, and name the cap in the `document_stats` and `page_size` field descriptions
- [x] 8.3 Reject a blank `description`
- [x] 8.4 Count the documents of the obtained pages in the INFO event, an incomplete listing's included
- [x] 8.5 State in `CLAUDE.md` that the template sets a property the instance fails validation without, such as the document server's `description`
- [x] 8.6 Update the tests, the module docstrings and `docs/architecture.md`
