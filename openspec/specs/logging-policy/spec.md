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
attached to every `create_agent` graph (preparation, researcher, playground); (4) tool call
completed — tool name, tool_call_id, duration, outcome (`success`/`error`), owned by the runner
choke point that creates the DIAL stage; (5) query clarity checked — duration, outstanding
question count, token usage when available including the cached-input-token count, owned by the
`update_query` preparation tool; (6) plan approval checked — duration, approval outcome, token
usage when available including the cached-input-token count, owned by the `approve_plan`
preparation tool; (7) iteration reviewed — iteration number, duration, verdict
(`continue`/`report`), next-plan step count, token usage when available including the
cached-input-token count, owned by the reviewer node; (8) report generated — duration, report
length, token usage when available including the cached-input-token count, owned by the report
node; (9) request completed — outcome (`completed`/`failed`), total duration, and on failure the
same `error_reference` as the ERROR record. The `finish_iteration` sentinel tool SHALL NOT
produce a tool-call event above DEBUG.

#### Scenario: Successful research turn reads as a skeleton at INFO

- **WHEN** a turn runs preparation, hands off to research, and streams a report, with all log
  levels at INFO
- **THEN** the log contains the request-received, preparation-completed, model-call, tool-call,
  iteration-reviewed, report-generated, and request-completed events, none carrying message
  bodies or tool arguments

#### Scenario: Tool failure is visible in the skeleton

- **WHEN** an MCP tool execution returns a `ToolMessage` with `status == "error"`
- **THEN** the tool-call event fires at INFO with `outcome=error`

#### Scenario: finish_iteration stays out of the INFO skeleton

- **WHEN** the researcher calls the `finish_iteration` sentinel
- **THEN** no INFO tool-call event is emitted for it

#### Scenario: Failed turn closes the narrative

- **WHEN** a turn fails after the request-received event
- **THEN** the request-completed event fires with `outcome=failed` and the same
  `error_reference` carried by the ERROR record

#### Scenario: Cached input tokens are visible in token usage

- **WHEN** a model response reports cached input tokens (LangChain
  `usage_metadata.input_token_details["cache_read"]`)
- **THEN** the corresponding model-call, query-clarity-checked, plan-approval-checked,
  iteration-reviewed, or report-generated event's token-usage field includes the cached count
  (counts only — no payload content)

#### Scenario: Usage absent stays graceful

- **WHEN** a model response carries no usage metadata
- **THEN** the event still fires, with its token-usage field marked unavailable

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
