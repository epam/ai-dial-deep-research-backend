# logging-policy — delta

## MODIFIED Requirements

### Requirement: INFO request skeleton

At INFO level the service SHALL emit a metadata-only request lifecycle skeleton, each event a
stable message prefix plus `key=value` fields: (1) request received — deployment, message count,
owned by the chat completion; (2) preparation completed — duration, `research_started`, plan
step count, outstanding question count, owned by `DeepResearchCompletion`; (3) model call
completed — agent name, duration, finish kind, requested tool names, content length, token usage
when available including the cached-input-token count, owned by a model-call logging middleware
attached to every `create_agent` graph (preparation, researcher, playground); (4) tool call
completed — tool name, tool_call_id, duration, outcome (`success`/`error`), owned by the runner
choke point that creates the DIAL stage; (5) iteration reviewed — iteration number, duration,
verdict (`continue`/`report`), next-plan step count, token usage when available including the
cached-input-token count, owned by the reviewer node; (6) report generated — duration, report
length, token usage when available including the cached-input-token count, owned by the report
node; (7) request completed — outcome (`completed`/`failed`), total duration, and on failure the
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
- **THEN** the corresponding model-call, iteration-reviewed, or report-generated event's
  token-usage field includes the cached count (counts only — no payload content)

#### Scenario: Usage absent stays graceful

- **WHEN** a model response carries no usage metadata
- **THEN** the event still fires, with its token-usage field marked unavailable
