## ADDED Requirements

### Requirement: The plan covers each part of the query and keeps what the user asked for

The preparation agent's prompt SHALL tell it to find each separate part of the query and to make
sure that the plan covers each one. A part is what makes two requested values different, such as a
country, a period or a forecaster. One plan step MAY cover several parts, for example the same
indicator for several countries.

The restated query and the plan SHALL keep what the user asked for. They SHALL NOT add a detail
that the user did not state, and SHALL NOT drop a detail that the user stated. When the user asks
to compare two values, the plan SHALL NOT assume that they come from one source, unless the user
says so. A plan step that names where to look, as the rules on data sources require, is not an
added detail.

The plan SHALL say what research looks for, and never how the report looks. It SHALL carry no
step and no phrase about the form of the report: no table, chart or list, and no sections, order
or length. The one exception is a form that the user asked for, in the query or in a later
message. Then exactly one plan step SHALL ask for that form, as the user described it, and the
plan SHALL add no other form. That step is written as a plan step, such as "Present the forecasts
in a table", and never as a copy of the user's message.

#### Scenario: Two forecasts to compare are two parts

- **WHEN** the user asks to compare the IMF forecast of euro-area GDP growth for 2026 with the
  consensus forecast
- **THEN** the plan SHALL cover both forecasts, and SHALL NOT add that they come from the same
  publication

#### Scenario: No form of the report unless the user asks for one

- **WHEN** the user asks for the IMF forecasts of GDP growth for Germany and France and asks for no
  form of the report
- **THEN** no plan step SHALL ask for a table, a chart, a list, sections, an order or a length

#### Scenario: A requested form becomes one plan step

- **WHEN** the user asks for the same forecasts and adds, in a later message, that they want them
  in a table
- **THEN** exactly one plan step SHALL ask to present the forecasts in a table, and no plan step
  SHALL ask for any other form

## MODIFIED Requirements

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
**faithful-relay**). The agent SHALL add no formatting request of its own.

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

#### Scenario: A unit request survives the restatement

- **WHEN** the user asks for the exports of Germany "in US dollars"
- **THEN** the query the agent records with `update_query` SHALL keep "in US dollars", and SHALL
  add no formatting request that the user did not make, such as a number of decimals

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

The query itself is unaffected: the preparation agent restates what the user asked for, a request
for a computed figure included, and the plan alone carries how research handles it. The query check
SHALL treat a request for a computed figure as a clear subject, and its prompt SHALL say what
research does with it: look for a source that states the figure and, where none does, retrieve the
figures it would be computed from. The query check SHALL NOT ask about such a request: neither how
the figure should be computed, such as a method, a formula or a regression specification, nor what
to report instead.

The rule SHALL hold when the user insists on a calculation or rejects a plan without one. The
preparation agent SHALL then say plainly that research does not compute figures and that, where no
source states the figure, the report gives the cited figures the calculation needs, and SHALL keep
the plan item that looks for a stated figure. No plan item SHALL calculate or promise a calculated
result.

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
- **THEN** the preparation agent SHALL say that research does not compute figures and that the
  report will give the cited figures the calculation needs where no source states it, and no
  recorded plan item SHALL ask to calculate the elasticity or promise a calculated result

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
