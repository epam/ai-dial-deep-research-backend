# clarification-and-plan-alignment Specification

## Purpose
TBD - created by archiving change clarification-and-plan-alignment. Update Purpose after archive.
## Requirements
### Requirement: Preparation agent gates research behind clarification and plan approval

On each chat completion request the app SHALL drive a single-context LangChain
tool-calling agent (the **preparation agent**) that holds one conversation and
advances a clarify → plan → approve → launch flow by calling tools. The preparation
agent SHALL have exactly these control tools and no MCP/data tools: `update_query`,
`update_plan`, `approve_plan`, `start_research`. Research itself runs only after
approval, in the same turn, as a separate graph (see the **research-execution**
capability); the preparation agent SHALL NOT research or write a report.

The flow's ordering SHALL be enforced by tool preconditions (hard gates), not by
the agent's discretion: research SHALL NOT be startable until the working query's
clarifications are resolved and the plan is user-approved.

#### Scenario: Every turn starts with the preparation agent
- **WHEN** a chat completion request is processed and the loaded `CrossTurnPrepState` does not have the research-started flag set
- **THEN** the app SHALL run the preparation agent for that turn

#### Scenario: No MCP client or research graph unless the agent calls start_research
- **WHEN** the preparation agent's run for a turn finishes without having called `start_research`
- **THEN** the app SHALL NOT construct an MCP client, fetch tools, or run the research graph for that turn

#### Scenario: A clear, approved request can launch; an unprepared one cannot
- **WHEN** the agent calls `start_research` while the query is unclear or the plan is unapproved
- **THEN** the call SHALL fail with an error naming the missing precondition, and research SHALL NOT start
- **AND WHEN** the agent calls `start_research` after clarifications are resolved and the plan is approved
- **THEN** the gate SHALL pass

### Requirement: CrossTurnPrepState is mutated only by tools, never by the agent

The preparation flow's working state SHALL be a typed `CrossTurnPrepState` (the working
query, the clarification result, the plan, the plan id, the plan-approved flag, the
research-started flag). The agent SHALL read the effect of its tool calls via the
tool results but SHALL NOT have any channel to write `CrossTurnPrepState` fields directly;
only tool code SHALL mutate `CrossTurnPrepState`. In particular, the plan-approved flag
SHALL be set only by `approve_plan`, and the research-started flag only by
`start_research`. The plan id identifies the recorded query and plan, which a
snapshot of failed research belongs to (**research-resume**). Only three tools
write it: `update_plan` sets a fresh one, `update_query` clears it together with
the plan, and `start_research` gives one to a plan recorded before plan ids
existed.

The one write outside the tools is the state a failed research turn persists when
it saves a snapshot: a copy of `CrossTurnPrepState` with the plan-approved and
research-started flags reset (**research-resume**). It changes nothing the agent
could have written. Any other failed turn persists the `CrossTurnPrepState` the request's
history held when the turn started, unchanged, so a failed turn without a snapshot
never keeps what its own tool calls wrote.

#### Scenario: The agent cannot self-approve a plan
- **WHEN** the agent emits assistant text asserting the plan is approved without `approve_plan` having set the approval flag
- **THEN** `CrossTurnPrepState.plan_approved` SHALL remain false and `start_research` SHALL still refuse

#### Scenario: A failed research turn persists the flags reset
- **WHEN** research fails with a quota error in the turn whose `start_research` set the research-started flag
- **THEN** the persisted `CrossTurnPrepState` SHALL carry the same query, plan and plan id, with the plan-approved and research-started flags false

#### Scenario: A failed preparation turn keeps the state it started from
- **WHEN** `update_plan` records a new plan in a turn whose next model call then fails with a quota error
- **THEN** the persisted `CrossTurnPrepState` SHALL equal the one the turn started from, without the new plan

### Requirement: update_query sets the working query and runs an independent clarity check

The `update_query(query)` tool SHALL, atomically: set the working query; reset any
recorded plan together with its plan id, and clear the plan-approved flag; and run an independent LLM check
that judges whether the request is specific enough to research, recording the
resulting clarifying questions (an empty list meaning the request is clear). The
clarity check SHALL consider the conversation history together with the candidate
query. Every material dimension — intent, region, time period, and focus — SHALL be settled before
the request passes, and the check SHALL NOT inject assumed defaults into the query. A material
dimension that was previously asked but not addressed by the user SHALL be asked again rather than
dropped. The check SHALL NOT assess data-source availability, and SHALL NOT ask obvious or
low-value questions.

The check SHALL resolve the time period itself, without a question, in each of these cases:

- an open or one-sided bound, such as "from 2020" or "until now";
- a span counted back from today, such as "the last 10 years" (see "A span of years counted back
  from today ends with the current year");
- an event or an era that it recognizes (see "A period named by an event or an era is written with
  its years");
- "the latest" or "the most recent" publication, which selects a document and needs no period;
- the latest, most recent or current value of an indicator, which is its latest actual value and
  needs no period;
- a time choice that the user handed over or declined.

The check SHALL ask for the time period in each of these cases:

- The query names no time period and no event or era. Words such as "outlook", "overview",
  "trends" or "current state" do not name a time period.
- A bare "latest", "recent" or "lately" has nothing else to anchor it.
- The query names an event or an era that the check does not recognize.

A question about how a value was revised, such as how a forecast changed over time, needs a date
range for the revisions: the dates between which the forecasts were made. When the query gives no
such range, the clarity check SHALL ask for it. This question comes in addition to the period that
the value is about.

When clarifying questions are produced, the agent SHALL present them to the user in
natural language and end the turn awaiting an answer. When the user answers, the
agent SHALL fold the answer into a refined query and call `update_query` again,
supporting multiple rounds until the check returns no questions. There SHALL be no
sentinel answer string.

The restated query SHALL keep the user's formatting requests, such as a unit, because the report
writer and report review see the user's request only as this query restates it (see
**faithful-relay**). The agent SHALL add no formatting request of its own. The exception is a
request to calculate, round or convert a figure: the query follows "The plan never asks to convert
or round a figure" and "The plan never asks for a calculation". The `update_query` tool's
description SHALL refer to the prompt section "Unsupported operations" for such a request, because
the agent writes the query when it makes that call.

#### Scenario: Under-specified query yields clarifying questions
- **WHEN** `update_query` runs on a query missing a material dimension (e.g. region or period)
- **THEN** it SHALL record clarifying questions, and the agent SHALL present them and end the turn without recording a plan

#### Scenario: A query with no period gets a question
- **WHEN** the user asks for "the labour market outlook for Germany" and names no time period and no
  event or era
- **THEN** the clarity check SHALL record a question that asks for the time period, and SHALL NOT read "outlook" as a time period

#### Scenario: Vague time reference is clarified
- **WHEN** the request uses a bare "latest" or "recent" with nothing else to anchor it
- **THEN** the clarity check SHALL record a question asking the user for the time period, and SHALL NOT resolve it itself

#### Scenario: A recognized event or era settles the period
- **WHEN** the request anchors the time period to an event or an era that the check recognizes, such
  as "since the 2008 financial crisis"
- **THEN** the clarity check SHALL treat the time period as settled and SHALL record no question about it

#### Scenario: The current value of an indicator needs no period
- **WHEN** the request asks for the current unemployment rate of Canada, with no period given
- **THEN** the clarity check SHALL record no question about the time period

#### Scenario: A previously unanswered dimension is re-asked
- **WHEN** a material dimension was asked in a prior round and the user's reply did not address it
- **THEN** the clarity check SHALL ask about that dimension again rather than treating it as settled

#### Scenario: A clear query yields no questions
- **WHEN** `update_query` runs on a query that is specific enough to research
- **THEN** it SHALL record an empty question list, marking the clarification resolved, and the agent MAY proceed to draft a plan

#### Scenario: Changing the query invalidates the plan
- **WHEN** `update_query` is called after a plan was recorded (and possibly approved)
- **THEN** the recorded plan and its plan id SHALL be cleared and the plan-approved flag SHALL be reset to false

#### Scenario: A unit request survives the restatement

- **WHEN** the user asks for the exports of Mexico "in euros"
- **THEN** the query the agent records with `update_query` SHALL keep "in euros", and SHALL add no
  formatting request that the user did not make, such as a number of decimals

#### Scenario: A question about revisions needs the dates of the revisions

- **WHEN** the user asks how the IMF forecast of 2026 GDP growth for Germany changed, and gives no
  dates between which the forecasts were made
- **THEN** the clarity check SHALL record a question asking for that date range

### Requirement: A span of years counted back from today ends with the current year

A span of N years counted back from today ("the last N years", "the past N years") SHALL end with
the current year, which counts as one of the N although it has not ended, so the span starts N-1
years earlier. The current year is the one the user most wants to see, and the other reading that
keeps it, the last N completed years plus the current one, turns "the last 2 years" into three
calendar years; a span given in months or days runs to today and needs no such rule. The agent
SHALL write the resolved years into the query it records, so research never reads the relative
span itself. When the user declines to choose the time period, the agent SHALL apply two defaults:
the last 10 years for past values, counted the same way, and the next 3 years after the current
year for forecasts. The agent SHALL open its reply by naming the default it applied, so the user
can change it. The preparation agent's prompt and the query check's prompt SHALL both state the
rule with an example that uses the current year, and SHALL both state the two defaults with their
years computed from today's date.

#### Scenario: The last two years include the current year

- **WHEN** in October 2026 the user asks for GDP growth in Germany over the last 2 years
- **THEN** the query the agent records and the plan SHALL give the period as 2025–2026, and
  SHALL NOT give it as 2024–2025

#### Scenario: A span stated in the first turn is recorded with its years

- **WHEN** in 2026 the user asks how GDP growth developed over the last 10 years, with the
  subject and the region given
- **THEN** the query the agent records SHALL state the period as 2017–2026, and SHALL NOT keep
  it as the words "the last 10 years" alone

#### Scenario: The default span on a declined time choice ends with the current year

- **WHEN** in 2026 the user declines to choose the time period
- **THEN** the agent SHALL apply 2017–2026 as the last 10 years, and SHALL open its reply by
  telling the user that range

#### Scenario: The default span of forecasts is the next three years

- **WHEN** in 2026 the user asks for the IMF forecasts of GDP growth for Germany and declines to
  choose the time period
- **THEN** the agent SHALL apply 2027–2029 to the forecasts, and the query check SHALL treat the
  time period as settled

#### Scenario: The query check accepts a span resolved this way

- **WHEN** in 2026 the user asks how inflation in Germany changed over the last three years, and
  the agent restates the period as 2024–2026
- **THEN** the query check SHALL record no question about the time period

#### Scenario: A span given in months runs to today

- **WHEN** in October 2026 the user asks for developments over the last 6 months
- **THEN** the period SHALL run from April 2026 to today, and the rule on years SHALL NOT
  stretch it to the whole of 2026

### Requirement: update_plan records the plan; the agent presents the query and plan verbatim after each edit

The `update_plan(steps)` tool SHALL record the agent-authored research plan into
`CrossTurnPrepState` with a fresh plan id, and reset the plan-approved flag. The plan id is
renewed on every call, even when the steps equal the recorded ones, so a snapshot
saved for an earlier plan never matches a plan recorded after it
(**research-resume**). The plan SHALL be stored as an
ordered list of step strings. `update_plan`'s returned message SHALL include the
working query and the recorded plan as one labelled block: the query after the label
"Research query:", then the label "Plan:" and the steps as a numbered list. The labels
let the user tell the query from the plan, and the numbers let the user refer to a step.
It SHALL fail with an informative error
when the clarifications are not yet resolved (no clarity check has run, or it
returned outstanding questions), so a plan cannot be recorded for an unclear query.

After each `update_plan` call — the initial draft and every subsequent revision —
the agent SHALL present the labelled block, with BOTH the working query and the recorded
plan, to the user verbatim, unchanged in labels, wording, order, and numbering, so what the user
sees always
matches the recorded query and plan, and SHALL then ask whether the user approves or
wants changes. (Rendering the recorded query and plan programmatically into the
assistant message, rather than relying on the agent to echo them, is a deferred
follow-up.)

#### Scenario: Recorded query and plan are presented to the user verbatim
- **WHEN** the agent presents a recorded plan to the user for review
- **THEN** it SHALL present both the working query and the recorded `CrossTurnPrepState.plan` steps verbatim (same labels, wording, order, and numbering)

#### Scenario: The query and the plan are labelled
- **WHEN** `update_plan` records a plan
- **THEN** its returned message SHALL give the query after the label "Research query:" and the numbered steps after the label "Plan:"

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

### Requirement: The plan never asks for a calculation

The plan the preparation agent drafts SHALL NOT ask to calculate, compute, derive, estimate or
model a figure, such as a growth rate from two levels, a difference, a share, a sum, an average, an
elasticity or a regression estimate, because neither research nor the report computes anything (see
**report-composition**, "Reports contain no calculations"). When the query asks for such a figure,
the plan item SHALL ask research to look for a source that states the figure. Only where no source
states it SHALL the plan item ask research to retrieve the figures it is computed from:

- When the query names these figures, the plan SHALL name them. For a growth rate of X, or for an
  elasticity of X to Y, the plan names X and Y.
- When the query names only a measure, such as an index, the plan SHALL ask for a source that
  states how to compute it, and for the figures that this source names.

The preparation agent SHALL plan such an item straight away, without asking the user first, and
its prompt SHALL say so, with an example of such a plan item.

A comparison is not a calculation. When the query asks to compare values, the plan SHALL ask
research to find each value, and SHALL NOT ask for their difference.

The query keeps a request for a computed figure, such as "the average inflation over 2010–2020": the
preparation agent restates what the user asked for, and the plan alone carries how research handles
it. An explicit instruction to calculate the figure, such as "compute it from the annual values",
stays out of the query and the plan, the query keeps the figure, and the agent gives the note (see
"The agent tells the user which requested operations Deep Research does not perform"). The query
check SHALL treat a figure that needs a calculation, and a figure in a unit or a currency that the
user names, as a clear subject. It SHALL NOT ask how to calculate or convert a figure, such as a
formula, a regression specification or an exchange rate, and SHALL NOT ask which figure or unit to
report instead. Its prompt SHALL say only which questions not to ask, and SHALL NOT describe what
Deep Research or research does with such a figure, because the check decides only which
clarifications to ask.

The rule SHALL hold when the user insists on a calculation or rejects a plan without one. The
preparation agent SHALL then give the note again (see "The agent tells the user which requested
operations Deep Research does not perform"), and keep the plan item that looks for a stated
figure. No plan item SHALL calculate or promise a
calculated result.

#### Scenario: The user asks for an elasticity

- **WHEN** the clarified query asks to quantify the elasticity of import growth to GDP growth over
  a period
- **THEN** the recorded plan SHALL ask to look for a stated elasticity and, if no source states
  one, to retrieve the import growth and GDP growth series for that period, and no plan item SHALL
  ask to calculate, estimate or model the elasticity, by regression or otherwise

#### Scenario: The query check does not ask for an estimation method

- **WHEN** the query asks to quantify the elasticity of import growth to GDP growth, and the
  subject, the region and the period are settled
- **THEN** the query check SHALL NOT ask how the elasticity should be estimated, by which formula,
  or with which regression specification, and SHALL NOT ask what to report instead of a calculated
  elasticity

#### Scenario: The query check does not ask about a conversion

- **WHEN** the user asks for "Mexico's exports in 2023, converted to euros", and the subject, the
  region and the period are settled
- **THEN** the query check SHALL NOT ask which exchange rate to use, and SHALL NOT ask whether to
  report the figure in another currency instead

#### Scenario: The user asks for a growth rate

- **WHEN** the query asks for the growth of a value between two years
- **THEN** the plan SHALL ask for a source that states that growth and, if none does, for the
  value in both years, and SHALL NOT ask to compute the growth from the two values

#### Scenario: The user asks for an index without its inputs

- **WHEN** the query asks for a trade-openness index for Germany and names none of its inputs
- **THEN** the plan SHALL ask for a source that states the index, and otherwise for a source that
  states how to compute it and for the figures that this source names

#### Scenario: The user asks to compare two values

- **WHEN** the query asks to compare the IMF forecast of 2026 GDP growth for Germany with the IMF
  forecast for France
- **THEN** the plan SHALL ask research to find each forecast, and SHALL NOT ask for the difference
  between them

#### Scenario: The user insists on a calculation

- **WHEN** the user rejects a plan that looks for a stated elasticity and answers that they need a
  calculation
- **THEN** the preparation agent SHALL tell the user that Deep Research does not calculate
  figures and that, where no source states the elasticity, the report gives the figures it is
  computed from, and no recorded plan item SHALL ask to calculate the elasticity or promise a
  calculated result

#### Scenario: The user instructs a calculation

- **WHEN** the user asks for the average inflation over 2010–2020 and adds "compute it from the
  annual values"
- **THEN** the restated query SHALL ask for the average inflation over 2010–2020 without the
  instruction, the plan SHALL look for a stated average and, if no source states it, retrieve the
  annual values, and the agent SHALL tell the user that Deep Research does not calculate figures

### Requirement: The plan asks for the latest actual value of an indicator

When the query asks for the latest, most recent or current value of an indicator, the plan item
SHALL ask for its latest actual value, not the last observation of the series, because a dataset
series can run past today with forecasts. The plan SHALL name no year for that value: which period
is the latest actual one depends on the series. A query for a forecast, or for a stated period,
SHALL be planned as asked.

#### Scenario: The most recent value is planned as the latest actual value

- **WHEN** the user asks for the most recent real GDP growth rate of Canada from the World Economic
  Outlook dataset, whose series run several years past today with forecasts
- **THEN** the plan SHALL ask for Canada's latest actual real GDP growth rate, and SHALL NOT ask
  only for the latest observation of the series

#### Scenario: The plan names no year for the latest actual value

- **WHEN** the user asks for the current inflation rate of Canada
- **THEN** the plan SHALL ask for the latest actual value without fixing it to one calendar year

#### Scenario: A forecast query is planned as a forecast

- **WHEN** the user asks for the furthest-ahead forecast of Canada's real GDP growth
- **THEN** the plan SHALL ask for that forecast, and SHALL NOT ask for the latest actual value

#### Scenario: A stated period is planned as asked

- **WHEN** in March 2031 the user asks for Canada's real GDP growth rate last year
- **THEN** the plan SHALL ask for the value for 2030

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
- **WHEN** the user approved a revised plan in the conversation but `CrossTurnPrepState.plan` still holds an earlier version
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

### Requirement: start_research hard-gates and stops at readiness

The `start_research()` tool SHALL fail with an error naming the missing
precondition unless the working query is set, the clarifications are resolved, and
the plan is approved. On a passing gate the tool SHALL mark research as started and
return a ready-to-research summary (the finalized query and the approved plan). The
tool itself SHALL NOT run research, review, or report generation: the turn
coordinator launches the research graph after the preparation agent's run finishes
(see the **research-execution** capability), so the flag is the hand-off signal.

Once the gate has passed and research is marked as started, the preparation agent SHALL make **no
further model call** in that turn — so there is no acknowledgement, no "research is starting"
message written after the hand-off. This SHALL hold regardless of what the model would have
written: the app SHALL end the preparation agent's run as soon as research is marked as started,
rather than relying on the prompt to keep it quiet.

**Accepted limitation — one case remains outside that guarantee, by construction.** Text the model
emits on the **same** assistant message that carries the `start_research` call has already been
streamed by the time the tool executes, so nothing downstream of the call can withhold it, and DIAL
content cannot be retracted. Such text is contracted to reach the assistant content anyway (see
**dial-agent-with-mcp**'s assistant-content requirement, which carries text from intermediate
messages that also carry tool calls).

A launch turn MAY therefore still open with a stray sentence ahead of the report. The only guard is
that the preparation instructions no longer ask the agent to announce the hand-off, and the
instructions SHALL keep not asking for it. This is a knowingly accepted gap in the "the response is
the report alone" goal, not an omission: closing it would mean buffering all preparation text until
the agent run ends, at the cost of streaming clarifying questions live. The delivered content SHALL
be the report alone in every case the app can control.

A gate **failure** SHALL leave the agent free to continue: it receives the error, and it SHALL
still reply to the user — a rejected `start_research` SHALL never produce a turn with no
answer.

#### Scenario: Gate failure names the missing precondition
- **WHEN** `start_research` is called with the plan not yet approved
- **THEN** it SHALL fail with an error that names plan approval as the missing precondition, and SHALL NOT mark research as started

#### Scenario: Gate pass returns the ready-to-research summary
- **WHEN** `start_research` is called with the query clear and the plan approved
- **THEN** it SHALL mark research as started and return a summary containing the finalized query and the approved plan; the tool call itself SHALL NOT produce a research report

#### Scenario: Hand-off is silent
- **WHEN** `start_research` passes its gate during a turn
- **THEN** the preparation agent SHALL make no further model call in that turn, and no text written after the hand-off SHALL reach the assistant content

#### Scenario: Text on the calling message is the one case not suppressed
- **WHEN** the model emits natural-language text on the same assistant message that calls `start_research`
- **THEN** that text SHALL already have been streamed and SHALL remain in the assistant content, ahead of the report; ending the agent run cannot retract it, and only the prompt discourages it

#### Scenario: Gate failure still answers the user
- **WHEN** `start_research` is rejected because the plan is not approved
- **THEN** the preparation agent SHALL continue its run and reply to the user with what is still needed, and the turn SHALL NOT end with empty assistant content

### Requirement: Rewind continues from the surviving assistant message's state

Because `CrossTurnPrepState` and the transcript ride on the assistant message, the app SHALL
require no rewind-detection logic. When the user edits or regenerates an earlier
message and DIAL truncates the later turns, the app SHALL naturally continue from
the `CrossTurnPrepState` recorded on the last surviving assistant message. Editing the first
user message (no prior assistant message) SHALL start from a fresh `CrossTurnPrepState`.

#### Scenario: Rewound conversation continues from the surviving state
- **WHEN** a request's transcript has been truncated by a rewind so the last assistant message is an earlier one
- **THEN** the turn SHALL load the `CrossTurnPrepState` from that surviving assistant message and continue, without any special rewind handling

#### Scenario: Edited first message starts fresh
- **WHEN** the first user message is edited so the request carries no prior assistant message
- **THEN** the turn SHALL start from a fresh `CrossTurnPrepState`

### Requirement: Refuse input after research has started

When the loaded `CrossTurnPrepState` indicates research has already started, the app SHALL
refuse further input for that session and instruct the user to start a new
conversation, rather than running the preparation agent again. A persisted
`CrossTurnPrepState` says so only after research delivered its report: a failed research
turn persists the flag reset, so its conversation stays open for a resume
(**research-resume**).

#### Scenario: Message after launch is refused
- **WHEN** a request's loaded `CrossTurnPrepState` has the research-started flag set
- **THEN** the app SHALL return a message instructing the user to start a new conversation, and SHALL NOT run the preparation agent

#### Scenario: A conversation whose research failed is not refused
- **WHEN** a request follows a turn whose research run failed
- **THEN** the app SHALL run the preparation agent for it

### Requirement: Cross-context conversation is allowed during preparation

The preparation agent SHALL be able to answer the user's general, conversational
side questions (e.g. "what is CPI?") from its own knowledge during the preparation
flow, and SHALL steer the conversation back toward clarification and planning. The
agent's user-facing output SHALL be natural-language text (the questions, the plan,
or an answer); the user SHALL NOT be required to use any sentinel phrasing.

#### Scenario: Side question answered without derailing the flow
- **WHEN** the user asks a general question mid-preparation instead of answering the current question
- **THEN** the agent MAY answer it from its own knowledge and SHALL then continue the clarification or planning flow

### Requirement: Every preparation LLM call's inputs and outputs are specified

The preparation flow makes exactly three kinds of LLM call, and each one's inputs SHALL be
exactly what is listed here — nothing else reaches a model, and adding an input SHALL require
updating this requirement.

**1. The preparation agent's model call** (one per agent step)

- System prompt: the preparation instructions, filled with the instance's `agent_name`, today's
  date, the spans of years computed from that date, and the turn's data-sources string. The spans
  are the examples of a span counted back from today, and the default span of forecasts, the three
  years after the current one. The data-sources string holds the configured servers' descriptions,
  the document statistics block, the datasets section and the rendered glossary, each when its
  condition holds (see **data-sources-discovery**). When the list of datasets failed, it also
  carries the instruction to plan around the failure (see **data-sources-discovery**). It carries neither the instruction
  to request missing definitions nor the instruction about the dataset tools, because this agent
  has no MCP tools.
- Messages: the **full** conversation history reconstructed from the DIAL request — every user
  message as text, and for every prior assistant turn its persisted preparation agent messages
  (its `AIMessage`s and `ToolMessage`s), and directly after every prior assistant turn whose state
  carries the failure flag one fixed failed-turn note as a system message (**research-resume**) —
  followed by the current turn's accumulated messages. No research record is part of it: neither
  research-agent's messages nor a report draft. No image content is part of it, because the
  preparation agent has no MCP tools. There SHALL be no truncation, windowing, or
  summarization; a turn that outgrows the model's context SHALL fail rather than silently drop
  history.
- Tools bound: the four preparation control tools.
- Output: assistant text and/or tool calls. The text is the user-visible answer, except on a
  turn where research starts (see the silent hand-off rule below).

**2. The query clarity check** (one per `update_query` call)

- System prompt: the intake-check instructions, filled with today's date, the same spans of years
  computed from that date as the preparation agent receives, and the turn's data-sources string,
  the same one the preparation agent receives, with no instruction about a failed list of
  datasets.
- Messages: one human message carrying the rendered conversation so far and the candidate query.
  The rendering SHALL include only natural-language user and assistant text, and the
  failed-turn note as a `System note:` line at its position in the conversation; tool calls,
  tool results, and any other system message SHALL be dropped. No image content SHALL be
  included.
- Output: a structured `QueryReviewResponse` — a per-dimension assessment, then the clarifying
  questions (empty when the query is ready). The tool result carries the questions; the whole
  response is saved in the turn's `preparation.query_reviews` (**research-resume**).

**3. The plan approval check** (one per `approve_plan` call)

- System prompt: the plan-approval instructions, filled with today's date only — no server
  descriptions, no document statistics block, no datasets section and no glossary.
- Messages: one human message carrying the recorded plan as a numbered list and the rendered
  conversation, filtered exactly as in the clarity check. No image content.
- Output: a structured `PlanReviewResponse` — the assessment, whether the recorded plan matches
  the one last discussed, whether the user approved it, and a user-facing failure reason. The tool
  result carries the outcome and, on a refusal, the failure reason; the whole response is saved in
  the turn's `preparation.plan_reviews` (**research-resume**).

#### Scenario: The agent sees the whole conversation, the checks see only its prose

- **WHEN** a preparation turn runs on a conversation whose earlier turns contain preparation tool
  calls and tool results, and an earlier research turn whose research-agent messages hold page
  images
- **THEN** the preparation agent's model call SHALL receive the preparation tool calls and results
  and no image, while the clarity check and the approval check SHALL receive only the user and
  assistant text

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

#### Scenario: The agent and the clarity check receive the spans of the current year

- **WHEN** a preparation turn runs on 20 November 2025
- **THEN** the preparation agent's system prompt and the clarity check's system prompt SHALL each
  give the last 10 years as 2016–2025 and the next 3 years as 2026–2028

### Requirement: Stateless turns persist CrossTurnPrepState and transcript in DIAL custom state

The app SHALL process each turn statelessly, with no checkpointer and no
`interrupt()`. At the start of a turn it SHALL reconstruct the LangChain message
history from the DIAL transcript and load `CrossTurnPrepState` from the latest assistant
message's `custom_content.state` — the `CrossTurnPrepState` fields directly under its
`preparation` key (a fresh `CrossTurnPrepState` when none is present). At the end of a turn
it SHALL persist, via `choice.set_state`, the resulting `CrossTurnPrepState` fields under
`preparation`, next to the turn's preparation agent messages (`agent_messages`) and
the whole responses of its clarity checks (`query_reviews`) and approval checks
(`plan_reviews`); a research turn also persists its research record under
`research` (**research-resume**). A failed turn persists as well, with a failure
flag. A turn whose research run saved a snapshot persists its preparation agent
messages and reviews, its `CrossTurnPrepState` with the plan-approved and research-started
flags reset, and the snapshot. Any other failed turn, and a failed research turn
whose snapshot cannot be saved, persists only the `CrossTurnPrepState` the request's history
held when the turn started. A failure while the application properties are fetched
or validated persists nothing, and a turn never fails once its report is written.
When the full state of a turn whose report was written cannot be built or encoded,
the turn persists a closing state instead: its `CrossTurnPrepState` with research started,
and nothing else (**research-resume**). The app SHALL NOT keep server-side session
state across requests.

#### Scenario: Turn persists transcript and CrossTurnPrepState
- **WHEN** a turn completes and its full state can be built and encoded
- **THEN** the assistant message's `custom_content.state` SHALL contain, under `preparation`, the current `CrossTurnPrepState` fields, the turn's preparation agent messages and its reviews, and the app SHALL hold no other cross-request state for the session

#### Scenario: A delivered report whose state cannot be saved still closes the conversation
- **WHEN** a turn delivered its report and its full state cannot be built or encoded
- **THEN** the assistant message's `custom_content.state` SHALL contain the `CrossTurnPrepState` fields with research started and no agent messages, reviews or research record, and the next request SHALL be refused as a conversation whose research has started

#### Scenario: Next turn restores CrossTurnPrepState from the transcript
- **WHEN** a follow-up request carries a prior assistant message whose `custom_content.state` `preparation` field records a resolved clarification and an unapproved plan
- **THEN** the preparation agent for the new turn SHALL run with that `CrossTurnPrepState` restored, so the gates reflect the prior turn's progress without re-deriving it from the messages

#### Scenario: The turn after a failed research run restores the plan without approval
- **WHEN** a follow-up request's latest stateful assistant message was written by a failed research turn that saved a snapshot
- **THEN** the preparation agent SHALL run with that turn's query, plan and plan id restored, and with the plan-approved and research-started flags false

### Requirement: The plan covers each part of the query and keeps what the user asked for

The preparation agent's prompt SHALL tell it to find each separate part of the query and to make
sure that the plan covers each one. A part is what makes two requested values different, such as a
country, a period or a forecaster. One plan step MAY cover several parts, for example the same
indicator for several countries.

The restated query and the plan SHALL keep what the user asked for. They SHALL NOT add a detail
that the user did not state. Every detail that the user stated SHALL stay in the query and in every
plan step. The only exception is an instruction to calculate or round a figure: both leave it out,
and the agent tells the user (see "The agent tells the user which requested operations Deep
Research does not perform"). A request to convert keeps its target unit in the query and in every
plan step that looks for the figure. When the user asks to compare two values, the plan SHALL NOT
assume that they come from one source, unless the user says so. A plan step that names where to
look, as the rules on data sources require, is not an added detail. The restated query SHALL be a
full question or a full instruction, not a noun phrase.

The plan SHALL say what research looks for, and never how the report looks. It SHALL carry no
step and no phrase about the form of the report: no table, chart or list, and no sections, order
or length. The one exception is a form that the user asked for, in the query or in a later
message. Then exactly one plan step SHALL ask for that form, as the user described it, and the
plan SHALL add no other form. That step is written as a plan step, such as "Present the forecasts
in a table", and never as a copy of the user's message. A rounding or a conversion is not a form:
when the requested form carries one, such as "a table with one decimal", the step asks for the
form without it.

#### Scenario: The restated query is a full question

- **WHEN** the user asks "What was the unemployment rate of Canada in 2023?"
- **THEN** the restated query SHALL be a full question, such as "What was the unemployment rate of
  Canada in 2023?", and SHALL NOT be a noun phrase such as "Unemployment rate of Canada in 2023"

#### Scenario: Two forecasts to compare are two parts

- **WHEN** the user asks to compare the IMF forecast of euro-area GDP growth for 2026 with the
  consensus forecast
- **THEN** the plan SHALL cover both forecasts, and SHALL NOT add that they come from the same
  publication

#### Scenario: A stated detail stays in every plan step

- **WHEN** the user asks for the real exports of Italy in euros over 2010–2019
- **THEN** the restated query and every plan step that looks for the figure SHALL keep "real",
  "in euros" and the period

#### Scenario: No form of the report unless the user asks for one

- **WHEN** the user asks for the IMF forecasts of GDP growth for Germany and France and asks for no
  form of the report
- **THEN** no plan step SHALL ask for a table, a chart, a list, sections, an order or a length

#### Scenario: A requested form becomes one plan step

- **WHEN** the user asks for the same forecasts and adds, in a later message, that they want them
  in a table
- **THEN** exactly one plan step SHALL ask to present the forecasts in a table, and no plan step
  SHALL ask for any other form

#### Scenario: A requested form that carries a rounding

- **WHEN** the user asks for the same forecasts "in a table with one decimal"
- **THEN** exactly one plan step SHALL ask to present the forecasts in a table, and no plan step
  SHALL ask for one decimal

### Requirement: The plan never asks to convert or round a figure

The plan the preparation agent drafts SHALL NOT ask to convert a figure to another unit, scale or
notation, or to round it, because the report gives every figure as its source gives it (see
**faithful-relay**, "Rule 4 — figures keep their source's value, unit and period"). The plan SHALL
NOT mention the precision of figures.

A unit, a currency or a scale that the user asks a figure in, such as "the exports of Mexico in
euros", is part of the requested fact. It stays in the restated query and in the plan, because it
decides which source research looks for. It SHALL NOT become a plan item that converts a value from
another unit.

An instruction to convert a figure to a unit is a request for the figure in that unit. The restated
query and every plan step that looks for the figure SHALL give the figure in the target unit,
without the words that ask to convert: "Mexico's exports, converted to euros" becomes "Mexico's
exports in euros". Research needs no conversion to answer it: when no source gives the requested
fact in the requested unit, a value in another unit is an exact match (see **source-selection**, the
term "Exact match" and its exception for the unit).

An instruction to round a figure, such as "round the figures to two decimal places", SHALL stay out
of the restated query and the plan. It is neither a detail that the query and the plan keep nor a
form of the report (see "The plan covers each part of the query and keeps what the user asked for").

#### Scenario: The user asks for rounded figures

- **WHEN** the user asks for the unemployment rate of Spain from 2012 to 2016 "to two decimal
  places"
- **THEN** neither the restated query nor any recorded plan item SHALL carry the rounding, also as
  a step for a form of the report, and no plan item SHALL mention the precision of the figures

#### Scenario: A requested currency selects the source

- **WHEN** the user asks for the exports of Mexico "in euros"
- **THEN** the restated query and the plan SHALL keep "in euros" as part of the requested fact, and
  no plan item SHALL ask to convert a value from another currency

#### Scenario: A requested conversion keeps its target unit, with the note

- **WHEN** the user asks for "Mexico's exports, converted to euros"
- **THEN** the restated query and every plan step that looks for the figure SHALL ask for Mexico's
  exports in euros, no plan item SHALL ask to convert a value, and the agent SHALL tell the user
  that Deep Research does not convert figures

### Requirement: The agent tells the user which requested operations Deep Research does not perform

Deep Research does not calculate, round or convert figures (see "The plan never asks for a
calculation" and "The plan never asks to convert or round a figure"). The preparation agent's
prompt SHALL keep every rule for these requests in one section, "Unsupported operations", after the
description of the three stages. The stages and the `update_query` tool's description SHALL refer to
that section instead of restating its rules. The section SHALL state that Deep Research never does
these operations, for every request and also when the user insists, and SHALL give its examples in
the order of the reply: the note, then the query. The rules apply to the query, to the plan and to
the agent's replies.

When the user gives an explicit instruction to calculate, round or convert a figure, such as
"compute it from the annual values", "round the figures to two decimal places" or "convert it to
euros", the preparation agent SHALL give the note: one sentence that tells the user that Deep
Research does not do the operation. The note SHALL:

- name only the operations that the user asked for;
- say what the report gives instead, for example "Deep Research does not round figures: the report
  gives each figure at the precision of its source";
- never promise or offer a calculated, rounded or converted figure;
- never ask the user whether to do the operation.

The note is required only for an explicit instruction. A figure that looks like the result of a
calculation or a transformation, and that a source can state as its own indicator, is a request for
a figure. Examples are a multi-year average, a share of GDP and a share in percent. Such a request
SHALL NOT require the note, and a note there is acceptable: the preparation agent cannot know which
figures the sources state. A plain request with no calculation or transformation, such as "the
exports of Mexico in euros", SHALL NOT get the note.

The agent SHALL write the note once in a reply. When the reply presents the block that
`update_plan` returns, the note SHALL come directly before the block. The `update_plan` tool's
response SHALL tell the agent not to write again a sentence that it already wrote in the turn, such
as the note. When the user insists on an operation in a later message, the agent SHALL give the
note again, and SHALL add the operation neither to the query nor to the plan. Whether the agent
records the plan again and presents the block again is left to the agent. Client rules cannot allow
a calculation, a rounding or a conversion, so the note holds for every channel.

#### Scenario: The user asks to round

- **WHEN** the user asks for the unemployment rate of Spain from 2012 to 2016 "to two decimal
  places"
- **THEN** the agent SHALL tell the user that Deep Research does not round figures, and the
  note SHALL NOT name a conversion or a calculation

#### Scenario: The user asks for two operations

- **WHEN** the user asks for the exports of Mexico in 2019 and asks to "convert them to euros and
  give them to two decimals"
- **THEN** one sentence SHALL tell the user that Deep Research does not convert and does not round
  figures

#### Scenario: A share of GDP or a multi-year average needs no note

- **WHEN** the user asks for "the debt of Italy as a share of GDP" or for "the average inflation of
  France over 2010–2020", and gives no instruction to calculate or convert
- **THEN** the agent SHALL NOT be required to tell the user that Deep Research does not calculate
  or convert figures, and the plan SHALL look first for a source that states the figure

#### Scenario: A plain request gets no note

- **WHEN** the user asks for the exports of Mexico "in euros" and gives no instruction to convert
- **THEN** the agent SHALL NOT tell the user that Deep Research does not convert figures

#### Scenario: The note appears once

- **WHEN** the user asks to calculate the average from the annual values
- **THEN** the agent's reply SHALL give the note that Deep Research does not calculate figures
  once, directly before the block that `update_plan` returns, and SHALL NOT repeat it

#### Scenario: The user insists on a rounding

- **WHEN** the user rejects a plan because it does not promise figures with two decimals
- **THEN** the agent SHALL tell the user again that Deep Research does not round figures, and
  SHALL NOT change the query or the plan; it MAY record the same plan again and present the block
  again

### Requirement: The agent asks for an approval check only for a clear approval

The preparation agent SHALL call `approve_plan` only when the user's message clearly approves the
plan and asks for no change to the query or the plan. The wording of an approval can vary. A
message that approves the plan and also asks for a change is a request for a change, and the agent
SHALL handle the change first.

#### Scenario: An approval with a change is a change

- **WHEN** the user answers a presented plan with "looks good, but add France"
- **THEN** the agent SHALL NOT call `approve_plan`, and SHALL revise the query or the plan to add
  France

### Requirement: A plan step names a data source, not its series

A plan step SHALL name a data source by its name. It SHALL NOT name a series, an indicator or a
value from the description of a data source, because research chooses them. A plan step SHALL write
the requested figure in the words of the query.

The descriptions of the data sources show examples, not everything that a source holds. The
preparation agent SHALL use them only to choose the sources to search. It SHALL NOT match the
request to the series, units or values that a description lists. The preparation agent's prompt
SHALL say so next to the data sources.

#### Scenario: A plan step names the source, not a series

- **WHEN** the user asks for the real exports of Japan, and the description of a dataset lists a
  series named "Exports"
- **THEN** the plan step SHALL name the dataset and ask for "real exports", and SHALL NOT name the
  series "Exports"

### Requirement: A period named by an event or an era is written with its years

A period named by an event or an era, such as a war or a presidency, SHALL get its years in
parentheses after the name. The agent SHALL write the years wherever the query or the plan names
that period:

- A period with a start and an end SHALL get both years.
- A period that starts at an event and has not ended SHALL get only the start year.
- An open end that names no event, such as "until now" or "from 2020", SHALL stay as the user wrote
  it. The agent SHALL NOT add today's date or an end year to it.

The query check SHALL treat an event or an era that it recognizes as a settled time period. The
preparation agent's prompt SHALL state the three cases with an example of each.

#### Scenario: A closed era gets both years

- **WHEN** the user asks how the industrial output of the United Kingdom changed "during the Second
  World War"
- **THEN** the query the agent records and every plan step that names the period SHALL give it as
  "during the Second World War (1939–1945)", and the agent SHALL NOT ask the user for the years

#### Scenario: An open start at an event gets one year

- **WHEN** the user asks how the GDP of Germany developed "since the fall of the Berlin Wall"
- **THEN** the query the agent records SHALL give the period as "since the fall of the Berlin Wall
  (1989)", and SHALL NOT add an end year

#### Scenario: An open end stays as the user wrote it

- **WHEN** the user asks to summarize the key developments in a subject "until now"
- **THEN** the query the agent records SHALL keep "until now", and SHALL NOT add today's date or
  the current year to it
