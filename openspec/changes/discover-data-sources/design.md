## Context

See proposal.md for the motivation. The requirements are in the change's specs; the
`data-sources-discovery` spec owns the fetch, the retries and the rendering.

The state of the code this design builds on:

- **The turn starts in `DeepResearchCompletion._run_turn`** (`app/completion.py`). It loads the
  application properties, runs `PrepAgentRunner.run`, and, when `start_research` fired, runs
  `ResearchRunner.run` on the same choice. Preparation opens no MCP connection today. The research
  runner and the playground runner (`app/playground/runner.py`) each call `load_mcp_tools`, which
  builds a fresh `MultiServerMCPClient` and polls `tools/list` per server.
- **`data_sources_descriptions` reaches three calls today**: the preparation agent's system prompt
  (`preparation/agent.py`, `PREP_AGENT_SYSTEM`), the query clarity check in `update_query`
  (`preparation/tools.py`, `QUERY_REVIEW_SYSTEM`), and the playground agent (`playground/agent.py`,
  `PLAYGROUND_SYSTEM`). No node of the research graph receives it: not the research agent
  (`RESEARCH_AGENT_SYSTEM_PROMPT`), research-review (`RESEARCH_REVIEW_SYSTEM_PROMPT`), the report
  writer (`REPORT_SYSTEM_PROMPT`) or the report reviewer (`REPORT_REVIEW_SYSTEM_PROMPT`). All four
  are built in `research/nodes.py`, and each system prompt is filled once per call from values
  that are constant for the turn.
- **The list-datasets tool is called lazily today.** `CitationLookups.dataset_sources`
  (`research/citation_lookups.py`) calls it the first time a report review or the delivery needs
  the catalogue, and caches only a successful answer. The call goes through the LangChain tool
  object from `load_mcp_tools`, invoked tool-call-shaped, and `read_catalogue`
  (`research/dataset_metadata.py`) reads the structured result from the returned `ToolMessage`'s
  artifact. The tool stays in the research agent's tools. The configuration field that names it is
  `MCPClientSettings.dataset_metadata_tool`, required on a `statgpt` server.
- **Hand-written text copies the catalogue.** A channel's `data_sources_descriptions` typically
  carries a datasets section that lists each dataset's name, id and description, which is what the
  list-datasets tool returns.
- **The StatGPT dataset tools answer with structured content only.** In `statgpt-backend`,
  `statgpt/app/mcp/tools/datasets_meta.py` marks both the available-datasets tool and the
  dataset-structure tool "Structured-only: the whole result is the structured content, also sent
  as JSON text". The structure tool's arguments are `DatasetStructureArgs`
  (`statgpt/app/chains/datasets_meta/structure_tool.py`), whose one field is `dataset_id`, the
  dataset's URN. An unknown id raises a `ToolError`, which reaches the client as an error result.
- **The answers are small for a small catalogue.** A dataset's record in the list answer is on the
  order of 200 tokens, and its structure answer on the order of 450 tokens, counted with
  `tiktoken`'s `o200k_base` encoding. `tiktoken` has no entry for the configured model, so the token
  counts are estimates. A structure lists at most 10 sample values per dimension, so a dimension
  with more values, such as a country dimension, is not listed in full. The server picks those 10 at
  random on every call (`statgpt/app/utils/formatters/dataset_detailed.py`,
  `sample_component_values` with `shuffle_sample=True`), so two structure answers for one dataset
  differ.
- **The MCP adapter opens a session per tool call.** In the installed `langchain-mcp-adapters`
  0.3.0, a tool built by `get_tools()` without a session opens its own session on every call
  (`langchain_mcp_adapters/tools.py`, the `if session is None:` branch that calls
  `create_session`). `MultiServerMCPClient.session(server_name)` opens one initialized session per
  `async with`.
- **The StatGPT glossary tools answer with structured content.** In `statgpt-backend`,
  `statgpt/app/mcp/tools/glossary.py` builds the result from `AvailableTermsStructuredContent` and
  `TermDefinitionsStructuredContent`; the tool docstring says the whole result is the structured
  content, also sent as JSON text. `notFound` is omitted when every term resolves. The installed
  `mcp` 1.28.1 exposes it as `CallToolResult.structuredContent`, next to `isError`.
- **Probing a StatGPT server** showed that a list call and a parallel definitions fetch each
  finish within a few seconds, that opening an MCP session costs on the order of a second, and
  that under concurrent load an occasional call fails with HTTP 502 from DIAL Core. These
  observations were made with the `fastmcp` client, not with this app.
- **The MCP transport does not end a stalled call.** `app/mcp_tools.py` records that `mcp` 1.x
  logs a read timeout at DEBUG and leaves the call waiting, which is why a deadline of the app's own
  is needed.
- **`app/tool_failures.py` owns the failure helpers** used for tool calls:
  `error_resolution.exception_leaves` unwraps the `ExceptionGroup` a session context raises, and
  the failure kind in a log record is the class name of the first leaf.

## Goals / Non-Goals

**Goals:**

- An admin deploying a channel to a new environment writes by hand only what the servers cannot
  report. The datasets, their structures and the glossary come from the StatGPT MCP server.
- Every call that plans, researches, writes or reviews sees the same data sources, fetched once per
  turn, with no new failure mode that ends a turn.
- The research agent does not spend iterations on list or structure calls whose answers the app
  already fetched.
