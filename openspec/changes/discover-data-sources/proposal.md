## Why

The description of a channel's data sources is written by hand today, in
`prompts.data_sources_descriptions`, and deploying to a new environment means an admin rewrites it
for that environment. For datasets the text is a hand copy of what the StatGPT MCP server already
reports: a channel's description typically carries a datasets section that copies the
list-datasets tool's answer. The copy goes stale whenever the catalogue changes, and it never
carries the datasets' structures, so the research agent spends iterations calling the list and
structure tools to learn what the server could have told the app once. A dataset's catalogue record
and its structure together are on the order of 650 tokens, so a catalogue of about ten datasets
costs on the order of 6,500 tokens (estimated with the `o200k_base` encoding).

A channel can also require that a report uses its glossary's terminology. A model sees a glossary
term today only if the research agent happens to call a glossary tool, so nothing guarantees that
the preparation agent, the report writer or the report reviewer ever see the glossary. A glossary
of a hundred terms, each defined in a short paragraph, is on the order of 5,000 tokens, which is
small enough to put into every call's context.

So the app discovers the data sources itself: once per turn, before preparation, it fetches the
list of datasets, their structures and the glossary from the channel's StatGPT MCP server, and puts
them next to the hand-written text. The StatGPT backend stays unchanged: the app calls tools the
server already exposes.

## What Changes

- **BREAKING: `dataset_metadata_tool` is renamed to `list_datasets_tool`**, and the specs call the
  tool the "list-datasets tool". Its rules do not change: a `statgpt` server must name it, and no
  other server type may. A channel configuration that still sets `dataset_metadata_tool` fails
  validation, so every deployed channel must rename the field when it takes the new image.
- **A statgpt MCP server may name a `dataset_structure_tool`.** It is optional, only a `statgpt`
  server may set it, and, like the list, it is designed for a catalogue of about ten datasets. Its contract is one `dataset_id` argument and the dataset's
  structure as the MCP structured result.
- **The app runs one data-sources fetch per turn, before the preparation agent runs**, on every
  channel with a `statgpt` server. It calls the list-datasets tool with at most 3 attempts. When a
  dataset-structure tool is named, it then calls that tool once per listed dataset, concurrently,
  with at most 3 attempts per call. The glossary fetch runs in the same fetch, concurrently with the
  datasets.
- **The datasets section is rendered as one string**: `Datasets:` followed by the list-datasets
  structured result as one-line JSON, exactly as the server sent it, then, when structures were
  fetched, `Dataset structures:` followed by a JSON array of the structure answers in list order. A
  structure that was not obtained becomes `{"dataset_id": ..., "error": "failed to obtain dataset
  structure"}`, and a failed list becomes `failed to obtain list of datasets`.
- **The data-sources string** is `prompts.data_sources_descriptions`, then the datasets section,
  then the glossary. It goes to every model call that receives `data_sources_descriptions` today —
  the preparation agent, the query review inside `update_query`, and the playground agent — and to
  every node of the research graph: the research agent, research review, the report writer and the
  report reviewer. None of the research nodes receives `data_sources_descriptions` today.
- **The field description of `data_sources_descriptions` tells the admin to describe only what
  the app does not fetch**, since the app appends the datasets and the glossary after it.
- **The research agent and the playground agent are told which dataset calls succeeded and which
  failed.** An answer the datasets section shows is not requested again. A call that failed after
  the app's retries is the agent's to make, as the fallback.
- **A failed list of datasets does not stop preparation.** The preparation agent is told to go on
  aligning the plan and, when the query needs dataset data, to add a plan item asking research to
  search the available datasets, saying that no specific dataset can be suggested because the list
  could not be obtained. Neither preparation call is told to call a dataset tool, because
  preparation has no MCP tools.
- **Showing the whole catalogue is designed for channels with about ten datasets.** The app does
  not cap or shorten the catalogue, and a channel with a larger one is deferred. A channel can leave
  `dataset_structure_tool` unset to show the list without the structures.
- **The data sources in the system prompt count as retrieved sources.** The report writer may cite
  a fact from the data-sources string, such as a dataset's metadata, with the citation form of the
  source it describes, and the reviewer does not flag it. Nothing tells the writer to cite, or not
  to cite, datasets the research did not query.
