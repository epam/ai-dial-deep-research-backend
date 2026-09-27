## 1. Rename the dataset-metadata tool to the list-datasets tool (D15)

- [ ] 1.1 Rename `MCPClientSettings.dataset_metadata_tool` to `list_datasets_tool` in `app_properties.py`: the field, its description, `_validate_dataset_metadata_tool` and its error messages, and the `ApplicationProperties.dataset_metadata_tool` accessor
- [ ] 1.2 Rename `LoadedMcpTools.dataset_metadata_tool` and the log message that names the tool in `app/mcp_tools.py`, and every use in `app/research/runner.py` and `app/research/citation_lookups.py`; keep the failure-kind tokens and the module name `research/dataset_metadata.py` (D15)
- [ ] 1.3 Update `tests/test_app_properties.py`, `tests/test_mcp_client.py`, `tests/test_status_stages.py` and `tests/test_research_dispatch.py` for the new name
- [ ] 1.4 Update the sentence in `README.md` that names `dataset_metadata_tool`, and the mention in `docs/architecture.md`

## 2. Configuration

- [ ] 2.1 Add the optional `dataset_structure_tool` field to `MCPClientSettings`, with a validator allowing it only on a `statgpt` server, a description saying the datasets display is designed for about ten datasets and that leaving it unset shows the list alone, and an `ApplicationProperties` accessor returning it with its server's name (spec `application-config-schema`, "A statgpt MCP server may declare its dataset-structure tool")
- [ ] 2.2 Add the `GlossaryTools` model (`list_terms_tool`, `definitions_tool`, `max_terms_per_definitions_call` with `ge=1`, `references_table: ReferencesTable`, unknown fields rejected), the optional `glossary` field with its `statgpt`-only validator, its description telling the admin when to set it, and an `ApplicationProperties.glossary` accessor (spec `application-config-schema`, "A statgpt MCP server may declare its glossary tools")
- [ ] 2.3 Rewrite the description of `Prompts.data_sources_descriptions` to say it holds only what the app does not fetch, naming the list of datasets, their structures and the glossary
- [ ] 2.4 Extend the field descriptions of `ReferencesTable` and `ReferenceColumn` to cover the glossary table: a key can be a field of a glossary term's record, and the first column falls back to the cited term
- [ ] 2.5 Add validator tests to `tests/test_app_properties.py`: each new field accepted on a `statgpt` server, rejected on a `generic_rag` server, and an incomplete `glossary` rejected; run `make format` to regenerate `docs/generated-app-schema.json`

## 3. Shared catalogue parsing and citation seeding (D14)

- [ ] 3.1 Split `read_catalogue` in `research/dataset_metadata.py` so that the part turning a structured result into `dict[str, DatasetSource]` takes a dict, used both by the `ToolMessage` path and by the turn-start fetch
- [ ] 3.2 Let `CitationLookups` start with a catalogue passed in, keeping the lazy fetch when none is passed (spec `report-citations`, "Cited identifiers are looked up once per turn and shared by the review and the delivery")
- [ ] 3.3 Test in `tests/test_dataset_metadata.py` and `tests/test_citation_lookups.py`: a seeded catalogue makes no list-datasets call during review or delivery, and an unseeded one fetches as today

## 4. The datasets part of the fetch (D1–D4, D6, D10–D13)

