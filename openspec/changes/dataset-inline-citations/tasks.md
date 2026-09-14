## 1. Configuration

- [x] 1.1 Add `dataset_metadata_tool` to `MCPClientSettings` in `src/dial_deep_research/app_properties.py`, an optional string with a `Field(description=...)` written for the operator filling in the DIAL admin form.
- [x] 1.2 Add the validator: only a `statgpt` server may set it, the error naming the offending server and its type. Declare it after `_validate_document_metadata`, so the connection-mode and file-sharing errors still come first.
- [x] 1.3 Add an `ApplicationProperties.dataset_metadata_tool` accessor returning the single configured name, or `None` when no server names one — the counterpart of the existing `file_sharing_tool` property.
- [x] 1.4 Update the `max_pill_title_chars` description: the budget governs the leading part of every pill label, a cited document's title and a cited dataset's name or URN alike, and the trailing part is appended after the shortening.
- [x] 1.5 Extend `tests/test_app_properties.py`: the field accepted on a `statgpt` server, absent accepted, a `generic_rag` server setting it rejected, and the accessor returning the name and `None` for a configuration that names none.

## 2. Reading the dataset catalogue

- [x] 2.1 Write `src/dial_deep_research/app/research/dataset_metadata.py`: call the configured tool tool-call-shaped with no arguments, read the `datasets` array out of the `ToolMessage`'s structured result, and return one `DatasetSource` per cited id the answer reported with a usable page URL.
- [x] 2.2 Give it the failure shape `file_sharing.py` has: one exception type carrying a stable `kind` token, with kinds for an error-status answer, a missing structured result and an unreadable one, and no logging anywhere in the module. The error status is read off the `ToolMessage` rather than raised, because this tool keeps the agent's error handling (see `design.md`, decision 6).
- [x] 2.3 Write `tests/test_dataset_metadata.py`: the call carries no arguments; a well-formed answer yields the name, URL and last-update date; extra fields in a record are ignored; a record with no URL, a storage-relative URL, an unknown id and a name-less record each behave as specified; an error status, a missing structured result and an answer of the wrong shape each raise the typed error with the expected kind.

## 3. Tool loading

- [x] 3.1 Add `dataset_metadata_tool` to `LoadedMcpTools` in `src/dial_deep_research/app/mcp_tools.py`, resolved from the server's full advertised list, left in the agent's tool list, and with its error handling untouched.
- [x] 3.2 Extend `tests/test_mcp_client.py`: naming the tool does not hide it from the agent, a filter omitting it still finds it for the app, a filter naming it keeps it with the agent, its error handling stays on, and a tool the server does not advertise is reported as absent.

## 4. Conversion and the annotation payload

- [x] 4.1 Populate `CitationMarker.dataset_id` from the regex group the parser already captures, and add `cited_dataset_ids` beside `cited_document_ids` in `src/dial_deep_research/app/research/citations.py`.
- [x] 4.2 Add `DatasetSource` (page URL, optional name, optional last-update date) and `is_web_url`, and split `_ConvertibleCitation` into a document and a dataset model with a union, `_build_annotation` dispatching on which it holds.
- [x] 4.3 Add the `dataset_sources` parameter to `convert_citations`, defaulting to empty so the demo keeps calling it unchanged, and convert a dataset citation when its URN resolved an absolute `http` or `https` URL.
- [x] 4.4 Build the dataset annotation: `text/html` attachment type, the portal URL carried verbatim, `<name> dataset` on the card and the shortened name with `dataset` appended on the pill, the URN as the leading part when no name resolved, a `body.quote` Markdown list carrying the URN and the last-update date when one was reported, and no `body.selector`.
- [x] 4.5 Make `AnnotationAttachment.type` explicit per citation, `AnnotationBody.selector` optional and `AnnotationBody.quote` optional, and dump the payload with `exclude_none=True` in `send_annotations` so an absent field is absent from the wire rather than null.
- [x] 4.6 Add the two dataset counts to `log_citations_resolved`, so the (8c) event carries them beside the document counts.
- [x] 4.7 Extend `tests/test_citations.py` and `tests/test_dial_annotations.py`: the dataset payload in full, the unnamed-dataset fallback, the same label shape resolved and unresolved, the pill budget applied to a name and to a URN, the quote with and without a date, an unreported id and a storage-relative URL keeping their marker text, exact URN matching, a document and a dataset folding into one pill, and the absent fields missing from the dumped payload.

