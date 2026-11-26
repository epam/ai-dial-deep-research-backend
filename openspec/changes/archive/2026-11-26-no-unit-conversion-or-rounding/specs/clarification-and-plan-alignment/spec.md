## ADDED Requirements

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

## MODIFIED Requirements

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
