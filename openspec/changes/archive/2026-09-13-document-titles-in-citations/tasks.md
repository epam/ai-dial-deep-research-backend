## 1. Configuration

- [x] 1.1 Add `document_metadata_resource` and `document_title_key` to `MCPClientSettings` in `src/dial_deep_research/app_properties.py`, both optional strings, each with a `Field(description=...)` written for the operator filling in the DIAL admin form.
- [x] 1.2 Add the validator: only a `generic_rag` server may set either, the two are set together or not at all, and the template carries exactly one `{document_ids}` placeholder. Declare it after the existing `_validate_file_sharing_tool` so the more fundamental misconfiguration is still reported first.
- [x] 1.3 Add an `ApplicationProperties` accessor returning the configured server name, resource template and title key as one value, or `None` when no server names them — the counterpart of the existing `file_sharing_tool` property.
- [x] 1.4 Extend `tests/test_app_properties.py`: both fields accepted on a `generic_rag` server, both absent accepted, each one alone rejected, a template with no placeholder rejected, a `statgpt` server setting either rejected, and the accessor returning `None` for a configuration that names neither.

## 2. Reading the metadata resource

- [x] 2.1 Write `src/dial_deep_research/app/research/document_metadata.py`: build the concrete URI by replacing the literal `{document_ids}` with the ids joined by commas, read it through `MultiServerMCPClient.get_resources(server_name, uris=[uri])`, parse the returned blob's data as JSON, validate it as an id-to-metadata object, and return `{document_id: title}` for every document carrying a non-empty string under the configured key.
- [x] 2.2 Give it the failure shape `file_sharing.py` has: one exception type carrying a stable `kind` token, kinds for a failed read and for an unreadable answer, and no logging anywhere in the module.
- [x] 2.3 Write `tests/test_document_metadata.py`: the URI is built from the cited ids in order; a well-formed answer yields the titles; string and integer keys are both accepted; a document absent from the answer, one missing the configured key, one whose value is empty and one whose value is not a string each yield no title without failing the read; a read that raises and an answer of the wrong shape each raise the typed error with the expected kind.

## 3. Labels in the citation step

- [x] 3.0 Widen the document keyword in `_DOCUMENT_MARKER` (`src/dial_deep_research/app/research/citations.py`) to `doc(?:ument)?`, so a marker copied through from a server's own attribution still converts. The pattern already runs case-insensitively and already tolerates the spacing.
- [x] 3.0a Widen `report_length._CITATION_RE` the same way, to `(?:doc(?:ument)?|dataset)\b`. Its `doc\b` does not match `document`, so without this the long spelling would be counted as report words while the citation parser treats it as a citation, and the two would disagree about what a citation is. Extend `tests/test_citations.py` and `tests/test_report_length.py` for the long spelling in both.
- [x] 3.1 Add a `document_titles` mapping parameter to `convert_citations` in `src/dial_deep_research/app/research/citations.py`, defaulting to empty.
- [x] 3.2 Build the label in `_build_annotation` from the title and the page when a title is present, and from the marker's document id and page when it is not. Both `body.title` and `body.source.attachment.title` carry the same string, and neither is shortened. Update the module docstring and the function docstring, which both currently state that the app holds no document title.
- [x] 3.3 Extend `tests/test_citations.py`: a titled document labels both fields with the title and the page; an untitled one falls back to the marker text; a run mixing a titled and an untitled document labels each of its annotations correctly; a long title is carried whole with no ellipsis; two pages of one titled document produce two entries differing only in the page.

## 4. Wiring in the research turn

- [x] 4.1 Return the per-request `MultiServerMCPClient` from `load_mcp_tools` on `LoadedMcpTools` in `src/dial_deep_research/app/mcp_tools.py`, and update its docstring to say what the client is for after the tools have been fetched.
- [x] 4.2 In `src/dial_deep_research/app/research/runner.py`, read the titles after `_share_cited_documents` returns and before `convert_citations`, asking only for the ids that resolved a URL, and skip the read entirely when nothing resolved or no server names a resource.
- [x] 4.3 Add the failure handling: a DEBUG record when no resource is configured, one WARNING naming the kind when the read raises or the answer is unreadable, and no record at all for a document that simply carries no title. Every citation converts either way.
- [x] 4.4 Add the titled-document count to `_ReportDelivery` and to `log_citations_resolved`, so the (8c) INFO event carries it beside the resolved count.
- [x] 4.5 Extend `tests/test_report_delivery.py`: a turn where every document resolves a title, one where the read raises and every pill is still drawn with marker labels, one where the answer is unreadable, one where a single document has no title and nothing warns, and one confirming the read asks only for the ids that resolved a URL.

## 5. The report writer's prompt

- [x] 5.1 Rewrite the citation paragraph of `REPORT_SYSTEM_PROMPT` in `src/dial_deep_research/app/research/prompts.py` so it describes what a tool's attribution conveys and presents concrete spellings — the tuple form and the labelled form — as examples among others, with no sentence claiming the tools use one particular form. Keep the 100-character line limit.
- [x] 5.2 Check the report-review checklist in the same file for any wording that names one server's attribution form, and correct it if it does.

## 6. Documentation and generated artifacts

- [x] 6.1 Update the report-delivery section of `docs/architecture.md` with the metadata read: where it sits in the step, what it asks for, and what a failure costs. Describe the current behaviour without narrating the change.
- [x] 6.2 Run `make format` to regenerate `docs/generated-app-schema.json` from the two new fields, and confirm `make lint` reports no drift.
- [x] 6.3 Confirm `dial_conf/core/applications-template.json` still needs no edit, since both new properties are optional, and that `tests/test_app_properties.py` still passes against it.

## 7. Verification

- [x] 7.1 Run `make format`, `make lint` and the full test suite.
- [x] 7.2 Run `openspec validate document-titles-in-citations --strict`.
- [x] 7.3 Drive a real report through a configured channel and confirm the pill and the popup entry both read the publication title with the cited page, using `scripts/send_conversation.py` against a running server.
- [x] 7.4 Measured in DIAL Chat against a real report: the client does **not** shorten a long pill label, and the pills ran off. The app therefore shortens the pill's copy of the title to `max_pill_title_chars`, a channel property defaulting to 20, and appends the page afterwards; the citation card keeps the title whole.
