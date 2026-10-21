## MODIFIED Requirements

### Requirement: PrepState is mutated only by tools, never by the agent

The preparation flow's working state SHALL be a typed `PrepState` (the working
query, the clarification result, the plan, the plan id, the plan-approved flag, the
research-started flag). The agent SHALL read the effect of its tool calls via the
tool results but SHALL NOT have any channel to write `PrepState` fields directly;
only tool code SHALL mutate `PrepState`. In particular, the plan-approved flag
SHALL be set only by `approve_plan`, and the research-started flag only by
`start_research`. The plan id identifies the recorded query and plan, which a
snapshot of failed research belongs to (**research-resume**). Only three tools
write it: `update_plan` sets a fresh one, `update_query` clears it together with
the plan, and `start_research` gives one to a plan recorded before plan ids
existed.

The one write outside the tools is the state a failed research turn persists when
it saves a snapshot: a copy of `PrepState` with the plan-approved and
research-started flags reset (**research-resume**). It changes nothing the agent
could have written. Any other failed turn persists the `PrepState` the request's
history held when the turn started, unchanged, so a failed turn without a snapshot
never keeps what its own tool calls wrote.

#### Scenario: The agent cannot self-approve a plan
- **WHEN** the agent emits assistant text asserting the plan is approved without `approve_plan` having set the approval flag
- **THEN** `PrepState.plan_approved` SHALL remain false and `start_research` SHALL still refuse

#### Scenario: A failed research turn persists the flags reset
- **WHEN** research fails with a quota error in the turn whose `start_research` set the research-started flag
- **THEN** the persisted `PrepState` SHALL carry the same query, plan and plan id, with the plan-approved and research-started flags false

#### Scenario: A failed preparation turn keeps the state it started from
- **WHEN** `update_plan` records a new plan in a turn whose next model call then fails with a quota error
- **THEN** the persisted `PrepState` SHALL equal the one the turn started from, without the new plan

### Requirement: update_query sets the working query and runs an independent clarity check

The `update_query(query)` tool SHALL, atomically: set the working query; reset any
recorded plan together with its plan id, and clear the plan-approved flag; and run an independent LLM check
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

The restated query SHALL keep the user's formatting requests, such as rounding figures, a
number of decimals or a unit, because the report writer and report review see the user's
request only as this query restates it (see **faithful-relay**).

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
- **THEN** the recorded plan and its plan id SHALL be cleared and the plan-approved flag SHALL be reset to false


#### Scenario: A rounding request survives the restatement

- **WHEN** the user asks for GDP growth by region "rounded to one decimal"
- **THEN** the query the agent records with `update_query` SHALL keep the request to round to
  one decimal

### Requirement: update_plan records the plan; the agent presents the query and plan verbatim after each edit

The `update_plan(steps)` tool SHALL record the agent-authored research plan into
`PrepState` with a fresh plan id, and reset the plan-approved flag. The plan id is
renewed on every call, even when the steps equal the recorded ones, so a snapshot
saved for an earlier plan never matches a plan recorded after it
(**research-resume**). The plan SHALL be stored as an
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
- **THEN** the plan SHALL be recorded with a fresh plan id and the plan-approved flag SHALL be false

#### Scenario: Recording the same steps again renews the plan id
- **WHEN** the agent calls `update_plan` with exactly the steps already recorded
- **THEN** the plan id SHALL differ from the one it replaced

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

After a failed turn, the conversation carries the failed-turn note
(**research-resume**). In that conversation, a user's request to continue or retry
the research SHALL count as approval of the recorded plan, provided the user
approved that same plan before the failure. The recorded-plan check applies as
always. The note by itself approves nothing.

#### Scenario: Approval granted when the user approves the recorded plan
- **WHEN** the recorded plan matches the plan discussed and the user's latest message approves it
- **THEN** `approve_plan` SHALL set the plan-approved flag to true