- The fetch adds as little latency as possible on a healthy server, and its worst case is bounded.
- A reader of the logs can tell a healthy fetch from a degraded one without the logs carrying any
  catalogue or glossary content.

**Non-Goals:**

- **Discovering the document server's publications.** The generic-RAG server has no tool that
  describes its collection, so the publication part of `data_sources_descriptions` stays
  hand-written.
- **Making `data_sources_descriptions` optional.** Every current channel still needs it for its
  publications. Its field description changes instead.
- **Accepting the old field name.** See D15.
- **Large catalogues.** Showing the whole catalogue, the list and the structures, is designed for a
  channel with about ten datasets, and a channel with a larger catalogue is deferred. Nothing caps,
  pages or shortens the catalogue, or the number of structure calls or of concurrent calls. Leaving
  `dataset_structure_tool` unset shows the list alone. See Risks.
- **A compact rendering of the structures.** The answers are shown as the server sent them. See
  D11.
- **Caching the data sources across turns or across users.** Every turn fetches them again. See
  D1.
- **A RAG-based glossary lookup.** The backend stays unchanged so that it stays possible later.
- **Fixing server content**, such as a truncated definition or a dataset description with a typo.
  That belongs to the server's own store.
- **Changing which tools the research agent is offered.** That stays the channel's
  `tools_to_include` decision.
- **Capturing the data sources the research agent fetches itself.** A direction for later work,
  deferred as a reliability enhancement. The app could attach tool-call interceptors to the
  `statgpt` server, the way `DataQueryCapture` (`research/data_queries.py`) keeps data-query records
  today, and read the agent's own list-terms, term-definitions and list-datasets results into the
  turn's registries. A catalogue the agent obtained would seed `CitationLookups`, so the citations
  would recover from a failed turn-start list without another call. For the glossary this is no
  longer needed: the reviewer already receives the agent's glossary results, and the glossary table
  already reads them, both selected from the transcript by tool name (D19, D21).

  Two ways were discussed. **Appending the raw successful results** needs no schema knowledge
  beyond MCP's `isError` flag, but the prompt then carries the failure text next to the later
  answers for the model to reconcile, and the app cannot decide the terminology rule's condition
  without reading the answer. **Parsing and merging** replaces a failed part with the successful
  answer. It needs the response shapes, but the turn-start fetch already validates exactly these
  (D4), so it adds no coupling beyond this change, and for the catalogue the shape is a contract
  of **report-citations**. The catalogue is the part worth doing first, by parsing and merging,
  because it is what makes citations recover. The glossary part waits until it is settled where
  the glossary lives: if it moves to a RAG lookup through the generic-RAG server, the glossary
  prefetch itself becomes obsolete, and the interceptor with it.

## Decisions

### D1. The turn coordinator runs one data-sources fetch before preparation, and hands it to both runners

`DeepResearchCompletion._run_turn` calls the fetch after the `prep_state.research_started` check,
so a conversation that already handed off fails at once without waiting for a fetch, and before
`PrepAgentRunner.run`. The fetch runs the datasets part and the glossary part concurrently
with `asyncio.gather`, each catching its own failures, so the turn waits for the slower part rather
than for their sum. The result is one value object, called `DataSources` here, that carries the
data-sources string, the catalogue for the citations (`None` when the list failed), whether a
structures block was rendered, the glossary's listed-term count (`None` when the list failed or no
glossary is configured) and its unresolved-term count, which the glossary instruction depends on
(D19). The coordinator passes the `DataSources` to both runners: the preparation runner needs the
string and whether the list of datasets failed (D18), and the research runner needs all of it. A channel without a `statgpt` server
gets a `DataSources` whose string is `data_sources_descriptions` unchanged, and no call is made.
The playground's runner does the same at the start of `PlaygroundRunner.run`, because the
playground has its own completion.

Alternatives considered:

- **Fetch inside the preparation runner or the agent builder.** Rejected: the research runner needs
  the same result, and the coordinator is the one place that sees both phases of the turn.
- **Fetch the datasets at research start only.** It would make no calls on preparation turns.
  Rejected: the preparation agent then sees only the hand-written text, so the admin could not
  remove the hand-written datasets section, which is the point of the change. The user chose the
  fetch before preparation.
- **Fetch concurrently with `reconstruct_history`.** It would hide the fetch behind the history
  download. Rejected for now: history reconstruction happens inside `PrepAgentRunner.run`, so
  overlapping them means moving that call out of the runner. It saves at most the shorter of the
  two durations. It can be done later without changing any spec.
- **Cache the data sources in the process with a time limit.** Rejected: the MCP calls carry the
  request's bearer token for per-user access, so a shared cache could serve one user's catalogue
  to another. The user also asked for a fetch per query.
- **Persist the data sources in `custom_content.state`.** Rejected: it would grow every persisted
  turn by the whole catalogue and glossary, and a list of records with an `index` field is exactly
  what the DIAL SDK chunk merge corrupts (`CLAUDE.md`, the `index` convention).

### D2. The app calls the tools through `client.session()`, one session per call

The fetch builds a client with the existing `build_mcp_client`, restricted to the `statgpt` server.
Each list attempt, structure attempt and definitions batch runs
`async with client.session(server_name) as session: await session.call_tool(name, arguments)`, and
reads the `CallToolResult` directly.

