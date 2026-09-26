## Context

See proposal.md for the motivation. The requirements are in the change's specs; the
`glossary-prefetch` spec owns the fetch, the retries and the rendering.

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

- Every call that plans, researches, writes or reviews sees the same glossary, fetched once per
  turn, with no new failure mode that ends a turn.
- The glossary fetch adds as little latency as possible on a healthy server, and its worst case is
  bounded.
- A reader of the logs can tell a healthy fetch from a degraded one without the logs carrying any
  glossary content.

**Non-Goals:**

- **Caching the glossary across turns or across users.** Every turn fetches it again. See D1.
- **Capping the number of concurrent definition calls.** A round sends all its batches at once.
  See Risks.
- **A RAG-based glossary lookup.** The proposal keeps the backend unchanged so that it stays
  possible later.
- **Telling an agent to re-list the terms when the list failed.** The failure text reaches the
  prompts, and nothing asks the agent to act on it.
- **Fixing glossary content**, such as a truncated definition. That belongs to the glossary store.
- **Changing which glossary tools the research agent is offered.** That stays the channel's
  `tools_to_include` decision.

## Decisions

### D1. The turn coordinator fetches the glossary before preparation, and hands it to both runners

`DeepResearchCompletion._run_turn` calls the fetch right after `load_application_properties` and
before `PrepAgentRunner.run`. The result is one value object, called `Glossary` here, that carries
the rendered string and the listed-term count (`None` when the list failed). The coordinator passes
the data-sources string to the preparation runner, and the `Glossary` itself to the research runner.
A channel without a glossary gets `None` and no call is made. The playground's runner does the same
at the start of `PlaygroundRunner.run`, because the playground has its own completion.

Alternatives considered:

- **Fetch inside the preparation runner or the agent builder.** Rejected: the research runner needs
  the same result, and the coordinator is the one place that sees both phases of the turn.
- **Fetch concurrently with `reconstruct_history`.** It would hide the fetch behind the history
  download. Rejected for now: history reconstruction happens inside `PrepAgentRunner.run`, so
  overlapping them means moving that call out of the runner. It saves at most the shorter of the
  two durations. It can be done later without changing any spec.
- **Cache the glossary in the process with a time limit.** Rejected: the MCP calls carry the
  request's bearer token for per-user access, so a shared cache could serve one user's glossary to
  another. The user also asked for a fetch per query.
- **Persist the glossary in `custom_content.state`.** Rejected: it would grow every persisted turn
  by the whole glossary, and a list of records with an `index` field is exactly what the DIAL SDK
  chunk merge corrupts (`CLAUDE.md`, the `index` convention).

### D2. The app calls the tools through `client.session()`, one session per call

The fetch builds a client with the existing `build_mcp_client`, restricted to the one server that
configures the glossary. Each list attempt and each batch runs
`async with client.session(server_name) as session: await session.call_tool(name, arguments)`, and
reads the `CallToolResult` directly.

Alternatives considered:

- **Call the LangChain tool objects from `load_mcp_tools`.** Rejected: it costs a `tools/list`
  round trip per turn before preparation for no gain, and the adapter's error handler turns an MCP
  error result into ordinary content, which the app would then have to tell apart from a real
  answer.
- **One session shared by every call of the fetch.** It would open one session instead of one per
  call. Rejected: with the `fastmcp` client a 502 closed the shared session, and every later call
  in it failed. Whether the `mcp` SDK's streamable HTTP client behaves the same was not checked, and
  a session per call makes the question irrelevant. The calls of a round run in parallel, so a
  session per call costs one session-open latency per round, not one per call.
- **Raw HTTP with `httpx`.** Rejected: it re-implements the MCP handshake that the adapter already
  provides.

### D3. Every failure is retried, with the tool-retry backoff, under a 20-second deadline per call

A list attempt or a batch call counts as failed when it raises, when `isError` is true, when it
does not finish within the deadline, or when its structured content fails validation (D4). Every
such failure is retried while attempts or rounds remain, as the user specified. The delays are
about 1 s and then 2 s with jitter, the same backoff the tool-call retry uses
(`tool_failures.py`); the implementation may reuse LangChain's `calculate_delay` if it stays
importable, or compute the same two delays itself. `asyncio.CancelledError` is never caught.

Each call, including its session open, runs under `asyncio.timeout(20)`. A healthy call finishes
within a few seconds, so 20 s leaves a wide margin. The worst case of a fetch against a server
that never answers is 3 list attempts of 20 s plus about 3 s of delays, about 63 s, after which no
definition call is made. A server that lists terms and then stalls costs at most three rounds of
20 s plus delays.

