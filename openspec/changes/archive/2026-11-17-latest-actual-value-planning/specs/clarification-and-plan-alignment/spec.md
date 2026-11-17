# Spec Delta

## ADDED Requirements

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
itself. The latest, most recent or current value of an indicator is not such a reference: it is
the indicator's latest actual value, it is settled and needs no period. Time references anchored to a named event or era (e.g. "Trump's first
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

#### Scenario: The current value of an indicator needs no period
- **WHEN** the request asks for the current unemployment rate of Canada, with no period given
- **THEN** the clarity check SHALL record no question about the time period

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