- **The turn-start list answer initializes the catalogue the citations read.** The report review's
  identifier checks and the report delivery reuse it, so a turn that cites datasets makes no second
  list-datasets call. When the turn-start call failed, they fetch the catalogue as they do today.
- **Glossary**: the glossary part of the fetch,
  its rendering, and the terminology rule for the report writer and its check for the report
  reviewer, as planned before. The research agent and the playground agent are told to repeat what
  the app's glossary fetch missed, a failed list of terms or missing definitions, with at most three
  calls each. Research-review and the report writer see the results of those calls in the
  transcript, and the report reviewer receives the successful ones, which the app selects by the
  configured glossary tool names.
- **The References tables come in a fixed order**: datasets, then documents, then the glossary,
  whatever order the servers are configured in.
- **Glossary citations**: a fact from a glossary definition is cited
  `[glossary <term>]`, a marker like the other three. Before delivery the app moves the glossary
  markers of each run of adjacent citations to the run's end, so they never split a pill, and
  rewrites them into one readable group: `(<term> - glossary term)`, or
  `("<term 1>", "<term 2>" - glossary terms)` for several. The References section
  gets a glossary table listing every cited term with its record, configured by
  `glossary.references_table` like a server's table. The report writer and the report reviewer both
  know the form. The `glossary` field's description tells the admin to set it whenever the server
  exposes glossary tools that the agent would be offered anyway. Publication descriptions are never
  cited, only publications.
- A channel with no `statgpt` server makes no data-sources call. The only difference it sees is
  that every node of the research graph now receives `data_sources_descriptions`.

## Capabilities

### New Capabilities

- `data-sources-discovery`: the per-turn data-sources fetch from the channel's StatGPT MCP server:
  the list-datasets call and its retries, the dataset-structure tool's contract and the structure
  calls, the glossary's list-terms call and definition rounds, the rendered datasets section and
  glossary, the data-sources string and the calls that receive it (including the playground agent,
  whose inputs no other spec owns), the instructions given to the agents that can call these tools,
  the rule that no fetch failure fails the turn, and the log records of the fetch.

### Modified Capabilities

- `application-config-schema`: the requirement "MCP server declares its dataset-metadata tool" is
  renamed to "MCP server declares its list-datasets tool" and names the field `list_datasets_tool`.
  Two new requirements: "A statgpt MCP server may declare its glossary tools" and "A statgpt MCP
  server may declare its dataset-structure tool". "Application properties model" says what
  `data_sources_descriptions` should hold. Four more requirements change only the tool's name.
- `report-citations`: "Cited datasets are named and linked through a contracted dataset-metadata
  tool" is renamed to "… list-datasets tool" and states that the call is made at the start of every
  turn. "Cited identifiers are looked up once per turn and shared by the review and the delivery"
  takes the catalogue from that call, and "A cited data query cites the dataset it ran against"
  selects from it. The renamed "The list-datasets tool is called by the app and stays available to
  the agent" scopes its full-tool-list lookup to the citation step, and "The References section is
  built by the app from the cited sources' metadata" fixes the order of its tables and adds the
  glossary table. Five more requirements
  change only the tool's name. A new requirement, "Cited glossary terms are listed in a glossary
  table", owns that table.
- `clarification-and-plan-alignment`: "Every preparation LLM call's inputs and outputs are
  specified" says that the preparation agent and the query review receive the data-sources string.
- `research-execution`: "Every research LLM call's inputs and outputs are specified" says that all
  four research graph calls receive the data-sources string, and which instructions the research
  agent gets. "Report node writes the final cited report and is the only assistant content" adds
  the glossary citation form.
- `report-composition`: a new requirement "A report uses the glossary's terminology", and "The
  rules the app can check itself are checked in Python, not by a model" adds the data-sources
  string to what the reviewer receives.
- `dial-agent-with-mcp`: "Tool-calling agent over MCP-loaded tools" says that a turn on a channel
  with a dataset server constructs a per-turn MCP client before preparation, and that the fetch
  names its tools directly instead of polling `tools/list`.
- `logging-policy`: "INFO request skeleton" lists the datasets-fetched and glossary-fetched events,
  and it and "A References section that could not be built is one WARNING" use the new tool name.
- `source-attribution`: "A cited identifier resolves against its server verbatim" uses the new
  tool name.