`call_tool` validates a successful result against the tool's output schema, as the MCP
specification recommends: "Clients SHOULD validate structured results against this schema"
(specification 2025-06-18, server tools, Output Schema). The library learns the schema from the
tool list, so on a fresh session a successful call is followed by a `tools/list` request
(`mcp/client/session.py`, `_validate_tool_result`, in the installed `mcp` 1.28.1). The app accepts
that request as part of the call. It runs under the call's deadline, and a failure of it counts as a
failed attempt, which the retries cover. The research agent's tool calls behave the same way today,
through `langchain-mcp-adapters`.

Alternatives considered:

- **Send the request with `session.send_request` and skip the library's schema validation.**
  Rejected by the user: it works around what the library does to follow the specification's
  recommendation, to save one request per call.
- **Call the LangChain tool objects from `load_mcp_tools`.** Rejected: it needs a `tools/list` per
  server to build the tools before preparation, and the adapter's error handler turns an MCP error
  result into ordinary content, which the app would then have to tell apart from a real answer.
- **One session shared by every call of the fetch.** It would open one session instead of one per
  call. Rejected: with the `fastmcp` client a 502 closed the shared session, and every later call
  in it failed. Whether the `mcp` SDK's streamable HTTP client behaves the same was not checked, and
  a session per call makes the question irrelevant. The calls of one step run in parallel, so a
  session per call costs one session-open latency per step, not one per call.
- **Raw HTTP with `httpx`.** Rejected: it re-implements the MCP handshake that the adapter already
  provides.

### D3. Every failure is retried, with the tool-retry backoff, under a 20-second deadline per call

A list attempt, a structure attempt or a batch call counts as failed when it raises, when `isError`
is true, when it does not finish within the deadline, or when its structured content fails
validation (D4). Every such failure is retried while attempts or rounds remain, as the user
specified. The delays are about 1 s and then 2 s with jitter, the same backoff the tool-call retry
uses (`tool_failures.py`); the implementation may reuse LangChain's `calculate_delay` if it stays
importable, or compute the same two delays itself. `asyncio.CancelledError` is never caught.

Each call, including its session open, runs under `asyncio.timeout(20)`. A healthy call finishes
within a few seconds, so 20 s leaves a wide margin. The user accepted 20 s; it can still be tuned
from the `Datasets fetched` and `Glossary fetched` durations without changing a spec.

The worst cases of the datasets part: a server that never answers costs 3 list attempts of 20 s
plus about 3 s of delays, about 63 s, after which no structure call is made. The bounded worst case
is a list whose third attempt succeeds just before its deadline, about 63 s, followed by structure
calls that each use all three attempts, about 63 s more, since they run concurrently: about 126 s
in total. The glossary part has the same shape, a list of about 63 s and then up to three rounds of
about 63 s together, and runs alongside, so the fetch's worst case is the larger of the two, about
two minutes, not their sum.

Alternatives considered:

- **Retry only the failures the tool-call retry classifies as transient**
  (`is_immediately_retryable`). Rejected: the user asked for 3 attempts, and a deterministic
  failure costs two more small calls, not a model round-trip.
- **No delay between attempts.** Rejected for the reason the tool-call retry spec gives: two
  attempts milliseconds apart test the same conditions twice.
- **Rely on the transport's timeouts.** Rejected: the read timeout does not end a call in `mcp`
  1.x, so a stalled call would hold the turn with no limit.

### D4. The structured content is validated only as far as the app reads it, and rendered from the raw dicts

The answer is read from `CallToolResult.structuredContent`. Small pydantic models with
`extra="allow"` check the shape the app relies on:

- the list-datasets answer is validated by the model `read_catalogue` already uses, `_Catalogue`: a
  `datasets` array (D14);
- a structure answer only has to be a JSON object, because the app reads nothing inside it;
- the list-terms answer has `terms`, a list of objects each with a `term` string, and the
  definitions answer has `definitions`, a list of objects each with `term` and `definition`
  strings, and optional `notFound`, a list of strings.

A result that fails the check, or carries no structured content, is a failed call.

The rendering uses the raw dicts, not `model_dump()`, so every field the server sends reaches the
prompt in the server's order, including fields this app does not know about.

Alternatives considered:

- **Parse the JSON text content when there is no structured content.** Rejected: the backend always
  sends structured content, `read_catalogue` already refuses a text-only answer for the same
  reason, and a second parsing path would hide a server change that the WARNING should surface.
- **Validate the structure answer's fields** (`datasetId`, `dimensions`). Rejected: the app does not
  read them, and validating them would turn a harmless server change into a missing structure.
- **Render from `model_dump()`.** Rejected: pydantic puts declared fields before extra fields, so
  the order would differ from the server's, and the spec requires the server's order.

### D5. A term is matched by its trimmed, case-folded name, and requested once per round

Before batching, the round's term names are deduplicated by their normalized form (surrounding
whitespace trimmed, then `str.casefold()`). A definitions record resolves every listed term whose
normalized name equals the record's normalized `term`. Two listed terms that normalize to the same
name therefore resolve together from one record.

