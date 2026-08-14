## MODIFIED Requirements

### Requirement: Tool execution surfaced as timed DIAL stages
For every tool the agent invokes during a request, the app SHALL emit a single DIAL "result" stage carrying both the input arguments and the tool's output. The one exception is `update_status`, which carries no result and SHALL produce no result stage — it is surfaced as the activity stage described in **Research progress surfaced as one open activity stage**, and the app SHALL NOT render its arguments or its acknowledgement anywhere in the stage channel. Titles follow the normalized form `[TOOL] "<tool_name>" - <action> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where action ∈ `{result, error}` and emoji ∈ `{✅, ❌}` respectively. Stage timestamps SHALL bracket the actual execution window (start when the call is dispatched to the MCP server, end when the result is received). When the tool returns an error (caught by `handle_tool_error` instead of bubbling), the stage SHALL use the `error ❌` action variant so the failure stands out in the chat UI. Stage content is rendered as markdown by DIAL, so both the input arguments and the tool output SHALL be wrapped in fenced code blocks (single newlines would otherwise collapse), making multi-line payloads — JSON args, plain-text results, error tracebacks — readable verbatim.

#### Scenario: Tool result stage carries start, end, elapsed, input, and output
- **WHEN** the tool result returns from the MCP server
- **THEN** the app SHALL emit a stage whose title includes the start timestamp, end timestamp, and elapsed seconds, and whose body contains an "Input" section with the JSON-fenced arguments followed by an "Output" section with the fenced tool result content

#### Scenario: Tool error stage signals failure but does not abort the turn
- **WHEN** an MCP tool raises (e.g. argument validation rejects the LLM's call) and the error is caught by the per-tool error handler
- **THEN** the app SHALL emit a stage whose title uses the `error ❌` variant (e.g. `[TOOL] "<tool_name>" - error ❌ (...)`), whose body carries the JSON-fenced "Input" section followed by a fenced "Error" section with the error text; the agent SHALL receive the same error text as a `ToolMessage` in its next step and MAY retry with corrected arguments without the chat completion failing

#### Scenario: The status tool produces no result stage
- **WHEN** research-agent calls `update_status` beside a research tool in one assistant message
- **THEN** the app SHALL emit a result stage for the research tool only, and the run's stage channel SHALL contain no `[TOOL] "update_status"` stage and no rendering of the status argument as stage content

## ADDED Requirements

### Requirement: Research progress surfaced as one open activity stage

While the research graph runs, the app SHALL keep exactly one DIAL stage open at all times, whose title names what research is doing at that moment. The app SHALL open the first such stage before the graph starts, and SHALL replace it — closing the open one, then opening a new one — each time research-agent announces a step through `update_status` and each time research-review, report or report-review is entered. Replacement SHALL be the only way the title changes, since a DIAL stage name can be appended to but never rewritten.

The activity stage SHALL carry a title only: no stage content, no bracketed prefix of the kind result stages use, and no elapsed time or timestamps. A closing activity stage means a new step has started, not that the closed step finished — work announced earlier may still be running — so the app SHALL NOT stamp it with any duration, and SHALL NOT open and close an activity stage at the same instant, which would render as a completed step.

One assistant message SHALL change the activity stage at most once. When a message carries several `update_status` calls, the app SHALL join their texts into one title and open a single stage. When a message calls `update_status` together with `finish_iteration`, the app SHALL leave the activity stage untouched.

The app SHALL close the open activity stage before the turn ends, on both the success and the failure path, using the failed status when the run is ending in an error. No activity stage SHALL be left open when the response completes.

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