- [ ] 4.1 Create `app/data_sources.py` with one MCP call helper: a client from `build_mcp_client` restricted to the `statgpt` server, one `client.session()` per call, `session.call_tool`, `asyncio.timeout(20)` around session open and call, up to three attempts with about 1 s and 2 s of jittered backoff, a failed attempt on raise, `isError`, timeout or an invalid structured result, `CancelledError` never caught, and the failure kind taken from the first exception leaf or `mcp_error`, `timeout`, `invalid_result`
- [ ] 4.2 Implement the list-datasets call with no arguments, validated as a `datasets` array (spec `data-sources-discovery`, "The list of datasets is requested with at most three attempts")
- [ ] 4.3 Implement the structure calls when `dataset_structure_tool` is set: one call per distinct string `id`, all concurrent, argument `{"dataset_id": <id>}`, each with its own three attempts, and a non-object answer counted as a failed attempt (spec "Dataset structures are requested concurrently, one call per dataset")
- [ ] 4.4 Render the datasets section: `Datasets:` and the list's structured result as one-line JSON with `ensure_ascii=False`, then `Dataset structures:` and the array in list order with `{"dataset_id": <id>, "error": "failed to obtain dataset structure"}` for a failed one, or `failed to obtain list of datasets` (spec "The datasets section is rendered as one string")
- [ ] 4.5 Define the `DataSources` value object: the data-sources string, the parsed catalogue (`None` when the list failed), whether a structures block was rendered, and the glossary's listed and unresolved counts
- [ ] 4.6 Log one INFO `Datasets fetched` event with the server, list attempts, listed count (absent on a failed list), structures requested, obtained and not obtained, and duration, plus the two WARNINGs, carrying no dataset id or name (spec "The datasets fetch is recorded in the logs")
- [ ] 4.7 Write `tests/test_data_sources.py` for the datasets part: a transient failure retried, three failures giving the failure text and no structure call, a stalled call cut off at its deadline, only the failed structure call repeated, a non-object answer, cancellation propagating, the rendering and failure entries, and the log records

## 5. The glossary part of the fetch (D2–D7, D10)

- [ ] 5.1 Create `app/glossary.py`: the list-terms call with three attempts, validated as a `terms` array of records with a `term` string, using the call helper from 4.1
- [ ] 5.2 Implement the definitions rounds: deduplicate by trimmed, case-folded name, batches of at most `max_terms_per_definitions_call` sent concurrently, at most three rounds re-requesting the unresolved terms, `notFound` and unmatched records handled as the spec says (spec "Definitions are requested in concurrent batches, in at most three rounds")
- [ ] 5.3 Render `Glossary terms:` and the one-line JSON array with `index` first, the record's fields in server order, and `"definition": null` after `term` for an unresolved term, or `failed to obtain list of terms` (spec "The glossary is rendered as one string")
- [ ] 5.4 Log the `Glossary fetched` event and its two WARNINGs with counts only
- [ ] 5.5 Test the glossary part in `tests/test_glossary.py`: batching, rounds, the rendering, a failed list, and the log records

## 6. The data-sources string and the turn wiring (D1, D8)

- [ ] 6.1 In `app/data_sources.py`, run the datasets part and the glossary part concurrently and join `prompts.data_sources_descriptions`, the datasets section and the glossary with blank lines into the data-sources string; a channel without a `statgpt` server gets the hand-written text unchanged and no call
- [ ] 6.2 In `DeepResearchCompletion._run_turn` (`app/completion.py`), run the fetch after the `research_started` check and before `PrepAgentRunner.run`, and pass the `DataSources` to both runners
- [ ] 6.3 Pass the `DataSources` into `PrepAgentRunner.run`, give `build_prep_agent` a parameter for it in place of reading `prompts.data_sources_descriptions`, and hand the combined string to `PrepTools`
- [ ] 6.4 In `ResearchRunner.run`, seed `CitationLookups` with the catalogue and pass the data-sources string to `build_research_graph` and on to every node in `research/nodes.py`
- [ ] 6.5 Run the fetch at the start of `PlaygroundRunner.run` and pass the string to `build_playground_agent`
- [ ] 6.6 Test that a handed-off conversation makes no data-sources call, that a turn makes one fetch whose result reaches both preparation and research, and that the playground runs its own fetch

## 7. Preparation prompts (D18)

- [ ] 7.1 Fill `PREP_AGENT_SYSTEM` and `QUERY_REVIEW_SYSTEM` with the data-sources string
- [ ] 7.2 Add a placeholder to `PREP_AGENT_SYSTEM`, filled only when the list failed, with the instruction to go on with clarification and the plan, to add a plan item that asks research to search the available datasets and says no dataset can be suggested yet, and to treat the rule that the plan must name a covering data source as not applying to a source whose listing failed
- [ ] 7.3 Test that the instruction appears only on a failed list, that neither preparation prompt tells the model to call a dataset tool, and that `PLAN_REVIEW_SYSTEM` receives no data sources