Alternatives considered:

- **Retry only the failures the tool-call retry classifies as transient**
  (`is_immediately_retryable`). Rejected: the user asked for 3 attempts, and a deterministic
  failure costs two more small calls, not a model round-trip.
- **No delay between attempts.** Rejected for the reason the tool-call retry spec gives: two
  attempts milliseconds apart test the same conditions twice.
- **Rely on the transport's timeouts.** Rejected: the read timeout does not end a call in `mcp`
  1.x, so a stalled call would hold the turn with no limit.

### D4. The structured content is validated, and the records are rendered from the raw dicts

The answer is read from `CallToolResult.structuredContent`. Two small pydantic models with
`extra="allow"` check the shape: the list answer has `terms`, a list of objects each with a
`term` string, and the definitions answer has `definitions`, a list of objects each with `term`
and `definition` strings, and optional `notFound`, a list of strings. A result that fails the check,
or carries no structured content, is a failed call.

The rendering uses the raw dicts, not `model_dump()`, so every field the server sends reaches the
prompt in the server's order, including fields this app does not know about.

Alternatives considered:

- **Parse the JSON text content when there is no structured content.** Rejected: the backend always
  sends structured content, and a second parsing path would hide a server change that the WARNING
  should surface.
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

### D6. The array is serialized on one line with `json.dumps(..., ensure_ascii=False)`

The default separators give exactly the shape the user asked for,
`[{"index": 1, "term": ...}, ...]`. Non-ASCII characters are kept as themselves.

Alternatives considered:

- **`indent=2`.** Rejected: indentation adds tokens to every call that carries the glossary, and a
  model reads the one-line form just as well.
- **One record per line.** Rejected: nothing reads the string line by line, and the user specified
  a single JSON array.

### D7. An unresolved term is marked by `"definition": null` directly after `term`

Alternatives considered:

- **Leave the `definition` field out.** Rejected: the model could not tell a term that failed to
  resolve from a record shape it does not know, and the decision was that unresolved terms are
  visibly marked.
- **A separate list of unresolved names after the array.** Rejected: it splits one term's facts
  across two places, and the model has to join them.

### D8. One owner builds the data-sources string, and the prompts receive strings

`app/glossary.py` owns the fetch, the rendering and a helper that joins
`prompts.data_sources_descriptions`, a blank line and the rendered glossary. Every prompt builder
receives the finished data-sources string where it receives `data_sources_descriptions` today. The
`PrepTools(data_sources_descriptions=...)` and `build_prep_agent` signatures keep their parameter
and are handed the combined string.

`ApplicationProperties` gains a `glossary` accessor next to `dataset_metadata_tool`. It returns the
one configured `glossary` together with its server's name, or `None`. At most one server can set
it, for the reason the other accessors give.

The research runner decides the missing-definitions instruction. It has the agent's tools from
`load_mcp_tools`, so it checks whether the configured `definitions_tool` name is among them, and
whether `Glossary.listed_count` is at least 1. The playground runner makes the same check.

Alternative considered: **pass the `Glossary` object into every prompt builder and let each one
compose.** Rejected: it spreads the composition rule over six call sites, where one helper keeps
it in one place.

### D9. The prompt placement follows the existing blocks and keeps the caching prefixes

- **Research agent:** a new `## Data sources` section in `RESEARCH_AGENT_SYSTEM_PROMPT`, with the
  data-sources string in a `<data_sources>` block. A `{glossary_instruction}` placeholder follows
  it, filled with the instruction or with an empty string.
- **Research-review:** the same `<data_sources>` section in `RESEARCH_REVIEW_SYSTEM_PROMPT`.
- **Report writer:** the same `<data_sources>` section in `REPORT_SYSTEM_PROMPT`, and the
  glossary-terminology rule next to the other report-wide rules when the glossary listed terms.
- **Report reviewer:** the same `<data_sources>` section in `REPORT_REVIEW_SYSTEM_PROMPT`, and
  check 7 there when the glossary listed terms.
- **Always the system prompt, never the request message.** The `prompt-caching` rules for the
  research-review and report-review messages govern only those messages, so leaving the messages
  unchanged keeps them intact.
- **One wording for the rule.** The writer's rule and the reviewer's check are both built from one
  constant in `research/prompts.py`, so they cannot drift apart. It is not a `ReportRule` in
  `report_rules.py`: that module holds only the rules Python decides from the draft text.

