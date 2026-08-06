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
preparation tool; (7) iteration reviewed — iteration number, duration, verdict
(`continue`/`report`), next-plan step count, token usage when available including the
cached-input-token count, owned by the research-review node; (8) report generated — draft ordinal
(1 for the first draft, incrementing per revision), duration, report length in characters and in
measured words, token usage when available including the cached-input-token count, owned by the
report node; (8a) report reviewed — draft ordinal, duration, the review model's
`verdict` (`approved`/`revise`/`failed`) and separately the app's `action`
(`deliver`/`revise`/`revise_over_ceiling`), the draft's measured word count, the
configured ceiling, the **number** of findings the review returned, and token usage when available
including the cached-input-token count, owned by the report-review node. The findings themselves are
LLM response text and SHALL NOT appear in this record or any other, at any level — they are carried to
the user in a DIAL stage instead (see **report-composition**); (8b) report delivered without
review — draft ordinal, the configured version budget, the draft's measured word count, owned by
the research runner: an exhausted budget makes no review call, so no report-reviewed event can
carry it; (9) request completed — outcome (`completed`/`failed`), total duration, and on
failure the same `error_reference` as the ERROR record. The `finish_iteration` sentinel tool SHALL
NOT produce a tool-call event above DEBUG.

Splitting the model's `verdict` from the app's `action` is deliberate: a draft the model approved
and the app revised anyway (because the measured count exceeded the ceiling) is otherwise
indistinguishable in the log from one the model asked to revise, and telling those apart is how the
review step's usefulness gets judged over time.

A report delivered with the review still unsatisfied SHALL be visible in the logs: an exhausted
version budget fires the report-delivered-without-review event, and `verdict=failed` marks a
review call that did not produce a verdict; such a call SHALL additionally log a WARNING naming
the failure kind.

A **failed revision** is recorded differently, because neither of the two report events can carry it:
the report-review node never runs for it (the graph leaves the loop instead, see
**research-execution**), and the report-generated event SHALL NOT fire for a draft that was never
produced. Its record SHALL therefore be a WARNING owned by the report node, naming the failure kind,
the ordinal of the revision that failed, and the ordinal of the draft delivered in its place. The
delivered report is the one an earlier report-generated event already recorded.
None of these SHALL log report text — counts, verdicts, actions, and durations only, per the content
allowlist.

#### Scenario: Successful research turn reads as a skeleton at INFO

- **WHEN** a turn runs preparation, hands off to research, and delivers a report on an instance
  whose version budget is above one, with all log levels at INFO
- **THEN** the log contains the request-received, preparation-completed, model-call, tool-call,
  iteration-reviewed, report-generated, report-reviewed, and request-completed events, none
  carrying message bodies or tool arguments

#### Scenario: Tool failure is visible in the skeleton

- **WHEN** an MCP tool execution returns a `ToolMessage` with `status == "error"`
- **THEN** the tool-call event fires at INFO with `outcome=error`

#### Scenario: finish_iteration stays out of the INFO skeleton

- **WHEN** research-agent calls the `finish_iteration` sentinel
- **THEN** no INFO tool-call event is emitted for it

#### Scenario: Failed turn closes the narrative

- **WHEN** a turn fails after the request-received event
- **THEN** the request-completed event fires with `outcome=failed` and the same
  `error_reference` carried by the ERROR record

#### Scenario: Cached input tokens are visible in token usage

- **WHEN** a model response reports cached input tokens (LangChain
  `usage_metadata.input_token_details["cache_read"]`)
- **THEN** the corresponding model-call, query-clarity-checked, plan-approval-checked,
  iteration-reviewed, report-generated, or report-reviewed event's token-usage field includes the
  cached count (counts only — no payload content)

#### Scenario: Usage absent stays graceful

- **WHEN** a model response carries no usage metadata
- **THEN** the event still fires, with its token-usage field marked unavailable
