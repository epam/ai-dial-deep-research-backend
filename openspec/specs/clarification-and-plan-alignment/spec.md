# clarification-and-plan-alignment Specification

## Purpose
TBD - created by archiving change clarification-and-plan-alignment. Update Purpose after archive.
## Requirements
### Requirement: Preparation agent gates research behind clarification and plan approval

On each chat completion request the app SHALL drive a single-context LangChain
tool-calling agent (the **preparation agent**) that holds one conversation and
advances a clarify → plan → approve → launch flow by calling tools. The app SHALL
NOT run the research/reflection/report path in this change. The preparation agent
SHALL have exactly these control tools and no MCP/data tools: `update_query`,
`update_plan`, `approve_plan`, `start_research`.

The flow's ordering SHALL be enforced by tool preconditions (hard gates), not by
the agent's discretion: research SHALL NOT be startable until the working query's
clarifications are resolved and the plan is user-approved.

#### Scenario: Request handled by the preparation agent, not the research agent
- **WHEN** a chat completion request is processed
- **THEN** the app SHALL run the preparation agent for that turn, and SHALL NOT construct an MCP client, fetch tools, or run the tool-calling research agent

#### Scenario: A clear, approved request can launch; an unprepared one cannot
- **WHEN** the agent calls `start_research` while the query is unclear or the plan is unapproved
- **THEN** the call SHALL fail with an error naming the missing precondition, and research SHALL NOT start
- **AND WHEN** the agent calls `start_research` after clarifications are resolved and the plan is approved
- **THEN** the gate SHALL pass

### Requirement: PrepState is mutated only by tools, never by the agent

The preparation flow's working state SHALL be a typed `PrepState` (the working
query, the clarification result, the plan, the plan-approved flag, the
research-started flag). The agent SHALL read the effect of its tool calls via the
tool results but SHALL NOT have any channel to write `PrepState` fields directly;
only tool code SHALL mutate `PrepState`. In particular, the plan-approved flag
SHALL be set only by `approve_plan`, and the research-started flag only by
`start_research`.

#### Scenario: The agent cannot self-approve a plan
- **WHEN** the agent emits assistant text asserting the plan is approved without `approve_plan` having set the approval flag
- **THEN** `PrepState.plan_approved` SHALL remain false and `start_research` SHALL still refuse

### Requirement: update_query sets the working query and runs an independent clarity check