The normalization matches the server's own lookup, which ignores case and surrounding spaces. The
deduplication makes the app independent of whether the server's deduplication of repeated
requested terms (`statgpt-backend` PR #706) is deployed.

Alternative considered: **exact string match.** Rejected: the server may return the stored
spelling of a term that the list gave in another case, and an exact match would count it as
unresolved.

### D6. Every JSON value is serialized on one line with `json.dumps(..., ensure_ascii=False)`

The default separators give the shape the user asked for, such as
`[{"index": 1, "term": ...}, ...]`. Non-ASCII characters are kept as themselves.

Alternatives considered:

- **`indent=2`.** Rejected: indentation adds tokens to every call that carries the data sources,
  and a model reads the one-line form just as well.
- **One record per line.** Rejected: nothing reads the string line by line, and the user specified
  a single JSON array for the glossary.

### D7. An unresolved term is marked by `"definition": null` directly after `term`

Alternatives considered:

- **Leave the `definition` field out.** Rejected: the model could not tell a term that failed to
  resolve from a record shape it does not know, and the decision was that unresolved terms are
  visibly marked.
- **A separate list of unresolved names after the array.** Rejected: it splits one term's facts
  across two places, and the model has to join them.

### D8. One owner builds the data-sources string, and the prompts receive strings

`app/data_sources.py` owns the fetch, the datasets rendering and a helper that joins
`prompts.data_sources_descriptions`, the datasets section and the rendered glossary, each part
after a blank line. `app/glossary.py` owns the glossary part of the fetch and its rendering, and
`app/data_sources.py` calls it. Every prompt builder receives the finished data-sources string where
it receives `data_sources_descriptions` today. `PrepTools(data_sources_descriptions=...)` keeps its
parameter and is handed the combined string. `build_prep_agent(state, today_date, prompts)` reads
`prompts.data_sources_descriptions` today, so it gains a parameter for the `DataSources` (or the
string and the failed-list flag) and stops reading that field.

`ApplicationProperties` gains `dataset_structure_tool` and `glossary` accessors next to
`list_datasets_tool`. Each returns the configured value, together with its server's name where the
fetch needs it, or `None`. At most one server can set each, for the reason the other accessors
give.

The research runner decides the two agent instructions (D16 and D19, the glossary
instruction). It has the agent's tools from `load_mcp_tools`, so it checks whether the configured
tool names are among them, together with what `DataSources` records. The playground runner makes
the same checks.

Alternative considered: **pass the `DataSources` object into every prompt builder and let each one
compose.** Rejected: it spreads the composition rule over six call sites, where one helper keeps
it in one place.

### D9. The prompt placement follows the existing blocks and keeps the caching prefixes

- **Research agent:** a new `## Data sources` section in `RESEARCH_AGENT_SYSTEM_PROMPT`, with the
  data-sources string in a `<data_sources>` block. A `{data_sources_instructions}` placeholder
  follows it, filled with the dataset-tools instruction (D16), the glossary instruction (D19),
  both, or an empty string.
- **Research-review:** the same `<data_sources>` section in `RESEARCH_REVIEW_SYSTEM_PROMPT`.
- **Report writer:** the same `<data_sources>` section in `REPORT_SYSTEM_PROMPT`, and the
  glossary-terminology rule next to the other report-wide rules on every turn of a channel that
  configures a glossary (D19).
- **Report reviewer:** the same `<data_sources>` section in `REPORT_REVIEW_SYSTEM_PROMPT`, the
  `<glossary_tool_results>` block, and check 7 there when the glossary fetch listed terms or that
  block is not empty (D19).
- **Always the system prompt, never the request message.** The `prompt-caching` rules for the
  research-review and report-review messages govern only those messages, so leaving the messages
  unchanged keeps them intact.
- **One wording for the glossary rule.** The writer's rule and the reviewer's check are both built
  from one constant in `research/prompts.py`, so they cannot drift apart. The writer's rule adds
  one caveat of its own: the data-sources glossary may lack terms or definitions, and the terms in
  the research's tool results count too. It is not a `ReportRule`
  in `report_rules.py`: that module holds only the rules Python decides from the draft text.

All system prompts that gain the data sources are constant for the whole turn, so the provider's
prompt cache still serves the repeated calls within the turn. They are not constant across turns
when structures are fetched, because the server samples a structure's values at random on every
call. The cost is small: research runs once per conversation, so its calls gain nothing from a
previous turn's cache anyway, and only the first preparation call of each preparation turn misses
the cache, over a conversation that is still short at that stage. This is accepted. Deterministic
sampling would be a backend change, which this change does not make.

Alternatives considered:

- **Put the data-sources string in a node's request message instead of its system prompt.**
  Rejected for every node: the data sources are standing context, as in the preparation prompts,
  and the system prompt is already the stable prefix of every call of a node.
- **Make the terminology rule an app-checked `ReportRule`.** Rejected: whether a phrase refers to
  the concept a glossary term names needs a reader, which is the line `report_rules.py` draws.

### D10. The log records are one INFO event per part, and at most two WARNINGs per part

One INFO event `Datasets fetched` ends every datasets fetch, with `server`, `list_attempts`,
`datasets`, `structures_requested`, `structures_obtained`, `structures_failed` and `duration`.
`datasets` is `None` when the list failed. One WARNING names the server and the failure kind of the
last list attempt when all three failed, and one WARNING names the server and the number of
structures not obtained.

One INFO event `Glossary fetched` ends every glossary fetch, with `server`, `list_attempts`,
`listed`, `resolved`, `unresolved`, `rounds` and `duration`. `listed` is `None` when the list
failed. One WARNING names the server and the failure kind of the last list attempt when all three
failed, and one WARNING names the server and the unresolved count after the last round.

The failure kind is the class name of the first exception leaf, or `mcp_error`, `timeout` or
`invalid_result` for the failures that raise nothing. Both INFO events join the `logging-policy`
request skeleton as events (1a) and (1b).

Alternative considered: **one WARNING per failed call.** Rejected: ten failed structure calls
would log ten records that say the same thing, and the end-of-fetch counts already say how
degraded the fetch was.

### D11. The datasets section shows the structured results verbatim

The section is `Datasets:` and the list-datasets structured result as one-line JSON, then, when
structures were fetched, a blank line, `Dataset structures:` and a JSON array of the structure
answers. This is what the user asked for: the tools' outputs as they are, from the structured
content. The top-level fields of the list answer (`providers`, `totalDatasets`, `totalAgencies`)
stay, because they are part of the answer.

Alternatives considered:

- **Render the catalogue as Markdown, like the hand-written section.** Rejected: the app would
  choose which fields a model sees, and a field the server adds later would be dropped silently.
- **A compact rendering that drops what every structure repeats**, such as dimensions with a single
  value and the attributes every dataset of a server shares. It would likely save a large share of
  the structure tokens. Rejected for now: a few thousand tokens is small next to a 1,050,000-token
  context, and a compact form needs rules about what is safe to drop. It can
  be added later without changing the fetch.

### D12. The structures go into a separate block after the list, not into each record

Alternative considered: **nest each structure into its catalogue record** as a `structure` field.
It saves the repeated id, name and `lastUpdated`. Rejected: the list answer would no longer be
what the server sent, and the user chose the separate block.

### D13. Each structure call has its own three attempts, not glossary-style rounds

The glossary needs rounds because one batch requests many terms, and the terms that fail are
re-batched. A structure call requests one dataset, so there is nothing to re-batch, and a per-call
retry gives the same result with less machinery. A failed structure becomes
`{"dataset_id": <id>, "error": "failed to obtain dataset structure"}`, keyed by the argument name
the app sent, since the app does not know which key the server uses for the id in its answer.

Alternatives considered:

- **Rounds, as for the glossary.** Rejected for the reason above.
- **Drop a failed dataset from the block.** Rejected: the model could not tell a dataset whose
  structure failed from one that was never requested, and the research agent's instruction (D16)
  names the failure entries as the ones to request itself.

### D14. The turn-start list answer seeds the citation lookups

`read_catalogue` is split so that the part which turns a structured result into
`dict[str, DatasetSource]` takes a dict and is shared: the citation path passes the `ToolMessage`
artifact's `structured_content`, and the fetch passes `CallToolResult.structuredContent`. The fetch
keeps the parsed catalogue in `DataSources`, and `ResearchRunner.run` passes it to
`CitationLookups`, which starts with that catalogue instead of `None`. When the list failed,
`CitationLookups` starts empty and fetches as it does today.

The rendered section and the catalogue come from the same answer, so the datasets a model is shown
are exactly the ones the review checks cited URNs against.

Alternatives considered:

- **Keep the lazy fetch and make a second list call at report time.** Rejected: it costs a second
  call per research turn, and the review could check URNs against a catalogue that differs from
  the one the models saw.
- **Parse the catalogue twice, once for the prompt and once for the citations.** Rejected: one
  parser keeps one set of rules about which records are usable.

### D15. `dataset_metadata_tool` is renamed to `list_datasets_tool` with no alias

The field, its validator, the `ApplicationProperties` accessor, `LoadedMcpTools`' field, the log
message in `load_mcp_tools` and the specs' prose all take the new name. The failure-kind tokens
(`dataset_call_failed` and the others in `dataset_metadata.py`) and the module name stay, because
they name what fails rather than the configuration field, and renaming them would change log
records that dashboards may read.

Alternatives considered:

- **Accept the old name as a deprecated alias** (`validation_alias=AliasChoices(...)`). Rejected: the
  field would have two names with no date to remove one, and the channel configurations that set it
  are few and owned by this team. The rollout order is in the migration plan.
- **Rename the field only, and keep "dataset-metadata tool" in the prose.** Rejected by the user:
  two names for one tool would coexist in the specs.

### D16. The research agent is told which dataset calls succeeded and which failed

`RESEARCH_AGENT_SYSTEM_PROMPT` gains an instruction, filled into `{data_sources_instructions}`,
that says for each bound dataset tool whether the app's own calls succeeded. When they did, the
agent does not call the tool again for an answer the datasets section shows. When they failed
after the app's retries, the agent calls the tool itself when it needs the answer: the agent's
call is the fallback for a failure the retries did not overcome, and it goes through the agent's
own tool-call retry and failure handling. Each fallback is capped at three calls in the whole
research, per list and per dataset structure, the same cap as the glossary instruction (D19) and
the research prompt's failed-tool rule (one call and two repeats). Behind each of those calls,
`ToolFailureMiddleware` still retries a transient failure up to twice in-process
(`TOOL_CALL_MAX_RETRIES` in `app/tool_failures.py`). Concretely: a successful list means "do not call the
list-datasets tool"; a failed list means "call it when you need to know which datasets exist"; a
structure shown means "do not call the structure tool for this dataset"; a failure entry, or a
failed list on a channel that names a structure tool, means "call the structure tool for the
datasets whose structure you need". Each part is included only when its tool is bound to the
agent, named as bound. The failed-list part about the structure tool also needs the list-datasets
tool bound, because without the list the agent has no dataset id to pass. A channel that wants the
fallback offers the list tool in its `tools_to_include`, and the migration plan says so.

The playground agent gets only the parts about a failed call. Its prompt says "You help to debug
and improve tools connected from MCP servers", and a part telling it not to call a tool would
contradict a user who asks it to call that tool.

The instruction does not tell the agent that a structure lists every available value, because it
does not: a structure lists at most 10 sample values per dimension. Coverage questions still need
the availability tool, and the prompt says nothing that would discourage it.

Alternatives considered:

- **Remove the list and structure tools from the agent's tools.** Rejected: the agent's call is
  the fallback for a failed fetch, and the `report-citations` spec keeps the list tool available to
  the agent.
- **Say nothing when a call failed, and let the failure text speak for itself.** Rejected: the
  failure text says what is missing but not what to do, and the agent should use the fallback.

### D18. Preparation is told to plan around a failed list, and never to call a dataset tool

When the list failed, `PREP_AGENT_SYSTEM` gains an instruction, filled into a placeholder after its
`<data_sources>` block: the failure does not hold up clarification or the plan, and when the query
needs dataset data, the plan carries an item that asks research to search the available datasets
and says that no specific dataset can be suggested because the list could not be obtained.
The placeholder is an empty string when the list succeeded. `QUERY_REVIEW_SYSTEM` gets no such
rule, because the clarity check does not ask the user to choose a dataset in any case.

The instruction is an exception to a rule `PREP_AGENT_SYSTEM` already states: "If any data source
in the 'Data sources available to research' section plausibly covers the query topic, the plan MUST
name it." With a failed list, no dataset can be named, so the instruction states explicitly that
this rule does not apply to a data source whose listing failed, and that the search item takes the
place of the named datasets. Otherwise the two rules contradict each other. The preparation calls get no instruction to call a
dataset tool, because preparation has no MCP tools.

The plan item is what carries the gap into research: the approved plan is the research agent's
first-iteration instruction, and the research agent's own instruction (D16) tells it to call the
list-datasets tool when the app's list failed.

Alternatives considered:

- **No instruction; let the failure text speak for itself.** Rejected: a model that reads "failed
  to obtain list of datasets" may stall, ask the user to retry, or ask the user to pick a dataset
  it cannot name.
- **Tell the user about the failure in a separate message.** Rejected: the plan item already tells
  the user, in the place where it matters, and a separate message adds a step the user cannot act
  on.

### D17. One change covers the datasets and the glossary, and both are implemented in it

The tasks order the work so that the rename, the datasets part of the fetch, the data-sources
string and its routing to every call, the dataset instruction and the citation seeding come first,
and the glossary part follows: `GlossaryTools`, `app/glossary.py`, the glossary instruction, the
terminology rule and check, the glossary citation form and the glossary table. Nothing is deferred:
the change is archived once both parts are done. The glossary part reuses the fetch, the routing
and the logging this change introduces, which is why the two are one change.

Alternative considered: **a separate change for the datasets.** Rejected by the user: the glossary
change already modifies the same requirements, and two changes would conflict on them.

The Deep Research evaluation is not a task of this change. The change ships first and is evaluated
afterwards, because every research node now receives the data-sources string and preparation
behaves differently when the list fails.

### D19. The research agent repeats the failed glossary calls itself, at most three times

When the glossary's list failed, the research agent is told to call the list-terms tool, and when
the list failed or some terms did not resolve, to request the missing definitions of the relevant
terms. Each is capped at three calls in the whole research, which matches the failed-tool rule the
research prompt already states (one call and two repeats), so a server that keeps failing costs a
bounded number of agent steps. Each part appears only when its tool is bound. The playground agent
gets the same failed-call parts.

When the fetch listed the terms and every term resolved, the research agent is told not to call
the bound glossary tools, as a successful list means "do not call the list-datasets tool" (D16).
Without this part, the agent requested definitions its context already held. The playground agent
never gets this part, for the reason D16 gives: its user may ask it to call any tool whatever the
fetch obtained.

The agent's results are ordinary tool results, so research-review and the report writer see them.
The report writer gets the terminology rule on every turn of a channel that configures a glossary,
and the rule says that the glossary in the data-sources string may lack terms or definitions and
that the terms and definitions in the research's tool results count too.

The report reviewer receives no transcript, so the app passes it the agent's glossary results
explicitly. The glossary tool names are in the configuration (`glossary.list_terms_tool` and
`glossary.definitions_tool`), so `research/nodes.py` selects, from the graph's `messages`, every
`ToolMessage` whose tool name is one of the two and whose status is not an error, and puts their
text, in order, into a `<glossary_tool_results>` block of `REPORT_REVIEW_SYSTEM_PROMPT`. The
transcript is final once the report loop starts, so the block is constant across the review calls
of a turn and keeps the system prompt a stable prefix. The text is passed as the server sent it,
with no parsing. The reviewer gets the check when the app's fetch listed at least one term or the
block is not empty.

Alternatives considered:

- **No instruction for a failed list.** Rejected: the agent's call is the fallback for a failure
  the app's retries did not overcome, the same reasoning as for the dataset tools (D16).
- **Request every missing definition, relevant or not.** Rejected: a glossary with many unresolved
  terms would spend many agent steps on terms the task does not use.
- **Leave the reviewer without the agent's results, and give it the check only when the app's
  fetch listed terms.** Rejected: on a turn whose fetch failed, the writer would follow a rule the
  reviewer cannot check.
- **Capture the results with a tool-call interceptor and merge them into the glossary.** Rejected
  for now: it needs the response shapes parsed and merged, while selecting by tool name needs
  nothing beyond the configured names and the result's status. See the deferred direction in
  Non-Goals.
- **Pass every tool result to the reviewer.** Rejected: the reviewer judges the draft, not the
  research, and the glossary results are the only ones a reviewer check depends on.

### D20. A failed list of datasets degrades the turn and never fails it

When every attempt of the turn-start list call fails, the turn goes on: preparation plans around it
(D18), the research agent calls the tool itself (D16), and the citation path tries the catalogue
again in each report review that needs it and at delivery. When all of those fail too, `[dataset
<urn>]` citations stay plain text and their References rows cannot be opened, while data-query
citations still become pills, labelled with the dataset's URN, because their link comes from the
query's own result.

Alternatives considered:

- **Fail every turn whose list fails.** Rejected: preparation does not need the catalogue, so a
  clarification turn would fail for nothing. Research takes minutes and retries the catalogue
  several times, so a short outage very likely recovers before delivery. When the server is fully
  down, its query tools fail too, and failing early only tells the user sooner.
- **Fail the turn when research is about to start and the list is still unavailable.** It would
  keep the one research a conversation may run from producing uncitable dataset citations.
  Rejected by the user: it also blocks a report that publications alone could support, and the
  degraded report still carries every citation marker.

### D21. A glossary term is cited with a marker that delivery makes readable, and cited terms get a References table

On a channel that configures a glossary, a fact taken from a glossary definition is cited
`[glossary <term>]`, a square-bracket marker like the other three. The citation conversion in
`research/citations.py` rewrites each one into the readable form `(<term> - glossary term)` before
delivery, with no pill, and `research/references.py` adds one table after the server tables,
configured by `glossary.references_table` exactly as a server's table is: a title, and columns keyed
by fields of a term's record.

A cited term's record comes from the app's fetch first, then from the research agent's successful
term-definitions results, then from its list-terms results, each matched by the trimmed,
case-folded name (D5) and read with the same shape rules as the fetch (D4). A record with a
`definition` wins over one without. The agent's results are selected from the transcript by the
configured tool names, as for the reviewer's `<glossary_tool_results>` block (D19); unlike that
block, the table parses them, because a row needs the definition field. The parsing adds no
coupling beyond the fetch's own. A term found nowhere still gets a row with its name.

The glossary marker counts as an inline citation for the word count, so `report_length.py` adds
`glossary` to the keywords its citation pattern exempts.

The References tables come in a fixed order by kind of source: datasets, then documents, then the
glossary, whatever order `mcp_servers` lists the servers in. The user set this order. Today the
tables follow the configured server order: `ApplicationProperties.references_tables` returns them in
server order, and its docstring says "an operator decides it by ordering the servers", and
`research/runner.py` writes them in that order. The property and the runner change for this, and so
does the sentence in `docs/architecture.md` that says "in the order the servers are configured".

Glossary markers are grouped per run of adjacent citations, the run the pill grouping already
defines. They leave their place, so the run's dataset and document markers still fold into one pill,
and one readable group ends the run: `(<term> - glossary term)` for one term, or
`("<term 1>", "<term 2>" - glossary terms)` for several. Left where the writer put them, a glossary
marker between two dataset markers would split one pill into two with the glossary text between.

A term containing a square bracket cannot be cited, because a marker ends at its first `]`, as the
other markers do. Glossary terms rarely contain square brackets, so this is accepted.

A marker in square brackets is read by the same rules as the other markers: the keyword in any
letter case, spaces around it, and one line. It also avoids two problems a parenthesised form written
by the model would have had: the app's Markdown-link detection (`_INLINE_HYPERLINK_RE`) reads
`[doc 12, page 3](text)` as a link, and a parenthesised term needs a balanced-parenthesis grammar.
The readable form is produced by the app itself, after the review, so neither problem arises.

Publication descriptions are never cited: only a publication itself is, by document and page. A
fact from the hand-written description of a publication series follows the rule for a sentence that
cannot be cited.

Alternatives considered:

- **The writer writes the readable form `(<term> - glossary term)` itself.** Chosen first, then
  replaced by the user: written directly after a marker it is read as a Markdown link and lost, and
  finding it needs a grammar for parentheses inside the term.
- **Double square brackets, `[[…]]`, for every citation form**, so that a term may contain `]`.
  Rejected: it changes the format of all four forms, the prompt and the parser for a case glossary
  terms rarely have, and a term containing `]]` would still break.
- **Rewrite each glossary marker where it stands.** Rejected: a glossary marker between two dataset
  markers would split their pill into two.
- **Deliver the marker as a pill, or leave it as written.** Rejected: a pill for a glossary term has
  no page to open, and an unconverted marker reads worse than the readable form.
- **Only the app's fetch fills the table.** Rejected by the user: a term only the agent resolved would
  show an empty definition, although the app already knows how to read the agent's answer.
- **A fixed `Glossary` title and `Term` and `Definition` headings.** Rejected by the user: a channel
  whose readers read another language could not change them, which every other References table
  allows.

## Risks / Trade-offs

- **[Latency on every turn]** Every turn on a channel with a dataset server waits for the fetch
  before the first preparation token: a few seconds on a healthy server, and up to about two
  minutes against a server that stalls every call until the last moment (D3). → The deadline bounds it, the INFO events record the duration of every
  fetch, and D1 leaves overlapping the fetch with history reconstruction as a later optimization.
- **[Token cost grows with the catalogue]** A catalogue of about ten datasets with their
  structures costs on the order of 6,500 tokens, which reach every preparation agent step, every clarity check, every research agent step, every
  research review, every report and every report review. A channel with 100 datasets would cost
  on the order of 65,000 tokens per call. → Showing the catalogue is designed for a channel with about ten
  datasets, and the specs and the field description say so. A larger channel is deferred. All of it sits in
  system prompts that are constant within the turn, so the provider's prompt cache serves the
  repeats. A cap or a compact rendering (D11) can be added later.
- **[The data-sources string changes between turns]** The server samples a structure's values at
  random on every call, so each turn's string differs. The first preparation call of each
  preparation turn misses the prompt cache, over a short conversation, and research is unaffected
  because it runs once per conversation. A plan written in one turn may also name a sample value
  that the next turn's structure does not show. → Accepted as minor (D9).
- **[Concurrency]** A fetch sends one structure call per dataset at once, and a large glossary
  sends many batches at once. Many calls in flight raise the chance of a gateway error. → Every
  call retries. A cap on concurrent calls can be added later without changing the specs.
- **[The rename breaks deployed channels]** A channel configuration that still sets
  `dataset_metadata_tool` fails validation, and every turn on it fails with "application not
  configured". → The migration plan renames the field in every channel configuration in the same
  rollout as the image.
- **[Research sees the data sources on every channel]** Every node of the research graph receives
  `data_sources_descriptions` even on a channel without a dataset server, which is a behavior
  change. The topics map was written for planning, and its hints may steer the research. → The
  Deep Research evaluation, run after the change ships, compares against the results before it.
- **[The report writer sees datasets research did not query]** The writer may cite a dataset from
  the catalogue that no tool call of the turn touched. That is acceptable in itself: a report may
  have a real reason to, such as citing a dataset's metadata (its description, coverage or last
  update) from the datasets section. The risk is only a citation of a dataset the report does not
  use. The review's identifier check does not catch it, because the URN is known to the server. → `REPORT_SYSTEM_PROMPT` already says "Do not
  introduce facts that are not grounded in the retrieved findings" and "Cite the source for every
  fact". The writer is told that the data-sources string counts as a retrieved source (spec
  `report-composition`, "The data sources in the system prompt count as retrieved sources"). No
  instruction about unqueried datasets is added, on purpose: telling the writer not to cite one
  would also tell it that it can, and citing one is acceptable when the report uses it. Watch for it in the evaluation's citation checks.