All system prompts that gain the glossary are constant for the whole turn, so the provider's
prompt cache still serves the repeated calls within the turn.

Alternatives considered:

- **Put the data-sources string in a node's request message instead of its system prompt.**
  Rejected for every node: the data sources are standing context, as in the preparation prompts,
  and the system prompt is already the stable prefix of every call of a node.
- **Make the terminology rule an app-checked `ReportRule`.** Rejected: whether a phrase refers to
  the concept a glossary term names needs a reader, which is the line `report_rules.py` draws.

### D10. The log records are one INFO event and at most two WARNINGs

One INFO event `Glossary fetched` ends every fetch, with `server`, `list_attempts`, `listed`,
`resolved`, `unresolved`, `rounds` and `duration`. `listed` is `None` when the list failed. One
WARNING names the server and the failure kind of the last list attempt when all three failed, and
one WARNING names the server and the unresolved count after the last round. The failure kind is
the class name of the first exception leaf, or `mcp_error`, `timeout` or `invalid_result` for the
failures that raise nothing.

Alternative considered: **one WARNING per failed call.** Rejected: a round of ten failed batches
would log ten records that say the same thing, and the end-of-fetch counts already say how degraded
the fetch was.

## Risks / Trade-offs

- **[Latency on every turn]** A turn on a channel with a glossary waits for the fetch before the
  first preparation token: a few seconds on a healthy server, and up to about a minute against a
  stalled server. → The deadline bounds it, the INFO event records the duration of every fetch, and
  D1 leaves overlapping the fetch with history reconstruction as a later optimization.
- **[Token cost]** About 5,000 more input tokens reach every preparation agent step, every clarity
  check, every research agent step, every research review, every report and every report review.
  → All of it sits in system prompts that are constant within the turn, so the provider's prompt
  cache serves the repeats.
- **[Concurrency on a large glossary]** A round sends all its batches at once, so a glossary of
  1,000 terms with a limit of 10 sends 100 concurrent calls, and many calls in flight at once
  raise the chance of a gateway error. → The rounds re-request whatever failed. A cap on concurrent batches
  can be added later without changing the specs.
- **[Research sees the topics map on every channel]** Every node of the research graph receives
  `data_sources_descriptions` even on a channel without a glossary, which is a behavior change.
  The topics map was written for planning, and its hints may steer the research. → Run the Deep
  Research evaluation on a channel without a glossary before and after the change.
- **[Reviewer false positives]** The terminology check could flag wording that is fine and spend
  report versions on rewrites. → The rule asks for the glossary term only where it names the
  concept, and `max_report_versions` caps the rewrites.
- **[A new failure path before preparation]** Every turn on a channel with a glossary now makes MCP
  calls before the user sees anything. → No failure of the fetch ends the turn (spec
  `glossary-prefetch`), and the failure text makes the gap visible to the models.

## Migration Plan

The `glossary` field is optional, so every existing channel validates and behaves as before, except
that research now receives `data_sources_descriptions`. To enable the glossary on a channel, add the
`glossary` object to its `statgpt` server entry in DIAL Core. To roll back, remove it. The private
channel configurations live outside this repository and are updated there.

## No changes required

- `app/mcp_tools.py` (`load_mcp_tools`, `LoadedMcpTools`): the fetch uses `build_mcp_client` and
  `client.session()` directly. Whether a glossary tool reaches an agent stays the
  `tools_to_include` filter's decision.
- `app/research/report_rules.py`: the glossary rule is a model-judged check (D9).
- `app/history.py` and the persisted state: the glossary is not persisted (D1).
- `app/preparation/prompts.py`: `PREP_AGENT_SYSTEM` and `QUERY_REVIEW_SYSTEM` already put
  `{data_sources_descriptions}` inside `<data_sources>`, and `PLAN_REVIEW_SYSTEM` receives neither.
  Only the value filled in changes.
- The request messages of research-review and report-review (`RESEARCH_REVIEW_HUMAN_MESSAGE`,
  `REPORT_REVIEW_REQUEST`): the data sources go into the system prompts (D9).
- `dial_conf/core/applications-template.json`: the field is optional, and the template carries only
  required properties.
- `README.md` environment-variables table and `settings.py`: no environment variable is added.

## Open Questions

- **Is 20 s the right per-call deadline?** It can be tuned from the `Glossary fetched` durations
  once the change is deployed, without changing a spec.
