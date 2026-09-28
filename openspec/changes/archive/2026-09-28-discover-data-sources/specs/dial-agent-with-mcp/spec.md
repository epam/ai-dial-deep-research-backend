## MODIFIED Requirements

### Requirement: Tool-calling agent over MCP-loaded tools

Each chat completion request SHALL first be handled by the preparation agent (see
the **clarification-and-plan-alignment** capability). When the preparation agent
approves a plan and calls `start_research`, the app SHALL run the **research
execution graph** (see the **research-execution** capability) in the same turn; the
research agent is the graph's **research-agent node**, not a directly-invoked
first-message agent.

The research-agent node SHALL be a fresh per-request LangChain `create_agent` over the
tools fetched from a freshly-constructed MCP client, plus one sentinel tool
(`finish_iteration`). It SHALL have access only to MCP-loaded tools and that
sentinel — no other built-in tools, subagents, skills, or persistent memory beyond
the graph state.

A tool an MCP server advertises for the **application** to call, rather than for an agent to call,
SHALL be excluded from every list bound to a model — today that is the file-sharing tool of the
**report-citations** capability. Such a tool SHALL be resolved from the server's full advertised
tool list rather than through that server's `tools_to_include` filter, which states which tools the
research agent may call; naming it in that filter SHALL NOT cause the agent to be offered it, and
omitting it SHALL NOT stop the app from calling it. An application-called tool SHALL have the agent tools'
error handling **disabled** on it: the agent tools convert a tool error into an error result message
so the model can retry, whereas the app needs the failure itself so it can fall back (see
**report-citations**). Disabling is an explicit act rather than an omission, because the MCP tool
adapter installs that conversion by default — a tool nobody touches still answers an error as
ordinary result content — so the app SHALL clear it on this tool rather than rely on it being
absent.

Research-agent SHALL be run with **forced tool choice** — every model
call re-issued with `tool_choice="any"` by an in-process `AgentMiddleware` — so every
model step emits a tool call and the model can never emit a free-form assistant
message.

A research-agent iteration therefore ends **only** when research-agent calls
`finish_iteration`, which SHALL be declared `return_direct=True`: the agent loop
returns as soon as that tool executes, with no further model round-trip. The two
mechanisms together make `finish_iteration` the single exit from a research-agent
iteration — the loop's other exit is a tool-call-free assistant message, which forced
tool choice makes unreachable — so research-agent cannot stop early and leave the graph
without a research-review verdict. Phase
control lives in the research graph's edges (see the **research-execution**
capability), not in middleware over a single agent's control flow.

The MCP client SHALL NOT be cached across requests, the app SHALL NOT open a
long-lived SSE listening stream on the MCP endpoint, and the app SHALL NOT issue or
retain an `Mcp-Session-Id`. Tool-list freshness across requests is achieved by
re-polling `tools/list` at the start of every turn that loads tools for a model,
matching the generic-RAG server's `stateless_http=True` deployment; persistent-session
features (long-lived sessions, `Mcp-Session-Id`, `Last-Event-ID` resumability,
`notifications/tools/list_changed`, `notifications/resources/*`,
`notifications/prompts/list_changed`) are out of scope for this capability.

A turn on a channel with a dataset server SHALL also construct a per-turn MCP client **before the
preparation agent runs**, for the data-sources fetch (see **data-sources-discovery**). The rules
above apply to it: it is not cached across requests and keeps no session. It calls the configured
list-datasets, dataset-structure and glossary tools by name and does not poll `tools/list` to
discover tools, because it offers no tool to a model. These tools are not application-called tools in the sense above: the
app calls them, but they stay in the agent's tools whenever the server's `tools_to_include` filter
offers them, the way the list-datasets tool does at the citation step.

#### Scenario: research-agent invokes an MCP tool

- **WHEN** research-agent needs information from the knowledge base during an iteration
- **THEN** it SHALL emit a tool call, the MCP server SHALL execute the tool, and the result SHALL be incorporated into the accumulated research context

#### Scenario: research-agent is run only after plan approval

- **WHEN** a chat completion request is processed and no plan has been approved yet
- **THEN** the research-agent node SHALL NOT run and no MCP client SHALL be constructed for research; the turn SHALL produce only preparation output. A client constructed for the data-sources fetch before preparation is not constructed for research

#### Scenario: Per-request agent and MCP scoping

- **WHEN** the MCP server's tool list changes between two requests that reach research (e.g. the generic-RAG MCP server is redeployed)
- **THEN** the later research run SHALL discover and use the new tool list without restarting the dial-deep-research process

#### Scenario: No session reuse across requests

- **WHEN** the app processes two requests that each construct an MCP client
- **THEN** the app SHALL construct a new MCP client for the second rather than reusing the first's, the second's MCP traffic SHALL NOT carry an `Mcp-Session-Id` derived from the first, and any in-flight notifications received during the first request's POST SSE response SHALL have terminated with that request

#### Scenario: An application-called tool is kept out of the agent's tools

- **WHEN** a configured MCP server advertises a file-sharing tool and a research turn starts
- **THEN** the tools bound to research-agent SHALL exclude it, whether or not that server's `tools_to_include` names it, and the app SHALL still be able to invoke it outside the agent

#### Scenario: One tool-list fetch serves both the agent and the app

- **WHEN** the app loads tools for a server that advertises search tools and a file-sharing tool
- **THEN** the server's advertised tool list SHALL be fetched for that turn and split into the agent's tools and the application-called tool, without a second `tools/list` round trip for the same server

#### Scenario: A preparation-only turn fetches the data sources

- **WHEN** a turn on a channel with a dataset server ends in preparation, without starting research
- **THEN** the app SHALL have constructed one per-turn MCP client for the data-sources fetch, SHALL
  NOT have polled `tools/list` to discover tools, and SHALL NOT reuse that client in a later
  request

#### Scenario: The fetched tools stay with the agent when the filter offers them

- **WHEN** a channel names a dataset-structure tool and configures a glossary, and its
  `tools_to_include` names the dataset-structure tool and the term-definitions tool
- **THEN** research-agent SHALL be offered both tools, and the app SHALL still call them itself in
  the data-sources fetch