- **[Sample values read as coverage]** A structure lists at most 10 sample values per dimension. A
  model could read a missing country as unavailable. → D16 says nothing that discourages the
  availability tool. If the evaluation shows the mistake, the dataset instruction can say it.
- **[Reviewer false positives]** The terminology check could flag wording that is fine and spend
  report versions on rewrites. → The rule asks for the glossary term only where it names the
  concept, and `max_report_versions` caps the rewrites.
- **[A new failure path before preparation]** Every turn on a channel with a dataset server now
  makes MCP calls before the user sees anything. → No failure of the fetch ends the turn (spec
  `data-sources-discovery`), and the failure texts make the gap visible to the models.

## Migration Plan

1. In the same rollout as the new image, rename `dataset_metadata_tool` to `list_datasets_tool` in
   every channel configuration. The channel configurations live in DIAL Core, outside this
   repository. Each contributor also renames it in their local `dial_conf/core/applications.json`.
2. To enable the structures on a channel, add `dataset_structure_tool` to its `statgpt` server
   entry, naming the server's dataset-structure tool. Offer the list-datasets tool in the server's
   `tools_to_include` too, so the research agent can use the fallback when the turn-start list
   fails (D16).
3. Remove the hand-written datasets section from the channel's `data_sources_descriptions`, since
   the app now appends the catalogue itself.
