## MODIFIED Requirements

### Requirement: INFO request skeleton

At INFO level the service SHALL emit a metadata-only request lifecycle skeleton, each event a
stable message prefix plus `key=value` fields: (1) request received — deployment, message count,
owned by the chat completion; (2) preparation completed — duration, `research_started`, plan
step count, outstanding question count, owned by `DeepResearchCompletion`; (3) model call
completed — agent name, duration, finish kind, requested tool names, content length, token usage
when available including the cached-input-token count, owned by a model-call logging middleware
attached to every `create_agent` graph (preparation, research-agent, playground); (4) tool call
completed — tool name, tool_call_id, duration, outcome (`success`/`error`), owned by the runner
choke point that creates the DIAL stage; (5) query clarity checked — duration, outstanding
question count, token usage when available including the cached-input-token count, owned by the
`update_query` preparation tool; (6) plan approval checked — duration, approval outcome, token
usage when available including the cached-input-token count, owned by the `approve_plan`
preparation tool; (7) research iteration reviewed — iteration number, duration, verdict
(`continue`/`report`), next-plan step count, token usage when available including the
cached-input-token count, owned by the research-review node; (7a) research iteration budget
exhausted — iteration count, owned by the research router: the last permitted iteration gets no
review call, so no research-iteration-reviewed event can carry the hand-off; (8) report generated — draft ordinal
(1 for the first draft, incrementing per revision), duration, report length in characters and in
measured words, token usage when available including the cached-input-token count, owned by the
report node; (8a) report reviewed — draft ordinal, duration, the `outcome`
(`deliver`/`revise`), an `error` field naming the exception kind when the review call failed and
nothing when it succeeded, the draft's measured word count, the configured ceiling, the
**number** of violations recorded against the draft, and token usage when available including the
cached-input-token count, owned by the report-review node. That number counts one combined list —
the app's own rule violations followed by the review model's — because that list is what a
revision acts on. The violations themselves are LLM response text and SHALL NOT appear in this
record or any other, at any level — they are carried to the user in a DIAL stage instead (see
**report-composition**); (8b) report delivered without review — draft ordinal, the configured
version budget, the draft's measured word count, owned by the research runner: an exhausted budget
makes no review call, so no report-reviewed event can carry it; (9) request completed — outcome
(`completed`/`failed`), total duration, and on failure the same `error_reference` as the ERROR
record. Neither the `finish_iteration` sentinel tool nor the `update_status` tool SHALL produce a
tool-call event above DEBUG: neither performs research, and `update_status` is surfaced to the user
as the activity stage instead (see **dial-agent-with-mcp**).

One `outcome` field carries the decision because the review model has no verdict field of its own:
an empty violation list is its approval (see **report-composition**), and the app folds its own
rule violations into that list before the decision is taken. The record therefore states that a
revision was required and how many violations it acts on, not whether the app's rules or the
review model raised them.

A report delivered with the review still unsatisfied SHALL be visible in the logs: an exhausted
version budget fires the report-delivered-without-review event, and a populated `error` field on
the report-reviewed event marks a review call that did not produce a verdict; such a call SHALL
additionally log a WARNING naming the failure kind.

A **failed revision** is recorded differently, because neither of the two report events can carry it:
the report-review node never runs for it (the graph leaves the loop instead, see
**research-execution**), and the report-generated event SHALL NOT fire for a draft that was never
produced. Its record SHALL therefore be a WARNING owned by the report node, naming the failure kind,
the ordinal of the revision that failed, and the ordinal of the draft delivered in its place. The
delivered report is the one an earlier report-generated event already recorded.
None of these SHALL log report text — counts, outcomes, and durations only, per the content
allowlist.

#### Scenario: Successful research turn reads as a skeleton at INFO

- **WHEN** a turn runs preparation, hands off to research, and delivers a report on an instance
  whose version budget is above one, with all log levels at INFO
- **THEN** the log contains the request-received, preparation-completed, model-call, tool-call,
  research-iteration-reviewed, report-generated, report-reviewed, and request-completed events, none
  carrying message bodies or tool arguments

#### Scenario: Tool failure is visible in the skeleton

- **WHEN** an MCP tool execution returns a `ToolMessage` with `status == "error"`
- **THEN** the tool-call event fires at INFO with `outcome=error`

#### Scenario: finish_iteration stays out of the INFO skeleton

- **WHEN** research-agent calls the `finish_iteration` sentinel
- **THEN** no INFO tool-call event is emitted for it

#### Scenario: update_status stays out of the INFO skeleton

- **WHEN** research-agent calls `update_status`
- **THEN** no INFO tool-call event is emitted for it

#### Scenario: Failed turn closes the narrative

- **WHEN** a turn fails after the request-received event
- **THEN** the request-completed event fires with `outcome=failed` and the same
  `error_reference` carried by the ERROR record

#### Scenario: Cached input tokens are visible in token usage

- **WHEN** a model response reports cached input tokens (LangChain
  `usage_metadata.input_token_details["cache_read"]`)
- **THEN** the corresponding model-call, query-clarity-checked, plan-approval-checked,
  research-iteration-reviewed, report-generated, or report-reviewed event's token-usage field includes the
  cached count (counts only — no payload content)

#### Scenario: Usage absent stays graceful

- **WHEN** a model response carries no usage metadata
- **THEN** the event still fires, with its token-usage field marked unavailable

## ADDED Requirements

### Requirement: Status-tool misuse is logged as a warning

Two ways of calling `update_status` waste a model round trip or produce nothing the user can act
on, and the service SHALL record each as a WARNING so the pattern is diagnosable without reading
payloads: an assistant message whose only tool call is `update_status`, and an assistant message
carrying more than one `update_status` call.

Each record SHALL be emitted once per assistant message rather than once per tool call, and SHALL
carry counts only — how many tool calls the message held and how many of them were status calls.
The announced status text is a tool-call argument value and SHALL NOT appear in these records or
in any other, at any level, per the content allowlist.

#### Scenario: A status-only message warns once

- **WHEN** research-agent produces an assistant message whose only tool call is `update_status`
- **THEN** the service SHALL emit one WARNING naming the condition and the tool-call counts, and
  the record SHALL NOT contain the announced status text

#### Scenario: Repeated status calls in one message warn once

- **WHEN** research-agent produces an assistant message carrying three `update_status` calls
- **THEN** the service SHALL emit one WARNING for that message rather than one per call, carrying
  the number of status calls

#### Scenario: Correct usage is silent

- **WHEN** research-agent calls `update_status` exactly once alongside at least one research tool
- **THEN** no misuse WARNING SHALL be emitted for that message