## Impact

- `src/dial_deep_research/app_properties.py`: the rename of `dataset_metadata_tool` to
  `list_datasets_tool` (the field, its validator and the `ApplicationProperties` accessor), the new
  `dataset_structure_tool` field and its validator, the `GlossaryTools` model (with its
  `references_table`) and the `glossary` field, and the new description of
  `Prompts.data_sources_descriptions`.
- `src/dial_deep_research/app_properties.py` (`references_tables` and its docstring) and
  `app/research/runner.py`: the fixed order of the References tables.
- `src/dial_deep_research/app_properties.py`: the field descriptions of `ReferencesTable` and
  `ReferenceColumn`, which cover the glossary table too.
- `src/dial_deep_research/app/research/citations.py`, `app/research/references.py`,
  `app/research/report_length.py`: finding glossary markers and
  rewriting them into the readable form, the glossary table, and exempting the marker from the word
  count.
- `src/dial_deep_research/app/data_sources.py` (new): the data-sources fetch, the list and structure
  calls with their attempts, the rendering of the datasets section, and the helper that builds the
  data-sources string.
- `src/dial_deep_research/app/glossary.py` (new): the glossary fetch and its rendering.
- `src/dial_deep_research/app/completion.py`: runs the fetch before preparation and passes its
  result to both runners.
- `src/dial_deep_research/app/mcp_tools.py`: the rename (`LoadedMcpTools.dataset_metadata_tool` and
  the log message that names the tool).
- `src/dial_deep_research/app/research/dataset_metadata.py`: the catalogue parsing is shared with
  the fetch, which reads a raw MCP result rather than a `ToolMessage`.
- `src/dial_deep_research/app/research/citation_lookups.py`: `CitationLookups` accepts the
  turn-start catalogue.
- `src/dial_deep_research/app/research/runner.py`: the rename, and seeding `CitationLookups`.
- `src/dial_deep_research/app/preparation/runner.py`, `app/preparation/agent.py`,
  `app/preparation/tools.py`: receive the data-sources string in place of
  `prompts.data_sources_descriptions`; `build_prep_agent` gains a parameter for it.
- `src/dial_deep_research/app/preparation/prompts.py`: the failed-list instruction placeholder in
  `PREP_AGENT_SYSTEM`.
- `src/dial_deep_research/app/research/graph.py`, `app/research/nodes.py`: pass the data-sources
  string to every node of the research graph.
- `src/dial_deep_research/app/research/prompts.py`: a `<data_sources>` block in
  `RESEARCH_AGENT_SYSTEM_PROMPT`, `RESEARCH_REVIEW_SYSTEM_PROMPT`, `REPORT_SYSTEM_PROMPT` and
  `REPORT_REVIEW_SYSTEM_PROMPT`, the dataset-tools instruction, and the statement that the
  data-sources string counts as a retrieved source, the glossary instruction, the
  glossary-terminology rule and its check, the glossary citation form in the writer's and the
  reviewer's prompts, and the `<glossary_tool_results>` block.
- `src/dial_deep_research/app/playground/runner.py`, `app/playground/agent.py`,
  `app/playground/prompts.py`: run the fetch, and add the data-sources string and the instruction.
- `docs/generated-app-schema.json`: regenerated by `make format`.
- `docs/architecture.md`: the data-sources fetch at the start of the turn, the data-sources string
  as a new input of every research graph node, the new tool name, and the fixed order of the
  References tables.
- `README.md`: the sentence at line 195 that names `dataset_metadata_tool`.
- Tests: `tests/test_app_properties.py`, `tests/test_mcp_client.py`, `tests/test_status_stages.py`
  and `tests/test_research_dispatch.py` for the rename, `tests/test_citation_lookups.py` and
  `tests/test_dataset_metadata.py` for the catalogue seeding and the shared parser, a new
  `tests/test_data_sources.py` for the fetch and the rendering, and the prompt tests that cover the
  changed templates.
- `dial_conf/core/applications.json` is each contributor's git-ignored local copy, seeded from the
  template; a copy that sets `dataset_metadata_tool` must be renamed by hand. `dial_conf/core/applications-template.json`
  carries no `statgpt` server, so it does not change.
- No new dependency and no new environment variable.
