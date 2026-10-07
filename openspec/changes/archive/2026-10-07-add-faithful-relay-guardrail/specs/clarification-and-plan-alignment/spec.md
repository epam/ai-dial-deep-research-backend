## MODIFIED Requirements

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
- **THEN** the recorded plan SHALL be cleared and the plan-approved flag SHALL be reset to false


#### Scenario: A rounding request survives the restatement

- **WHEN** the user asks for GDP growth by region "rounded to one decimal"
- **THEN** the query the agent records with `update_query` SHALL keep the request to round to
  one decimal