## 8. Research and playground prompts (D9, D16, D19)

- [ ] 8.1 Add a `<data_sources>` block to `RESEARCH_AGENT_SYSTEM_PROMPT`, `RESEARCH_REVIEW_SYSTEM_PROMPT`, `REPORT_SYSTEM_PROMPT` and `REPORT_REVIEW_SYSTEM_PROMPT`, filled once per turn
- [ ] 8.2 Build the research agent's dataset-tools instruction from the bound tool names and `DataSources`: do not call a tool for an answer the section shows; call it, at most three times per list or per dataset, when the app's calls failed; the failed-list structure part only when the list tool is bound too (spec "An agent that can call the dataset tools is told which calls are done and which failed")
- [ ] 8.3 Build the glossary instruction: call the list-terms tool at most three times when the list failed, and request the definitions of relevant terms without one, each in at most three calls, each part only when its tool is bound (spec "An agent that can call the glossary tools repeats what the app's fetch missed")
- [ ] 8.4 Give the playground agent only the failed-call parts of both instructions
- [ ] 8.5 Tell the report writer that facts from the data-sources string count as retrieved sources and are cited with the form of the source they describe, that publication descriptions are never cited, and nothing about unqueried datasets (spec `report-composition`, "The data sources in the system prompt count as retrieved sources")
- [ ] 8.6 On a glossary channel, give the report writer the `[glossary <term>]` form and the terminology rule with its caveat that the data-sources glossary may lack terms and that the research's glossary results count, built from one constant shared with the reviewer's check
- [ ] 8.7 Give the report reviewer the `[glossary <term>]` form, the `<glossary_tool_results>` block with the text of the research agent's successful results of the two configured glossary tools, selected from the graph's `messages` by tool name, and the terminology check when the fetch listed terms or that block is not empty
- [ ] 8.8 Extend the prompt tests: each prompt carries the data-sources string, each instruction part appears exactly under its conditions, and no prompt on a channel without a glossary mentions the glossary form

## 9. Citations and the References section (D21)

- [ ] 9.1 Write the References tables in a fixed order, datasets then documents, in `ApplicationProperties.references_tables` and `research/runner.py`, and update the docstring that says the operator decides the order
- [ ] 9.2 Parse `[glossary <term>]` markers in `research/citations.py` with the keyword read case-insensitively and spaces allowed, on one line, and on a channel without a glossary leave them as text
- [ ] 9.3 In the citation conversion, move each run's glossary markers out of the run so its other markers fold as before, and end the run with one readable group: `(<term> - glossary term)` for one term, `("<term 1>", "<term 2>" - glossary terms)` for several, duplicates merged (spec `report-citations`, "Cited glossary terms are listed in a glossary table")
- [ ] 9.4 Build the glossary table in `research/references.py` after the server tables: one row per distinct cited term in first-citation order, the record from the app's fetch, then the agent's term-definitions results, then its list-terms results, a record with a definition preferred, and the term alone when nothing matches; columns from `glossary.references_table`
- [ ] 9.5 Count a glossary marker as an inline citation in `research/report_length.py` by adding `glossary` to the exempted keywords
- [ ] 9.6 Test the table order, a glossary marker inside a dataset run still giving one pill, the grouped form, the table's record sources and fallbacks, a report citing only a glossary term, and the word count

## 10. Documentation and checks

- [ ] 10.1 Update `docs/architecture.md`: the data-sources fetch at the start of the turn, the data-sources string as an input of every research graph node, the fixed order of the References tables, and the glossary table
- [ ] 10.2 Run `make format`, `make lint` and `make test`, and fix what they report
- [ ] 10.3 Check the diff against `no_sensitive_info.md`: no client name, configuration, deployment fact or live measurement in code, tests, docs or the change's artifacts
- [ ] 10.4 Run `openspec validate discover-data-sources --strict`
