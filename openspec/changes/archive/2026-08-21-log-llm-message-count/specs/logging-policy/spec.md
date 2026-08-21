## ADDED Requirements

### Requirement: LLM call logging

Every direct LLM call the service makes — a `create_agent` model call or a raw chain invocation
in a node or tool — SHALL log an INFO record carrying that call's message count and, when
available, its token usage including the cached-input-token count. A call's duration SHALL be
measured as wall-clock time around the call alone: the timer starts immediately before the model
is invoked and stops immediately after it returns or raises, so it excludes prompt assembly,
response parsing, and any other work the owning node performs before or after the call.

Where the same node also reports a broader duration to the user — a DIAL stage covering the whole
node, not just the call — that stage duration is a separate measurement and SHALL NOT be the
value logged for the call. A call that raises SHALL still be logged with its duration and message
count wherever the owning node already logs a record for that path, since both are known before
the call resolves; only token usage is unavailable.

#### Scenario: Duration excludes surrounding node work

- **WHEN** a node builds its prompt, invokes the model, and computes further state before logging
- **THEN** the logged duration reflects only the model invocation, not the prompt assembly or the
  later computation

#### Scenario: A node's own stage duration stays independent

- **WHEN** a node's LLM call feeds both a DIAL stage and an INFO log record
- **THEN** the stage's duration may cover the whole node while the log record's duration covers
  only the call

#### Scenario: A failed call is still logged

- **WHEN** report-review's LLM call, or a report revision's LLM call, raises
- **THEN** the record for that attempt still carries the call's duration and message count, with
  token usage marked unavailable

## MODIFIED Requirements

### Requirement: INFO request skeleton

At INFO level the service SHALL emit a metadata-only request lifecycle skeleton, each event a
stable message prefix plus `key=value` fields: (1) request received — deployment, message count,
owned by the chat completion; (2) preparation completed — duration, `research_started`, plan
step count, outstanding question count, owned by `DeepResearchCompletion`; (3) model call
completed — agent name, duration, message count, finish kind, requested tool names, content
length, token usage when available including the cached-input-token count, owned by a model-call
logging middleware attached to every `create_agent` graph (preparation, research-agent,
playground); (4) tool call completed — tool name, tool_call_id, duration, outcome
(`success`/`error`), owned by the runner choke point that creates the DIAL stage; (5) query
clarity checked — duration, message count, outstanding question count, token usage when available
including the cached-input-token count, owned by the `update_query` preparation tool; (6) plan
approval checked — duration, message count, approval outcome, token usage when available including
the cached-input-token count, owned by the `approve_plan` preparation tool; (7) research iteration reviewed — iteration number,
duration, message count, verdict (`continue`/`report`), next-plan step count, token usage when
available including the cached-input-token count, owned by the research-review node; (7a)
research iteration budget exhausted — iteration count and the configured cap, owned by the
research router: the last permitted iteration gets no review call, so no
research-iteration-reviewed event can carry the hand-off, and both numbers are needed to read the
event without knowing the channel's configuration; (8) report generated — draft ordinal (1 for
the first draft, incrementing per revision), duration, message count, report length in characters
and in measured words, token usage when available including the cached-input-token count, owned
by the report node; (8a) report reviewed — draft ordinal, duration, message count, the `outcome`
(`deliver`/`revise`), an `error` field naming the exception kind when the review call failed and
nothing when it succeeded, the draft's measured word count, the configured ceiling, the
**number** of violations recorded against the draft, and token usage when available including the
cached-input-token count, owned by the report-review node. That number counts one combined list —
the app's own rule violations followed by the review model's — because that list is what a
revision acts on. The violations themselves are LLM response text and SHALL NOT appear in this
record or any other, at any level — they are carried to the user in a DIAL stage instead (see
**report-composition**); (8b) report delivered without review — draft ordinal, the configured
version budget, the draft's measured word count, owned by the report router: an exhausted budget
makes no review call, so no report-reviewed event can carry it, and the router that decides the
hand-off is where its research counterpart (7a) is owned too; (9) request completed — outcome
(`completed`/`failed`), total duration, and on failure the same `error_reference` as the ERROR
record. Neither the `finish_iteration` sentinel tool nor the `update_status` tool SHALL produce a
tool-call event above DEBUG: neither performs research, and `update_status` is surfaced to the user
as the activity stage instead (see **dial-agent-with-mcp**).

Each event's message-count and duration fields follow the LLM-call-logging requirement above.

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
the ordinal of the revision that failed, the ordinal of the draft delivered in its place, and —
per the LLM-call-logging requirement — the failed call's duration and message count. The
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

#### Scenario: An exhausted iteration budget is readable without the configuration

- **WHEN** an instance permits 10 iterations and the tenth finishes, so no review call is made
- **THEN** one INFO record SHALL carry both the iteration reached and the cap of 10, and no
  research-iteration-reviewed event SHALL fire for that iteration

#### Scenario: Model-call message count reflects the actual request

- **WHEN** a `create_agent` graph's model-call-completed event fires for a call whose assembled
  request carried the system message plus 12 conversation messages
- **THEN** the event's message count is 13, and no message body appears in the record

#### Scenario: Single-turn calls report a fixed message count

- **WHEN** research-review, report-review, `update_query`, or `approve_plan` makes its
  independent LLM call — a system message plus one rendered request message, regardless of how
  much the research transcript, report draft, or conversation has grown
- **THEN** the corresponding event's message count is 2, and the record contains no message body

#### Scenario: Report-generated message count includes the transcript

- **WHEN** the report node assembles its request — a system message, the research transcript, a
  report request, and (for a revision) a revision request — and invokes the model
- **THEN** the report-generated event's message count equals the length of that assembled list