#### Scenario: Stale recorded plan is refused, not approved
- **WHEN** the user approved a revised plan in the conversation but `PrepState.plan` still holds an earlier version
- **THEN** `approve_plan` SHALL NOT approve, SHALL leave the plan-approved flag false, and SHALL indicate the latest plan must be recorded first; the recorded plan content SHALL be left unchanged

#### Scenario: Revision request is not approval
- **WHEN** the user's latest message requests changes to the plan
- **THEN** `approve_plan` SHALL NOT approve, and SHALL indicate the requested changes so the agent can revise and re-record the plan

#### Scenario: A request to continue after a failed run approves the plan
- **WHEN** the user approved the recorded plan, the research run it started failed, and the user's latest message is "continue"
- **THEN** `approve_plan` SHALL set the plan-approved flag to true, without the plan being presented again

#### Scenario: The failed-turn note alone approves nothing
- **WHEN** the conversation carries the failed-turn note and the user's latest message asks what happened
- **THEN** `approve_plan` SHALL NOT approve

### Requirement: Stateless turns persist PrepState and transcript in DIAL custom state

The app SHALL process each turn statelessly, with no checkpointer and no
`interrupt()`. At the start of a turn it SHALL reconstruct the LangChain message
history from the DIAL transcript and load `PrepState` from the latest assistant
message's `custom_content.state` — the `preparation` field of the unified
`DialState` (a fresh `PrepState` when none is present). At the end of a turn it
SHALL persist both the message slice and the resulting `PrepState` into
`custom_content.state` as that unified `DialState` (under `messages` and
`preparation` respectively) via `choice.set_state`. A failed turn persists as well,
with a failure flag (**research-resume**). A turn whose research run saved a
snapshot persists its preparation messages, its `PrepState` with the plan-approved
and research-started flags reset, and the snapshot. Any other failed turn persists
an empty `messages` and the `PrepState` the request's history held when the turn
started. A failure while the application properties are fetched or validated
persists nothing, and a turn never fails once its report is written. The app SHALL
NOT keep server-side session state across requests.

#### Scenario: Turn persists transcript and PrepState
- **WHEN** a turn completes
- **THEN** the assistant message's `custom_content.state` SHALL contain the turn's `messages` slice and the current `preparation` state, and the app SHALL hold no other cross-request state for the session

#### Scenario: Next turn restores PrepState from the transcript
- **WHEN** a follow-up request carries a prior assistant message whose `custom_content.state` `preparation` field records a resolved clarification and an unapproved plan
- **THEN** the preparation agent for the new turn SHALL run with that `PrepState` restored, so the gates reflect the prior turn's progress without re-deriving it from the messages

#### Scenario: The turn after a failed research run restores the plan without approval
- **WHEN** a follow-up request's latest stateful assistant message was written by a failed research turn that saved a snapshot
- **THEN** the preparation agent SHALL run with that turn's query, plan and plan id restored, and with the plan-approved and research-started flags false

### Requirement: Refuse input after research has started

When the loaded `PrepState` indicates research has already started, the app SHALL
refuse further input for that session and instruct the user to start a new
conversation, rather than running the preparation agent again. A persisted
`PrepState` says so only after research delivered its report: a failed research
turn persists the flag reset, so its conversation stays open for a resume
(**research-resume**).

#### Scenario: Message after launch is refused
- **WHEN** a request's loaded `PrepState` has the research-started flag set
- **THEN** the app SHALL return a message instructing the user to start a new conversation, and SHALL NOT run the preparation agent

#### Scenario: A conversation whose research failed is not refused
- **WHEN** a request follows a turn whose research run failed
- **THEN** the app SHALL run the preparation agent for it

### Requirement: Every preparation LLM call's inputs and outputs are specified

The preparation flow makes exactly three kinds of LLM call, and each one's inputs SHALL be
exactly what is listed here — nothing else reaches a model, and adding an input SHALL require
updating this requirement.

**1. The preparation agent's model call** (one per agent step)