The `update_query(query)` tool SHALL, atomically: set the working query; reset any
recorded plan and clear the plan-approved flag; and run an independent LLM check
that judges whether the request is specific enough to research, recording the
resulting clarifying questions (an empty list meaning the request is clear). The
clarity check SHALL consider the conversation history together with the candidate
query, and SHALL be strict: every material dimension — intent, region, time period,
and focus — SHALL be explicitly settled by the user before the request passes, and
the check SHALL NOT assume or invent a default for a missing dimension. Vague time
references (e.g. "latest", "recent", "current") SHALL be treated as unsettled and
clarified by asking the user for a concrete period; the check SHALL NOT resolve them
itself. Time references anchored to a named event or era (e.g. "Trump's first
presidency") SHALL instead be resolved by proposing concrete dates from the
assistant's own knowledge for the user to confirm, counting as settled only once the
user confirms them. A material dimension that was previously asked but
not addressed by the user SHALL be asked again rather than dropped. The check SHALL
NOT assess data-source availability, SHALL NOT ask obvious or low-value questions,
and SHALL NOT inject assumed defaults into the query.

When clarifying questions are produced, the agent SHALL present them to the user in
natural language and end the turn awaiting an answer. When the user answers, the
agent SHALL fold the answer into a refined query and call `update_query` again,
supporting multiple rounds until the check returns no questions. There SHALL be no
sentinel answer string.

#### Scenario: Under-specified query yields clarifying questions
- **WHEN** `update_query` runs on a query missing a material dimension (e.g. region or period)
- **THEN** it SHALL record clarifying questions, and the agent SHALL present them and end the turn without recording a plan

#### Scenario: Vague time reference is clarified
- **WHEN** the request uses a vague time reference (e.g. "latest" or "recent") with no concrete period
- **THEN** the clarity check SHALL record a question asking the user to pin down a concrete period, and SHALL NOT resolve it itself

#### Scenario: Event-anchored period is resolved for confirmation
- **WHEN** the request anchors the time period to a named event or era (e.g. "Trump's first presidency") rather than concrete dates
- **THEN** the clarity check SHALL record a question proposing the concrete dates from the assistant's own knowledge and asking the user to confirm them, and SHALL NOT treat the period as settled until the user confirms

#### Scenario: A previously unanswered dimension is re-asked
- **WHEN** a material dimension was asked in a prior round and the user's reply did not address it
- **THEN** the clarity check SHALL ask about that dimension again rather than treating it as settled

#### Scenario: A clear query yields no questions
- **WHEN** `update_query` runs on a query that is specific enough to research
- **THEN** it SHALL record an empty question list, marking the clarification resolved, and the agent MAY proceed to draft a plan

#### Scenario: Changing the query invalidates the plan
- **WHEN** `update_query` is called after a plan was recorded (and possibly approved)
- **THEN** the recorded plan SHALL be cleared and the plan-approved flag SHALL be reset to false

### Requirement: update_plan records the plan; the agent presents the query and plan verbatim after each edit

The `update_plan(steps)` tool SHALL record the agent-authored research plan into
`PrepState` and reset the plan-approved flag. The plan SHALL be stored as an
ordered list of step strings. `update_plan`'s returned message SHALL include both
the working query and the recorded plan, presenting the steps as a numbered list so
the user can refer to a step by its number. It SHALL fail with an informative error
when the clarifications are not yet resolved (no clarity check has run, or it
returned outstanding questions), so a plan cannot be recorded for an unclear query.

After each `update_plan` call — the initial draft and every subsequent revision —
the agent SHALL present BOTH the working query and the recorded plan to the user
verbatim, unchanged in wording, order, and numbering, so what the user sees always
matches the recorded query and plan, and SHALL then ask whether the user approves or
wants changes. (Rendering the recorded query and plan programmatically into the
assistant message, rather than relying on the agent to echo them, is a deferred
follow-up.)

#### Scenario: Recorded query and plan are presented to the user verbatim
- **WHEN** the agent presents a recorded plan to the user for review
- **THEN** it SHALL present both the working query and the recorded `PrepState.plan` steps verbatim (same wording, order, and numbering)

#### Scenario: Every plan revision re-presents the query and plan
- **WHEN** the agent revises the plan and calls `update_plan` again
- **THEN** it SHALL present the working query and the updated plan to the user verbatim once more before seeking approval

#### Scenario: Plan recorded once clarifications are resolved
- **WHEN** the agent calls `update_plan` after the clarity check returned no questions
- **THEN** the plan SHALL be recorded and the plan-approved flag SHALL be false

#### Scenario: Plan rejected while clarifications are outstanding
- **WHEN** the agent calls `update_plan` while clarifying questions are still outstanding (or no clarity check has run)
- **THEN** the call SHALL fail with an error indicating clarifications must be resolved first, and no plan SHALL be recorded

### Requirement: approve_plan independently verifies approval and plan integrity

The `approve_plan()` tool SHALL use an independent LLM that reads the full
conversation and the recorded plan, and SHALL decide approval from two checks: (1)
whether the recorded plan still matches the plan that was discussed and approved in
the conversation, and (2) whether the user approved it. Approval SHALL be granted
only when both hold; on approval the tool SHALL set the plan-approved flag. The
tool SHALL NOT modify the recorded plan content under any circumstances.

When the recorded plan does not match the plan the user approved (e.g. the agent
revised the plan in chat but did not record the new version), `approve_plan` SHALL
refuse and indicate that the latest plan must be recorded via `update_plan` first.
There SHALL be no sentinel approval string. The tool SHALL fail when there is no
recorded plan or the clarifications are unresolved.

#### Scenario: Approval granted when the user approves the recorded plan
- **WHEN** the recorded plan matches the plan discussed and the user's latest message approves it
- **THEN** `approve_plan` SHALL set the plan-approved flag to true

#### Scenario: Stale recorded plan is refused, not approved
- **WHEN** the user approved a revised plan in the conversation but `PrepState.plan` still holds an earlier version
- **THEN** `approve_plan` SHALL NOT approve, SHALL leave the plan-approved flag false, and SHALL indicate the latest plan must be recorded first; the recorded plan content SHALL be left unchanged

#### Scenario: Revision request is not approval
- **WHEN** the user's latest message requests changes to the plan
- **THEN** `approve_plan` SHALL NOT approve, and SHALL indicate the requested changes so the agent can revise and re-record the plan

### Requirement: start_research hard-gates and stops at readiness in this change

The `start_research()` tool SHALL fail with an error naming the missing
precondition unless the working query is set, the clarifications are resolved, and
the plan is approved. Because research execution is deferred in this change, on a
passing gate the tool SHALL mark research as started and return a ready-to-research
summary (the finalized query and the approved plan); it SHALL NOT run research,
reflection, or report generation.

#### Scenario: Gate failure names the missing precondition
- **WHEN** `start_research` is called with the plan not yet approved
- **THEN** it SHALL fail with an error that names plan approval as the missing precondition, and SHALL NOT mark research as started

#### Scenario: Gate pass returns the ready-to-research summary
- **WHEN** `start_research` is called with the query clear and the plan approved
- **THEN** it SHALL mark research as started and return a summary containing the finalized query and the approved plan, and SHALL NOT produce a research report

### Requirement: Stateless turns persist PrepState and transcript in DIAL custom state

The app SHALL process each turn statelessly, with no checkpointer and no
`interrupt()`. At the start of a turn it SHALL reconstruct the LangChain message
history from the DIAL transcript and load `PrepState` from the latest assistant
message's `custom_content.state` — the `preparation` field of the unified
`DialState` (a fresh `PrepState` when none is present). At the end of a turn it
SHALL persist both the message slice and the resulting `PrepState` into
`custom_content.state` as that unified `DialState` (under `messages` and
`preparation` respectively) via `choice.set_state`. The app SHALL NOT keep
server-side session state across requests.

#### Scenario: Turn persists transcript and PrepState
- **WHEN** a turn completes
- **THEN** the assistant message's `custom_content.state` SHALL contain the turn's `messages` slice and the current `preparation` state, and the app SHALL hold no other cross-request state for the session

#### Scenario: Next turn restores PrepState from the transcript
- **WHEN** a follow-up request carries a prior assistant message whose `custom_content.state` `preparation` field records a resolved clarification and an unapproved plan
- **THEN** the preparation agent for the new turn SHALL run with that `PrepState` restored, so the gates reflect the prior turn's progress without re-deriving it from the messages

### Requirement: Rewind continues from the surviving assistant message's state

Because `PrepState` and the transcript ride on the assistant message, the app SHALL
require no rewind-detection logic. When the user edits or regenerates an earlier
message and DIAL truncates the later turns, the app SHALL naturally continue from
the `PrepState` recorded on the last surviving assistant message. Editing the first
user message (no prior assistant message) SHALL start from a fresh `PrepState`.

#### Scenario: Rewound conversation continues from the surviving state
- **WHEN** a request's transcript has been truncated by a rewind so the last assistant message is an earlier one
- **THEN** the turn SHALL load the `PrepState` from that surviving assistant message and continue, without any special rewind handling

#### Scenario: Edited first message starts fresh
- **WHEN** the first user message is edited so the request carries no prior assistant message
- **THEN** the turn SHALL start from a fresh `PrepState`

### Requirement: Refuse input after research has started

When the loaded `PrepState` indicates research has already started, the app SHALL
refuse further input for that session and instruct the user to start a new
conversation, rather than running the preparation agent again.

#### Scenario: Message after launch is refused
- **WHEN** a request's loaded `PrepState` has the research-started flag set
- **THEN** the app SHALL return a message instructing the user to start a new conversation, and SHALL NOT run the preparation agent

### Requirement: Cross-context conversation is allowed during preparation

The preparation agent SHALL be able to answer the user's general, conversational
side questions (e.g. "what is CPI?") from its own knowledge during the preparation
flow, and SHALL steer the conversation back toward clarification and planning. The
agent's user-facing output SHALL be natural-language text (the questions, the plan,
or an answer); the user SHALL NOT be required to use any sentinel phrasing.

#### Scenario: Side question answered without derailing the flow
- **WHEN** the user asks a general question mid-preparation instead of answering the current question
- **THEN** the agent MAY answer it from its own knowledge and SHALL then continue the clarification or planning flow
