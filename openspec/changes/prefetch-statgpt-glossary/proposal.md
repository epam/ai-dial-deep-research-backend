## Why

A channel that serves datasets through a StatGPT MCP server can also expose a glossary, and a
channel can require that a report always uses the glossary's terminology where it is relevant.
Today a model sees a glossary term only if the research agent happens to call a glossary tool, so
nothing guarantees that the preparation agent, the report writer or the report reviewer ever see
the glossary. A glossary of a hundred terms, each defined in a short paragraph, is on the
order of 5,000 tokens, which is small enough to put into every call's context. So the app fetches
it on every user turn instead of leaving it to the agent.

The StatGPT backend stays unchanged. The app calls the two glossary tools the server already
exposes, a list-terms tool and a term-definitions tool, so moving the glossary to a RAG-based
lookup later needs no backend work.

## What Changes

- **A statgpt MCP server may configure a glossary.** The new optional `glossary` object on the
  server's configuration names the list-terms tool (`list_terms_tool`), the term-definitions tool
  (`definitions_tool`), and the largest number of terms one term-definitions call may request
  (`max_terms_per_definitions_call`). The limit must be configured because the server states it only
  as text in the tool's argument description. Only a `statgpt` server may set the object.
- **The app fetches the glossary once per turn, before the preparation agent runs.** It calls the
  list-terms tool with at most 3 attempts. It then requests every listed term's definition in
  concurrent batches of at most `max_terms_per_definitions_call` terms, in at most 3 rounds. Each
  round after the first re-requests, in new batches, every term that did not resolve in the round
  before. A term does not resolve when its batch call failed or when the server reported it as not
  found. After the last round, the app logs the number of unresolved terms at WARNING. An
  unresolved term stays in the glossary without a definition.
- **The glossary is rendered as one string.** The string is `Glossary terms:` followed by a JSON
  array. The array has one object per listed term, in list order. Each object carries an `index`
  field that counts from 1, followed by every field of the term's record in the term-definitions
  response. An unresolved term carries the fields the list-terms tool gave it and `"definition":
  null`. When the list-terms tool fails 3 times, the string is `Glossary terms:` followed by
  `failed to obtain list of terms`, and the app logs that at WARNING.
- **The glossary is appended to `prompts.data_sources_descriptions`**, and the combined string goes
  to every model call that receives `data_sources_descriptions` today. Those calls are the
  preparation agent, the query review inside `update_query`, and the playground agent.
- **Every node of the research graph receives the combined data-sources string**: the research
  agent, research review, the report writer and the report reviewer, each in its system prompt.
  None of them receives `data_sources_descriptions` today. They receive it on every channel, and
  the glossary is appended when the channel configures one.
- **The report writer is told to use the glossary's terminology, and the reviewer checks it.** On a
  channel whose glossary listed at least one term, the report writer's prompt carries the rule that
  the report uses the glossary's term for a concept wherever a glossary term applies. The report
  reviewer, which sees the glossary through its data-sources string, gets a check of the same
  rule.
- **An agent that has the term-definitions tool gets an extra instruction.** The instruction tells
  the agent to request, with that tool, the definitions of terms that have none and whose names look
  relevant. It is added to the prompts of the research agent and the playground agent, and only when
  the term-definitions tool is among that agent's tools. Every other call sees unresolved terms
  marked by the null definition, and gets no such instruction.
- **The playground fetches the glossary in its own turn**, with the same rules.
- A channel without a `glossary` object makes no glossary calls, and its prompts carry no glossary.
  The only difference such a channel sees is that every node of the research graph now receives
  `data_sources_descriptions`.

## Capabilities

### New Capabilities

- `glossary-prefetch`: fetching a channel's glossary once per turn from its statgpt MCP server: the
  retry rules for the list-terms call and the definition rounds, the rendered string, the result
  when the fetch fails, the calls that receive it (including the playground agent, whose inputs no
  other spec owns), and the log records of the fetch.

### Modified Capabilities

- `application-config-schema`: a new requirement "A statgpt MCP server may declare its glossary
  tools", covering the `glossary` object, its three fields, and the rule that only a `statgpt`
  server may set it.
- `clarification-and-plan-alignment`: the requirement "Every preparation LLM call's inputs and
  outputs are specified" says that the preparation agent and the query review receive the
  data-sources string with the glossary appended.
- `research-execution`: the requirement "Every research LLM call's inputs and outputs are
  specified" says that all four research graph calls (research-agent, research-review, the report
  writer and report-review) receive the combined data-sources string, and that the research agent
  gets the missing-definitions instruction when its tools include the term-definitions tool.
- `report-composition`: a new requirement "A report uses the glossary's terminology" gives the
  report writer the instruction and the report reviewer the check. The requirement "The rules the
  app can check itself are checked in Python, not by a model" adds the data-sources string to what
  the reviewer receives and the new check to the reviewer's own checks.
- `dial-agent-with-mcp`: the requirement "Tool-calling agent over MCP-loaded tools" says that a
  turn on a channel with a glossary constructs a per-turn MCP client before preparation, and that
  the glossary calls name their tools directly instead of polling `tools/list`.

## Impact

- `src/dial_deep_research/app_properties.py`: the new `GlossaryTools` model, the `glossary` field
  on `MCPClientSettings` with its validator, and an `ApplicationProperties` accessor that returns
  the one configured glossary.
- `src/dial_deep_research/app/glossary.py` (new): the fetch, the retry rounds, and the rendering.
- `src/dial_deep_research/app/completion.py`: fetches the glossary before preparation and passes it
  to both runners.
- `src/dial_deep_research/app/preparation/runner.py`, `app/preparation/agent.py`,
  `app/preparation/tools.py`: receive the combined data-sources string in place of
  `prompts.data_sources_descriptions`.
- `src/dial_deep_research/app/research/runner.py`, `app/research/graph.py`,
  `app/research/nodes.py`: pass the combined string to every node of the research graph.
- `src/dial_deep_research/app/research/prompts.py`: a `<data_sources>` block in
  `RESEARCH_AGENT_SYSTEM_PROMPT`, `RESEARCH_REVIEW_SYSTEM_PROMPT`, `REPORT_SYSTEM_PROMPT` and
  `REPORT_REVIEW_SYSTEM_PROMPT`, the missing-definitions instruction, the glossary-terminology rule
  for the writer, and the new check in `REPORT_REVIEW_SYSTEM_PROMPT`.
- `src/dial_deep_research/app/playground/runner.py`, `app/playground/agent.py`,
  `app/playground/prompts.py`: fetch the glossary, and add the combined string and the instruction.
- `docs/generated-app-schema.json`: regenerated by `make format`.
- `docs/architecture.md`: the glossary fetch at the start of the turn, and the data-sources string
  as a new input of every research graph node.
- Tests: `tests/test_app_properties.py` for the validator, a new `tests/test_glossary.py` for the
  rounds and the rendering, and the prompt tests that cover the changed templates.
- No new dependency and no new environment variable. The glossary is optional, so
  `dial_conf/core/applications-template.json` does not change.
