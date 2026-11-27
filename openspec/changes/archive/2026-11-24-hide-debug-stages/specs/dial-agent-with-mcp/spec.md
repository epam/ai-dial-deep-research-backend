# Spec Delta

## MODIFIED Requirements

### Requirement: Tool execution surfaced as timed DIAL stages
For every tool the agent invokes during a request, the app SHALL emit a single DIAL "result" stage carrying both the input arguments and the tool's output. The one exception is `update_status`, which carries no result and SHALL produce no result stage — it is surfaced as the activity stage described in **Research progress surfaced as one open activity stage**, and the app SHALL NOT render its arguments or its acknowledgement anywhere in the stage channel. Titles follow the normalized form `[TOOL] <tool_name> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where emoji ∈ `{✅, ❌}` marks success and failure. The mark carries the outcome on its own, so the title SHALL NOT spend width on a word for it. Stage timestamps SHALL bracket the actual execution window (start when the call is dispatched to the MCP server, end when the result is received). When the tool returns an error (caught by `handle_tool_error` instead of bubbling), the stage SHALL be marked ❌ so the failure stands out in the chat UI. Stage content is rendered as markdown by DIAL, so both the input arguments and the tool output SHALL be wrapped in fenced code blocks (single newlines would otherwise collapse), making multi-line payloads — JSON args, plain-text results, error tracebacks — readable verbatim.

The result stages are debug stages (see **debug-stages**). The app SHALL emit them only when the
deployment shows debug stages, and this requirement describes a result stage when it is emitted.

#### Scenario: Tool result stage carries start, end, elapsed, input, and output
- **WHEN** the tool result returns from the MCP server
- **THEN** the app SHALL emit a stage whose title includes the start timestamp, end timestamp, and elapsed seconds, and whose body contains an "Input" section with the JSON-fenced arguments followed by an "Output" section with the fenced tool result content

#### Scenario: Tool error stage signals failure but does not abort the turn
- **WHEN** an MCP tool raises (e.g. argument validation rejects the LLM's call) and the error is caught by the per-tool error handler
- **THEN** the app SHALL emit a stage whose title is marked ❌ (e.g. `[TOOL] <tool_name> ❌ (...)`), whose body carries the JSON-fenced "Input" section followed by a fenced "Error" section with the error text; the agent SHALL receive the same error text as a `ToolMessage` in its next step and MAY retry with corrected arguments without the chat completion failing

#### Scenario: The status tool produces no result stage
- **WHEN** research-agent calls `update_status` beside a research tool in one assistant message
- **THEN** the app SHALL emit a result stage for the research tool only, and the run's stage channel SHALL contain no `[TOOL] update_status` stage and no rendering of the status argument as stage content
