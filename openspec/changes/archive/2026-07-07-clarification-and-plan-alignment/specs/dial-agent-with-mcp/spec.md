## MODIFIED Requirements

### Requirement: Tool-calling agent over MCP-loaded tools

As of the **clarification-and-plan-alignment** change, each chat completion request SHALL be handled by the **preparation agent** (see that capability) — a single-context tool-calling agent that asks clarifying questions, aligns with the user on a plan, and stops after the plan is approved — and the per-request tool-calling *research* agent SHALL NOT be invoked, nor SHALL an MCP client be constructed during the turn.

The research agent
construction, the MCP-client behavior, and the reflection loop are retained in code
(`AgentRunner`, `ReflectionMiddleware`) but are suspended; the related
research/reflection requirements in this capability (notably **Reflection-driven
research/report loop**) likewise describe retained-but-not-invoked behavior in this
change, to be re-activated (launched from the preparation agent's `start_research`
tool) in a later change.

The preparation agent SHALL be constructed per request via `create_agent` with the
preparation system prompt and exactly the four control tools (`update_query`,
`update_plan`, `approve_plan`, `start_research`) — no MCP-loaded tools, no
subagents, no persistent memory beyond the `PrepState` reconstructed from the DIAL
transcript. The persisted `custom_content.state` for a preparation turn SHALL carry
both the message slice (`messages`) and the preparation state (`prep`); it SHALL
NOT carry a `{dr_thread_id, checkpoint_id}` session pointer, and the app SHALL NOT
maintain a server-side checkpointer or session store.

The retained (currently suspended) research contract is unchanged: when the
research path is active, on each request the app SHALL construct a fresh MCP
client, fetch the current tool list, and run a fresh tool-calling agent to
completion with access only to MCP-loaded tools; the MCP client SHALL NOT be cached
across requests, the app SHALL NOT open a long-lived SSE listening stream, and the
app SHALL NOT issue or retain an `Mcp-Session-Id` (tool-list freshness via
re-polling `tools/list`, matching the generic-RAG `stateless_http=True`
deployment).

#### Scenario: Research agent not invoked in this change
- **WHEN** a chat completion request is processed under this change
- **THEN** the app SHALL handle the request via the preparation agent and SHALL NOT construct an MCP client, fetch tools, or run the tool-calling research agent

#### Scenario: Turn produces clarification, plan, an answer, or the ready-to-research summary — not research
- **WHEN** a chat completion request is processed under this change
- **THEN** the assistant response SHALL be clarifying questions, a proposed/revised plan, a conversational answer, the ready-to-research summary after approval, or the refuse-after-launch message — and SHALL NOT contain a research report

#### Scenario: Preparation turn persists messages and prep, not a session pointer
- **WHEN** a preparation turn completes
- **THEN** the assistant message's `custom_content.state` SHALL contain `messages` and `prep`, and SHALL NOT contain a `dr_thread_id` / `checkpoint_id` pointer