- System prompt: the preparation instructions, filled with the instance's `agent_name`, today's
  date, and the turn's data-sources string: the configured servers' descriptions, the document
  statistics block, the datasets section and the rendered glossary, each when its condition holds
  (see **data-sources-discovery**). When the list of datasets failed, it also
  carries the instruction to plan around the failure (see **data-sources-discovery**). It carries
  neither the instruction to request missing definitions nor the instruction about the dataset
  tools, because this agent has no MCP tools.
- Messages: the **full** conversation history reconstructed from the DIAL request — every user
  message as text, and for every prior assistant turn the persisted message slice (its
  `AIMessage`s and `ToolMessage`s) with image blocks rehydrated to base64, and directly after
  every prior assistant turn whose state carries the failure flag one fixed failed-turn note as a
  system message (**research-resume**) — followed by the current turn's accumulated messages. A
  snapshot's research transcript is never part of it. There SHALL be no truncation, windowing, or
  summarization; a turn that outgrows the model's context SHALL fail rather than silently drop
  history.
- Tools bound: the four preparation control tools.
- Output: assistant text and/or tool calls. The text is the user-visible answer, except on a
  turn where research starts (see the silent hand-off rule below).

**2. The query clarity check** (one per `update_query` call)

- System prompt: the intake-check instructions, filled with today's date and the turn's
  data-sources string, the same one the preparation agent receives, with no instruction about a
  failed list of datasets.
- Messages: one human message carrying the rendered conversation so far and the candidate query.
  The rendering SHALL include only natural-language user and assistant text, and the
  failed-turn note as a `System note:` line at its position in the conversation; tool calls,
  tool results, and any other system message SHALL be dropped. No image content SHALL be
  included.
- Output: a structured `QueryReviewResponse` — a per-dimension assessment, then the clarifying
  questions (empty when the query is ready).

**3. The plan approval check** (one per `approve_plan` call)

- System prompt: the plan-approval instructions, filled with today's date only — no server
  descriptions, no document statistics block, no datasets section and no glossary.
- Messages: one human message carrying the recorded plan as a numbered list and the rendered
  conversation, filtered exactly as in the clarity check. No image content.
- Output: a structured `PlanReviewResponse` — the assessment, whether the recorded plan matches
  the one last discussed, whether the user approved it, and a user-facing failure reason.

#### Scenario: The agent sees the whole conversation, the checks see only its prose

- **WHEN** a preparation turn runs on a conversation whose earlier turns contain tool calls, tool
  results, and page images
- **THEN** the preparation agent's model call SHALL receive all of it including the images, while
  the clarity check and the approval check SHALL receive only the user and assistant text

#### Scenario: All three calls see the failed-turn note in place

- **WHEN** a preparation turn runs on a conversation that holds a failed turn followed by the
  user's request to continue
- **THEN** the preparation agent's model call SHALL receive the failed-turn note as a system
  message between the failed turn's messages and the user's request, and the clarity check and the
  approval check SHALL each receive it as a `System note:` line at the same position in their
  rendered conversation, and none of the three SHALL receive the failed run's research transcript

#### Scenario: History is never silently shortened

- **WHEN** the reconstructed history is long
- **THEN** the preparation agent SHALL receive every reconstructed message, with no truncation or
  summarization applied

#### Scenario: The agent and the clarity check see the glossary, the approval check does not

- **WHEN** a preparation turn runs on a channel whose glossary listed terms
- **THEN** the preparation agent's system prompt and the clarity check's system prompt SHALL carry
  the same data-sources string ending in the rendered glossary, and the approval check's system
  prompt SHALL carry no part of the data-sources string

#### Scenario: The agent and the clarity check see the datasets section

- **WHEN** a preparation turn runs on a channel whose dataset server names a dataset-structure tool
- **THEN** the preparation agent's system prompt and the clarity check's system prompt SHALL carry
  the same data-sources string, including the datasets section with its structures block, and the
  approval check's system prompt SHALL carry no part of it
