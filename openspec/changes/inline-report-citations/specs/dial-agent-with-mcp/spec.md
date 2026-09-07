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
re-polling `tools/list` at the start of every turn that constructs a client,
matching the generic-RAG server's `stateless_http=True` deployment; persistent-session
features (long-lived sessions, `Mcp-Session-Id`, `Last-Event-ID` resumability,
`notifications/tools/list_changed`, `notifications/resources/*`,
`notifications/prompts/list_changed`) are out of scope for this capability.

#### Scenario: research-agent invokes an MCP tool

- **WHEN** research-agent needs information from the knowledge base during an iteration
- **THEN** it SHALL emit a tool call, the MCP server SHALL execute the tool, and the result SHALL be incorporated into the accumulated research context

#### Scenario: research-agent is run only after plan approval

- **WHEN** a chat completion request is processed and no plan has been approved yet
- **THEN** the research-agent node SHALL NOT run and no MCP client SHALL be constructed for research; the turn SHALL produce only preparation output

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

### Requirement: Research progress surfaced as one open activity stage

From the moment the research graph starts until the report is delivered, the app SHALL keep exactly one DIAL stage open at all times, whose title names what the turn is doing at that moment. The app SHALL open the first such stage before the graph starts, and SHALL replace it — closing the open one, then opening a new one — each time research-agent announces a step through `update_status`, each time research-review, report or report-review is entered, and once more when the graph has finished and the citation step begins (see **report-citations**), whose server-side copies can take a moment while the turn would otherwise look finished. Replacement SHALL be the only way the title changes, since a DIAL stage name can be appended to but never rewritten.

The activity stage SHALL carry a title only: no stage content, no bracketed prefix of the kind result stages use, and no elapsed time or timestamps. A closing activity stage means a new step has started, not that the closed step finished — work announced earlier may still be running — so the app SHALL NOT stamp it with any duration, and SHALL NOT open and close an activity stage at the same instant, which would render as a completed step.

One assistant message SHALL change the activity stage at most once. When a message carries several `update_status` calls, the app SHALL join their texts into one title and open a single stage. When a message calls `update_status` together with `finish_iteration`, the app SHALL leave the activity stage untouched.

The app SHALL close the open activity stage before the turn ends, on both the success and the failure path, using the failed status when the run is ending in an error. No activity stage SHALL be left open when the response completes. The citation step's stage SHALL be closed before the report text is appended, so the content never arrives under an open stage.

A step with nothing to do SHALL open no stage. The citation step on a turn whose draft cites nothing and carries no hyperlink finishes in microseconds, and opening a stage there would open and close it at the same instant — the thing this requirement forbids two paragraphs above. The app SHALL therefore open the citation step's stage only once it has work: a file-sharing call to make, or edits to apply to the draft.

#### Scenario: A status announcement replaces the open stage

- **WHEN** research-agent calls `update_status` while an activity stage is open
- **THEN** the app SHALL close the open stage and open a new one titled with the announced status, so exactly one activity stage is open before and after

#### Scenario: An activity stage stays open across the tool calls it covers

- **WHEN** research-agent announces a step and then runs several research tools
- **THEN** the activity stage SHALL remain open while those tools run and their result stages are emitted, and SHALL close only when the next announcement or node entry replaces it

#### Scenario: Several announcements in one message yield one stage

- **WHEN** one assistant message carries more than one `update_status` call and no `finish_iteration`
- **THEN** the app SHALL open exactly one activity stage whose title carries every announced status, and no activity stage SHALL be opened and closed at the same instant

#### Scenario: An announcement ending the iteration is ignored

- **WHEN** one assistant message carries both `update_status` and `finish_iteration`
- **THEN** the app SHALL neither close the open activity stage nor open a new one

#### Scenario: A node entry replaces the open stage

- **WHEN** research-review, report or report-review begins
- **THEN** the app SHALL replace the open activity stage with one naming that node's work, so no LLM call in the research graph runs without a stage describing it

#### Scenario: The activity stage carries no timing and no body

- **WHEN** an activity stage is closed
- **THEN** its title SHALL be unchanged from when it was opened, carrying no elapsed time, start time or end time, and the stage SHALL have received no content

#### Scenario: A failing run closes the open stage

- **WHEN** the research graph raises and the turn is delivered as a DIAL error
- **THEN** the app SHALL close the open activity stage with the failed status before the error is raised, and SHALL NOT leave a stage whose status is still unset

#### Scenario: The citation step is announced while it works

- **WHEN** the research graph has finished and the citation step has cited documents to resolve through the file-sharing tool
- **THEN** the app SHALL replace the graph's last activity stage with one naming the citation work, and SHALL close it before the report text is appended to the assistant content

#### Scenario: A citation step with nothing to do opens no stage

- **WHEN** the settled draft cites no document and carries no hyperlink, so the citation step has neither a call to make nor an edit to apply
- **THEN** the app SHALL open no activity stage for it, rather than one that opens and closes at the same instant