## 5. The citation step

- [x] 5.1 Issue the file-sharing call, the document-metadata read and the dataset-metadata call in one `asyncio.gather` in `src/dial_deep_research/app/research/runner.py`, asking the metadata resource about every cited document and labelling only from the titles of documents that resolved a URL.
- [x] 5.2 Add the dataset resolution's failure handling: a DEBUG record when no tool is configured, one WARNING naming the kind when the tool is not advertised, the call raises, or the answer cannot be read, and no record at all for a dataset the catalogue reports without a page URL.
- [x] 5.3 Add the two dataset counts to `_ReportDelivery` and pass the configured tool and its name into the delivery from `run`.
- [x] 5.4 Pass the two zero dataset counts explicitly at the demo's `log_citations_resolved` call in `src/dial_deep_research/app/annotations_demo/completion.py`, as its `documents_titled=0` already is.
- [x] 5.5 Extend `tests/test_report_delivery.py`: a dataset citation delivered as a pill, the three resolutions issued together, the title read asking for every cited id and showing only the resolved ones, each dataset failure kind, a dataset without a URL warning nothing, and the (8c) event carrying the dataset counts.

## 6. The report writer's prompt

- [x] 6.1 State in `REPORT_SYSTEM_PROMPT` (`src/dial_deep_research/app/research/prompts.py`) what identifies each kind of source: a document by its id and the cited page index, a dataset by its URN written whole, never abbreviated, case-changed, percent-encoded or stripped of its version. Keep the 100-character line limit.
- [x] 6.2 Give the report-review checklist's citation-format check the same wording, so the two halves of the contract cannot disagree.

## 7. Documentation and generated artifacts

- [x] 7.1 Update the report-delivery section of `docs/architecture.md`: what makes a dataset citation convertible, where its name and page address come from, what its annotation carries, and that the three resolutions are issued together. Describe the current behaviour without narrating the change.
- [x] 7.2 Run `make format` to regenerate `docs/generated-app-schema.json` from the new field, and confirm `make lint` reports no drift.
- [x] 7.3 Confirm `dial_conf/core/applications-template.json` still needs no edit, the new property being optional, and that `tests/test_app_properties.py` still passes against it.

## 8. Verification

- [x] 8.1 Run `make format`, `make lint` and the full test suite.
- [x] 8.2 Run `openspec validate dataset-inline-citations --strict`.

## 9. Every server must name the surface that resolves its citation ids

- [x] 9.1 Require `dataset_metadata_tool` on a `statgpt` server in `src/dial_deep_research/app_properties.py`, beside the rule refusing it on every other type, with an error that says why a dataset server cannot serve uncitable datasets.
- [x] 9.2 Require `document_metadata_resource` and `document_title_key` on a `generic_rag` server, keeping the set-together error for a half-configured pair so the two mistakes read differently.
- [x] 9.3 Rewrite the three field descriptions and the two `ApplicationProperties` accessors: `None` now means no server of that type is configured, not a server that named nothing.
- [x] 9.4 Add both fields to the `generic_rag` entry of every channel in `dial_conf/core/applications-template.json`, so a contributor's seeded configuration validates as it stands.
- [x] 9.5 Reword the citation step's two DEBUG records and their docstrings in `src/dial_deep_research/app/research/runner.py`: the absence they report is a channel that serves no documents or no datasets.
- [x] 9.6 Update every test fixture that builds a server of either type, and flip the four tests that asserted the fields were optional into the rejections they now are.
- [x] 9.7 Update the delta specs: the `application-config-schema` requirement for the dataset tool, a new MODIFIED requirement for the document-metadata pair, the two contract requirements in `report-citations`, the failure and DEBUG rules there, and the two `logging-policy` scenarios.
- [x] 9.8 Rewrite design decision 7 and the migration plan, which recorded the fields as optional and the change as needing no migration, and correct the proposal's optional-field bullets and impact list.
- [x] 9.9 Update the report-delivery section of `docs/architecture.md`, which stated both surfaces as optional.
