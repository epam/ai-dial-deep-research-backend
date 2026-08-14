# logging-policy

## Purpose

The service's logging policy: what each log level means (with a single-writer ownership rule
for ERROR), the metadata-only INFO request skeleton that makes a request's lifecycle readable
during incidents, the content allowlist that keeps message bodies, tool arguments, response
bodies, header values, and URL query strings out of log records at every level, and the
`LOG_PAYLOADS` opt-in that is the only path to payload-bearing records.

## Requirements

### Requirement: Log level semantics and ERROR ownership

The service SHALL emit log records according to these level semantics — DEBUG: developer
diagnostics (control flow, intermediate values, structure summaries); INFO: the operational
narrative (startup/configuration summaries plus the request skeleton), metadata-only; WARNING:
unexpected conditions the service handled, after which the request continues, possibly degraded;
ERROR: failures that affected the request outcome. A failure SHALL be logged at ERROR exactly
once, by the layer that owns its final handling (`raise_dial_error` in `error_resolution`);
layers that hand a failure onward — to a fallback path or by raising for an upstream handler —
SHALL log at most WARNING. Routine, expected per-request outcomes SHALL log at DEBUG.

#### Scenario: Failed request produces exactly one ERROR

- **WHEN** a turn fails with an unhandled exception
- **THEN** exactly one ERROR record is emitted (by `raise_dial_error`), carrying the stack trace
  and an 8-character `error_reference`

#### Scenario: Handled degraded condition logs WARNING, not ERROR

- **WHEN** a persisted assistant message's `custom_content.state` fails `DialState` validation
  and the turn falls back to visible-text history
- **THEN** the record is WARNING, and no ERROR is emitted for the condition

#### Scenario: Routine history fallbacks log at DEBUG

- **WHEN** an assistant message carries no custom content, or custom content whose state is not
  a dictionary (a legacy or plain-text turn)
- **THEN** the fallback records are DEBUG, not WARNING

#### Scenario: Chat-model construction logs at DEBUG

- **WHEN** a chat model is constructed for a request
- **THEN** the construction-parameters record is DEBUG, not INFO

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

### Requirement: Content allowlist for log records

The service's own call sites SHALL NOT emit user/system/assistant/tool message bodies, tool-call
argument values, tool or LLM response bodies, attachment content, header values, or URL query
strings and fragments in log records at any level. Allowed values are structure: roles, counts,
sizes and lengths, durations, tool/deployment/model/agent names, identifiers, statuses and
outcome enums, error codes and types, finish reasons, MIME types, HTTP status codes, header
names, and URLs stripped to scheme, host, and path (DIAL relative `files/...` paths are allowed
once any query string is stripped). Stack traces and third-party exception text are allowed, but
the service's own exceptions SHALL NOT embed payload content in their messages, and a pydantic
`ValidationError` over content-bearing input (persisted conversation state, application
properties) SHALL be logged as its error count plus `loc` paths and error types — never its
rendered text or traceback.

#### Scenario: Image download failure logs a stripped URL

- **WHEN** an image download from DIAL files fails and the failure is logged
- **THEN** the logged URL contains no query string or fragment

#### Scenario: State validation failure logs structure only

- **WHEN** `DialState` validation of a persisted assistant state fails
- **THEN** the record carries the error count and the failing `loc` paths with error types, and
  no fragment of the persisted messages

#### Scenario: Application-properties validation failure logs structure only

- **WHEN** an instance's application properties fail validation
- **THEN** the WARNING carries the error count and the failing `loc` paths with error types, and
  no property values

### Requirement: Payload-debugging switch

Payload-bearing log records SHALL exist only behind the `LOG_PAYLOADS` opt-in: when it is
`false` (the default), the service SHALL emit no payload content at any level; when `true`, the
prompt-logging middleware SHALL be attached to every `create_agent` graph and SHALL log the
assembled LLM request (system message, messages, tool names) at DEBUG, with every string
truncated to `LOG_PAYLOADS_MAX_LENGTH` characters and an ellipsis marker recording the original
length. The switch SHALL be additive to the level: payload records are DEBUG-level, so
`LOG_PAYLOADS=true` alone (with levels at INFO) reveals nothing.

#### Scenario: Switch off means no payload records anywhere

- **WHEN** `LOG_PAYLOADS` is unset and every log level is DEBUG
- **THEN** no record contains prompt or message-body content from the service's own call sites

#### Scenario: Switch on emits truncated payload records at DEBUG

- **WHEN** `LOG_PAYLOADS=true` and `DEEP_RESEARCH_LOG_LEVEL=DEBUG`
- **THEN** each agent model call logs the assembled request with strings longer than
  `LOG_PAYLOADS_MAX_LENGTH` truncated and marked with the original length

#### Scenario: Switch alone reveals nothing

- **WHEN** `LOG_PAYLOADS=true` and all log levels are INFO
- **THEN** no payload record reaches any handler
