## ADDED Requirements

### Requirement: Opik tracing of agent runs when configured

The app SHALL attach an `opik.integrations.langchain.OpikTracer` callback to the per-request LangChain agent's streaming invocation **iff** Opik tracing is enabled via configuration (`OpikSettings.tracing_enabled` is true). When attached, the tracer SHALL capture the full hierarchical trace of the turn — the agent graph run, the underlying LLM call, and every MCP tool call (including arguments, results, and errors) — without altering the agent's outputs, the DIAL stages emitted, the assistant message content, or the top-level error funnel. When Opik tracing is not enabled, the agent SHALL run with no Opik callback attached and SHALL produce identical observable behaviour to a build that does not depend on Opik.

#### Scenario: Tracer attached when enabled
- **WHEN** `OPIK_TRACING_ENABLED=true` is set and the local Opik stack (started via `make opik-up`) is reachable, and a chat completion request is processed
- **THEN** the agent's streaming invocation SHALL be configured with an `OpikTracer` callback, and the resulting trace in Opik SHALL contain the agent run, the LLM call, and a span per MCP tool invocation with their inputs, outputs, and timings

#### Scenario: Tracer absent when disabled
- **WHEN** `OPIK_TRACING_ENABLED` is unset or false and a chat completion request is processed
- **THEN** no `OpikTracer` SHALL be constructed or attached, no Opik network calls SHALL be made by the app, and the chat completion SHALL produce the same DIAL stages and assistant content as a run with the Opik dependency absent

#### Scenario: Tracing failure does not break the turn
- **WHEN** Opik tracing is enabled but the configured Opik instance is unreachable mid-turn
- **THEN** the chat completion SHALL still complete successfully (the agent SHALL produce its assistant text and tool stages as usual), with any tracer-side exception either swallowed by LangChain's callback machinery or absorbed by the existing top-level error funnel — i.e. tracing failures SHALL never produce a non-200 response and SHALL never replace successful assistant content with the friendly error string

#### Scenario: Tool error is captured as a tool span
- **WHEN** Opik tracing is enabled and an MCP tool raises an error during a turn (caught by `handle_tool_error`)
- **THEN** the corresponding tool call SHALL appear in the Opik trace as a span carrying the tool arguments and the error text, while the existing DIAL `error ❌` stage and agent retry behaviour SHALL be unchanged