4. To enable the glossary on a channel, add the `glossary` object, with its `references_table`, to
   its `statgpt` server entry.

To roll back, deploy the previous image with the old field name restored in the configurations.

## No changes required

- `app/history.py` and the persisted state: the data sources are not persisted (D1).
- `app/research/report_rules.py`: the glossary rule is a model-judged check (D9), and the dataset
  identifier check keeps reading `CitationLookups`, which now starts with the catalogue.
- `QUERY_REVIEW_SYSTEM` and `PLAN_REVIEW_SYSTEM` in `app/preparation/prompts.py`: the first already
  puts `{data_sources_descriptions}` inside `<data_sources>`, and only the value filled in changes;
  the second receives no data sources. `PREP_AGENT_SYSTEM` does change, for D18.
- The request messages of research-review and report-review (`RESEARCH_REVIEW_HUMAN_MESSAGE`,
  `REPORT_REVIEW_REQUEST`): the data sources go into the system prompts (D9).
- The failure-kind tokens and the module name `research/dataset_metadata.py` (D15).
- `dial_conf/core/applications-template.json`: it carries no `statgpt` server, and both new fields
  are optional, so there is nothing to rename or add.
- `README.md` environment-variables table and `settings.py`: no environment variable is added.

## Open Questions

None. Serving a catalogue much larger than ten datasets is a deferred non-goal rather than an open
question.
