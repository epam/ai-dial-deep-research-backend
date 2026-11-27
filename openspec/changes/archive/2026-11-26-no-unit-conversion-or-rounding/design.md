## Context

Four texts let the report change a figure today:

- The faithful-relay rule "Each figure with its source's value, unit and period"
  (`src/dial_deep_research/app/research/faithful_relay.py`). Its writer part allows "One notation"
  (a scale word, a currency symbol or code, a thousands separator, a fraction written as a
  percentage) and "Usable precision" (round a value with more digits than a reader can use). Its
  blind-review part reports "a figure with more digits than a reader can use". The grounded review
  judges the draft by the writer part, because the policy sets `grounded_by_writer_parts`; the
  policy sets no grounded part of its own (`faithful_relay.py`, module docstring).
- `CALCULATION_DEFINITION` in `src/dial_deep_research/app/research/prompts.py`: "Three things are not
  calculations and stay allowed: a comparison …; writing a value in another notation …; and rounding
  a value …". The writer's section "No calculation by research or the report" and the blind review's
  check 7 are both built from it; the grounded review gets the writer's section.
- The term "Calculation" in `FAITHFUL_RELAY_TERMS`, same file as the rule: "Writing a value in the
  unit its source states for it, such as a fraction written as the percentage its series name
  states, is not a calculation either."
- The writer's list "These rules outrank the request" in `prompts.py`: "keep every figure as its
  source gives it, apart from the changes that the rule … allows".

The rule already ignores a request to round ("Do this also when the research question or the plan
asks to round figures or to give a number of decimals"); it still rounds on its own judgment.

StatGPT's data query tool now presents values itself, per dataset configuration (statgpt-backend
PRs #799 and #804, documented in its `statgpt/app/MCP_DATA_QUERY_RESPONSE.md`):

- `fractionToPercent` multiplies the configured fraction series by 100 and sets their unit attribute
  to `%`, so that no reader takes a converted value for a fraction or converts it again. The unit attribute is
  empty for the other series, so their unit, where they have one, is stated in the indicator name,
  as in "Gross domestic product, constant prices, percent change" (the example in
  `src/dial_deep_research/app/research/language_style.py`).
- `decimalPlaces` rounds the values after the conversion; a value too small for that precision keeps
  its first significant digit.
- Both apply only to the values the model reads (the `text/csv` and `text/markdown` resources). The
  user's attachments keep the stored values at full precision.

Client rules follow the generic rules at every step, and a more specific client rule is followed,
with one exception: the rule that nobody calculates (`_CLIENT_RULES_BLOCK` and
`_CLIENT_WRITER_RULES_CONTEXT` in `prompts.py`; **source-selection**, "Client rules follow the
generic rules in a tagged block").

The intake prompt (`PREP_AGENT_SYSTEM`, `src/dial_deep_research/app/preparation/prompts.py`) keeps
"the user's formatting requests, such as a unit" in the restated query. Its plan rules forbid a
calculation step and say nothing about a conversion or a rounding, and they allow one plan step for
a form of the report that the user asked for.

The source-selection terms already decide what a requested unit means for source choice: when no
source of one kind gives the requested fact in the requested unit, the value in another unit is an
exact match (`src/dial_deep_research/app/research/source_selection.py`, the exact-match term). A
unit request therefore needs no conversion to be answered.

## Goals / Non-Goals

**Goals:**

- No step of Deep Research changes a figure: no rounding, no change of unit, scale or notation.
- No request switches this off: not the user, the plan or a section's description. A channel's
  configuration carries no client rule that asks for it.
- A user who asks for a conversion or a rounding learns at planning time that the report will not
  do it.
- The reviews stop pushing the writer toward a change: no "too many digits" finding, and no finding
  that invites a made-up unit.

**Non-Goals:**

- Making unconfigured datasets readable. A dataset without `decimalPlaces` or `fractionToPercent`
  shows its raw values; that is fixed in its StatGPT configuration.
- Changing how sources are selected. The source-selection rules stay as they are, and a comparison
  or a rank stays allowed; the only addition is Decision 7's permission.
- Making rule 4 a second exception that no client rule overrides (Decision 6).
- Requiring every comparison to judge values at the precision of the less precise one. Rule 4
  permits it in one sentence (Decision 7); it does not require it, and it adds no other comparison
  guidance.
- A deterministic code check that every number in the draft occurs in a cited source. It would catch
  a rounding without a model, but it is a separate change with its own false positives (dates, page
  numbers, counts).
- Editing the files outside this repository (see "Work outside this repository").

## Decisions

### 1. The report changes no figure at all: no rounding and no notation change

The writer part says: write each number as its source writes it, with the same digits, decimals,
unit, currency and scale word; do not round, do not add digits, do not convert to another unit,
scale or notation. The examples name the changes models make: a fraction to a percentage, millions
to billions, a currency symbol to a code, a thousands separator added or removed.

Decided by the owner's instruction, and by the constitution's principle 8 "Each component owns its
concern": the data layer presents the values. A second presentation step in Deep Research can only
disagree with the first one, for example by rounding a configured `3.512` to `3.5`.

Alternatives:

- **Keep "One notation", drop only "Usable precision".** Rejected. The owner's concern is the risk of
  a wrong number, and a rescaling (`$500,000` to `USD 0.5 million`) is exactly where a model is wrong
  by a factor of 1,000, in a way no review can see without the source. The main readability gain of
  notation changes, fractions shown as percentages, now comes from the data layer.
- **Allow only adding or removing a thousands separator.** Rejected by the owner: one plain rule,
  "write the number as its source writes it", is easier for the model to follow than a rule with an
  exception.
- **Keep "Usable precision" as a fallback for datasets the data layer does not round.** Rejected:
  the writer cannot tell a configured value from an unconfigured one, so the fallback would also
  re-round configured values; and principle 8 puts the fix in the dataset's configuration.

### 2. A unit is given only where the source states it, and a series name states it

The writer gives the unit, the currency and the scale word that the source states for the value: a
unit attribute or column, a table heading, the text of a page, or the series name, such as an
indicator named "…, percent change" or "…, US dollar, billions". It gives that unit as the source states it, with one allowance:
"percent" may be written as "%". A currency is written as the source writes it. The writer never
gives a unit that the source does not state.

The owner assumes that StatGPT converts every series stored as a fraction and rounds correctly, so a
percentage stated in a series name belongs to a value that is already a percentage.

Alternative: **never take a unit from a series name; relay the name and attach nothing.** Rejected
by the owner. In the data layer's output, the unit attribute is set only on converted series, so for
most dataset values the series name is the only place that states the unit or currency. The ban
would strip "%" and "USD" from them, and the blind review would then ask for a false "the source
states no unit". It would also not stop the misreading it was meant to prevent, because the relayed
name carries the "%" next to the value.

### 3. The blind review keeps its unit check, with a fix that cannot invent a unit

The blind review still reports a figure without its unit, currency or scale word, because a writer
that drops the "%" of a publication value, or the "billions" of a series name, is a real failure.
The finding asks for the unit, currency or scale word that the source states, its series name
included, or, where the source states none, a sentence that the source states no unit; the writer,
who sees the source, makes that choice, and the writer part already asks for that sentence. It never proposes a unit. The "more digits than a reader can use" check
is removed.

Alternatives:

- **Keep the check as it is.** Rejected: the writer can answer a finding "a figure without a unit"
  with a made-up unit such as "units", which no source states.
- **Remove the blind unit check and leave units to the grounded review.** Rejected: the grounded
  review judges the whole writer rule against the transcript and can miss a dropped unit among many
  items; the blind check is cheap and catches it from the draft alone.

### 4. `CALCULATION_DEFINITION` sends conversion and rounding to rule 4 instead of calling them calculations

The definition keeps the comparison as the one allowed thing, and says that a change of unit, scale
or notation that needs no rate, and a rounding, are forbidden by the rule "Each figure with its
source's value, unit and period". A conversion that needs a rate, such as into another currency,
stays a calculation, as today: it keeps the highest priority, which no client rule overrides, and
the blind review's check 7 still judges it. The faithful-relay term "Calculation" drops its
exemption sentence.

Alternative: **define a conversion and a rounding as calculations.** Rejected. Then the blind
review's check 7 would have to judge them, and it cannot: a cited `3.5%` looks the same whether the
source said `3.5%` or `3.512%`. Rule 4 already splits the work correctly: the grounded review, which
sees the transcript, judges the value by the writer part; the blind review judges only what the
draft shows.

### 5. A request for an unsupported operation is answered at planning time and left out of the query

All the rules below live in one section of `PREP_AGENT_SYSTEM`, "Unsupported operations", after
Stage 3, so that the query, the plan and the replies follow one text. Stage 1, Stage 2 and the
`update_query` tool's description refer to the section and restate none of its rules. The section
states the invariant once: Deep Research never calculates, rounds or converts figures, for every
request and also when the user insists. Its examples follow the order of the reply: the note, then
the query.

- Deep Research does not calculate, round or convert figures. Only an explicit instruction counts as
  a request for one of these operations: "compute it from the annual values", "round the figures to
  two decimal places", "convert it to euros".
- A figure that looks like the result of a calculation or a transformation, and that a source can
  state as its own indicator, is a request for a figure. Examples are a multi-year average, a share
  of GDP and a share in percent. The preparation agent cannot know which figures the sources state,
  so it needs no note there; a note there is acceptable. A plain request with no calculation or
  transformation gets no note.
- What each instruction leaves in the restated query and the plan:
  - A calculation leaves the figure. The plan looks first for a source that states it and otherwise
    retrieves the figures it is computed from, as the calculation rule already says.
  - A rounding leaves nothing. A requested form that carries a rounding, such as "a table with one
    decimal", becomes a step for the table alone.
  - A conversion becomes the figure in the target unit, in the query and in every plan step that
    looks for the figure: "Mexico's exports, converted to euros" becomes "Mexico's exports in
    euros". Research needs no conversion for it: when no source gives the requested fact in the
    requested unit, a value in another unit is an exact match (`source_selection.py`, the
    exact-match term's exception for the unit).
- For each explicit instruction, the intake agent gives the note: one sentence that names only the
  requested operations and says what the report gives instead. The note never promises the
  operation and never asks whether to do it. The user sees the note before approving the plan, so
  the dropped request does not read as forgotten (the Deep Research constitution in `CLAUDE.md`,
  principle 11 "The user knows what happens"). When the user insists, the agent gives the note
  again and adds the operation neither to the query nor to the plan. Whether it records the plan
  again is left to the agent.
- A unit, a currency or a scale that the user asks a figure in is part of the requested fact. It
  stays in the query and the plan, because the source-selection rules search for it, and it gets no
  note.
- The plan does not mention the precision of figures.
- The writer therefore sees no instruction to calculate or round in the research question, and
  sees a conversion only as a requested unit. It follows rule 4 through the existing "These rules
  outrank the request" mechanism. Its faithful-relay item becomes
  "keep every figure as its source gives it, with no rounding and no conversion", and the paragraph
  about section descriptions names a rounding or a conversion among the things a description
  cannot ask for. A configured section description is a likely place to ask for "figures rounded
  to one decimal".

Alternatives:

- **Keep the request in the restated query, and let the writer ignore it.** Rejected: the writer
  reads the request in the research question and can comment in the report on not applying it,
  which neither the outrank list nor an added "do not say that you did not" sentence prevents.
- **Drop the request without a sentence.** Rejected: the user would read the restated query as the
  agent having forgotten the instruction.
- **One fixed sentence that names all three operations.** Rejected by the owner: a user who asked
  only to round would read about conversions and calculations they never asked for.
- **A note for every requested average.** Rejected by the owner: a note there is optional, not
  required, because the preparation agent cannot know whether a source states the figure.
- **Omit the target unit of a conversion from the query and the plan.** Rejected: research does
  not need the unit omitted, because it accepts a value in another unit when no source gives the
  requested one.
- **Keep the target unit of a conversion only as a preference, such as "preferably in US
  dollars".** Rejected by the owner: the target unit is the requested fact, so the query names the
  figure in it.
- **Say in the report that a requested conversion was not done.** Rejected: the user is told at
  planning time, when they can still react, and the outrank list forbids that commentary.
- **Ask a clarifying question about it.** Rejected: the answer cannot change what the report does.
- **A rule of its own for a user who insists**, such as "call `update_plan` again with the same
  steps" or "call no tool". Rejected: an absolute rule for one scenario conflicts with the
  scenarios next to it, such as a user who insists and asks for another change in the same message,
  where the agent must revise the plan. The invariant "also when the user insists" decides what
  matters, the operation stays out and the user is told, and leaves the tool calls to the agent.
- **Rules for each operation in Stage 1 and Stage 2, next to the steps they affect.** Rejected: the
  same rule stated in several places drifts, and the stages only need to point to the section.

### 5a. The update_plan tool labels the query and the plan

The reply that presents a plan opens with the restated query as a bare sentence, so a user cannot
tell the query from the agent's own text, and with a sentence about an unsupported operation in
front of it the reply is hard to read. The `update_plan` tool returns the query and the plan as one
block, the query after the label "Research query:" and the steps after the label "Plan:", and the
agent copies the block verbatim, as it already copies the query and the plan.

Alternatives:

- **Tell the agent in its prompt to add the labels.** Rejected: the tool already owns the text that
  the agent copies verbatim, so the labels belong in it, and a prompt instruction would be one more
  thing the agent can paraphrase.
- **Render the block into the message from code.** Deferred, as the main spec already says: the
  agent writes the reply, and moving the query and the plan out of it changes the turn's streaming
  and the approval check's view of the conversation.

### 5b. A period named by an event or an era gets its years; an open end stays as written

A period named by an event or an era, such as a war or a presidency, gets its years in parentheses
after the name, wherever the query or the plan names it:

- A period with a start and an end gets both years: "during the Second World War (1939–1945)".
- A period that starts at an event and has not ended gets only the start year: "since the fall of
  the Berlin Wall (1989)".
- An open end that names no event, such as "until now" or "from 2020", stays as the user wrote it,
  with no date.

Research reads the query and the plan, not the conversation, so the years must be written where it
reads them. An open end is left alone because the agent can otherwise write today's date into it,
which pins a period that the user left open.

The query check (`QUERY_REVIEW_SYSTEM`) lists the cases in which it asks for the time period: the
query names no period and no event or era; a bare "latest", "recent" or "lately" has no anchor; or
the query names an event or an era that the check does not recognize. Words such as "outlook",
"overview", "trends" or "current state" name no period: they can read as a time signal, and the
check says so to ask for the period of such a query.

### 5c. The note is written once, and the query leaves out the instruction

The agent can write the note as text together with its `update_plan` call and then again, in the
reply after the tool returns, in front of the block. The prompt therefore says to write the note
once in a reply, and directly before the block when the reply presents the block. The tool's response, which
the agent reads right before that reply, tells it not to write again a sentence that it already
wrote in the turn, such as the note. That sentence covers a note that the agent still writes
together with the call.

The agent writes the query in its first tool call, `update_query`. The tool's description, which
the agent reads when it makes that call, refers to the section "Unsupported operations" for a
request to calculate, round or convert a figure. The Stage 1 sentence that keeps the user's
formatting requests in the query names the same exception and points to the same section.

Alternatives:

- **Write the note "directly before the query and the plan", without naming the tool call.**
  Rejected: it does not say whether the note goes with the tool call or after it, so the note can
  appear twice.
- **Drop the Stage 1 exception for an instruction to calculate, round or convert.** Rejected:
  without it, the Stage 1 sentence that keeps the user's formatting requests in the query can keep
  a rounding in the query.
- **Examples of such instructions in the Stage 1 exception**, such as "compute the mean". Rejected:
  an example of an instruction can be read as a request for a figure, which then gets a note that it
  does not need.
- **Examples that copy the wording of specific user queries.** Rejected: they overfit the prompt to
  those queries (the Deep Research constitution in `CLAUDE.md`, principle 3 "Do not overfit").
- **A one-sided example, "convert it to euros" leaves no currency.** Rejected: it can be read as
  dropping any currency, including one that the user asks the figure in.

### 5d. A plan step names a data source and keeps the user's words

A plan step names a data source by its name. It does not name a series, an indicator or a value
from the description of a data source, because research chooses them, and it writes the requested
figure in the words of the query. Example: for "the real exports of Japan", the step says "real
exports", also when a dataset lists a series named "Exports". A plan step that copies a series
name can drop a qualifier that the user stated, such as "real" or "nominal".

The data-source descriptions in the prompt show examples, not everything that a source holds. The
prompt says so next to them, and says to use them only to choose the sources to search, never to
match the request to the series, units or values that they list. Research does that matching.

Every detail that the user stated stays in the query and in every plan step. The only exception is
an instruction to calculate or round. A conversion keeps its target unit in every plan step that
looks for the figure.

Alternative: **a plan-step rule "keep the user's qualifiers", such as "nominal".** Rejected: it
treats the symptom. The rule that a step names the source and not the series addresses the cause.

### 5e. The restated query is a full question or instruction

The user sees the restated query after the label "Research query:", and the report is written from
it. Stage 1 says to write it as a full question or a full instruction, not as a noun phrase, and the
calculation example shows its query as a full question. A query written as a noun phrase, such as
"Unemployment rate of Canada in 2023", reads as a fragment after the label.

Alternative: **keep the user's own words for each detail in the restatement, and give "since 2018"
as an open-end example.** Rejected: the rule on named periods already decides an open end, and the
extra rule only adds wording; it also drops "from 2020" from the open-end examples.

### 5f. The query check says only which questions not to ask

The query check (`QUERY_REVIEW_SYSTEM`) is a separate LLM call and does not see `PREP_AGENT_SYSTEM`,
so the section "Unsupported operations" does not reach it. Its task is to decide which clarifying
questions the agent asks. Its prompt therefore says only which questions not to ask:

- A figure that needs a calculation, and a figure in a unit or a currency that the user names, are
  clear subjects.
- It does not ask how to calculate or convert a figure, such as a formula or an exchange rate.
- It does not ask which figure or unit to report instead.

The preparation agent asks the user every question that the check returns, so a question about an
operation reaches the user unless the check itself leaves it out.

Alternatives:

- **Tell the check that Deep Research never calculates, rounds or converts, and what research does
  with such a figure.** Rejected: the check does not need the reason to know which questions not to
  ask, and a check that knows a conversion will not be made can ask instead whether to report the
  figure in another unit.
- **Let the preparation agent drop the check's questions about operations.** Rejected: the agent
  relays the check's questions as they come, and a filter in the agent would make it judge the
  check.

### 5g. The agent calls approve_plan only for a clear approval

Stage 3 says to call `approve_plan` only when the message clearly approves the plan and asks for no
change to the query or the plan. A message such as "looks good, but add France" approves and asks
for a change at once, and the change comes first.

Alternative: **leave it to the approval check of `approve_plan`.** Rejected: that check reports the
requested change, but only after a call that the agent should not make, and the agent then has to
revise the plan in a second step.

### 6. Client rules keep their precedence; a channel's configuration carries no converting rule

Rule 4 does not claim to hold against a client rule. The client-rule precedence stays as it is: a
more specific client rule is followed, and only the rule that nobody calculates is exempt. A client
rule that tells the writer to convert or round is removed from the channel's configuration instead.
The owner's assumption is that no client rule allows a calculation, a rounding or a conversion, so
the intake agent's sentence holds for every channel and the intake agent needs no client rules.

Alternative: **make rule 4 a second exception that no client rule overrides.** Rejected by the
owner. It would edit the client-rules block, the grounded review's client context, the `client_rules`
field description and three spec requirements, for a case that the channel configuration settles by
removing one rule. Writing "also when a client rule asks" into rule 4 alone was rejected in review,
because it contradicts the client-rules block at every step.

### 7. A comparison may judge two values at the precision of the less precise one

Rule 4 governs the figures the report writes. A comparison writes no figure: it says whether one
value is above, below or equal to another. A source may give a value rounded for presentation, so
two sources can give the same value at different precisions, and a dataset `3.512%` and a
publication `3.5%` can be the same value. A comparison may therefore judge the two values at the
precision of the less precise one, while both are written as their sources give them. Rule 4 says
so in one sentence, so that a rounding ban on written figures is not read as a ban on such a
comparison.

Alternative: **compare the values as written, so `3.512%` is above `3.5%`.** Rejected by the owner:
it can report a difference that is only a difference of presentation.

## Prompt texts

The report-side wording below was the starting point for implementation; the implementer kept the
meaning and fitted it to the surrounding text.

Writer part of "Each figure with its source's value, unit and period":

```
Keep every figure's value, unit, currency and period as its source gives them, and say whether it
is nominal or real where the source says so. Write each number as its source writes it: the same
digits, the same decimals, the same unit, currency and scale word.

- Do not round a figure, and do not add digits to it. Do not replace a figure with an
  approximation, such as "about 2%" or "over USD 1 trillion".
- Do not convert a figure to another unit, scale or notation. Examples: a fraction to a percentage,
  millions to billions, "$" to "USD", a number with a thousands separator to one without. A
  conversion that needs a rate, such as into another currency, is also a calculation.
- Give the unit, the currency and the scale word that the source states for the value, also when
  the source states them only in the series name, such as "percent change", "US dollar" or
  "billions". You may write "percent" as "%". Do not give a unit that the source does not state.
  When the source states no unit for a value, say so.

A data query result gives its values already in the unit and at the precision that the data
source sets. Give them as the result gives them. Do all this also when the research question, the
plan or a section's description asks to round figures, to give a number of decimals or to convert a
unit.

A comparison is not a change to a figure. Two sources can give the same value at different
precisions, so a comparison may judge two values at the precision of the less precise one. Write
both values as their sources give them.
```

Blind-review part:

```
A figure without its unit, its currency or its scale word is a violation. Ask for the unit, the
currency or the scale word that the source states for the value, its series name included, or,
where the source states none, a sentence saying so. Never propose a unit yourself. Whether a figure
matches its source is not yours to judge, and neither is the number of its digits.
```

`CALCULATION_DEFINITION`, the sentence after the highest-priority sentence:

```
A comparison that produces no new number, such as which value is larger, a rank, or the direction
of a change, is not a calculation and stays allowed. Writing a value in another unit, scale or
notation without a rate, such as a fraction as a percentage, and rounding a value are not
calculations either, but they are not allowed: the rule "Each figure with its source's value, unit
and period" forbids them. A conversion that needs a rate, such as into another currency, is a
calculation.
```

The preparation texts below are the implemented wording, copied from
`src/dial_deep_research/app/preparation/prompts.py` and
`src/dial_deep_research/app/preparation/tools.py`.

`PREP_AGENT_SYSTEM`, the section "Unsupported operations", which comes after Stage 3:

```
Deep Research never calculates, rounds or converts figures. The report gives every figure as its
source gives it. This holds for every request, also when the user insists.

Calculation:
- A figure that needs a calculation is a request for that figure. Examples: a growth rate from two
  levels, a difference between two values, a share, a sum, an average, an elasticity.
- The plan never asks to calculate, compute, derive, estimate or model a figure. A plan step asks
  research to look for a source that states the figure. When no source states it, the step asks
  research to find the figures that it is computed from:
  - When the query names these figures, the step names them. For a growth rate of X, or for an
    elasticity of X to Y, the step names X and Y.
  - When the query names only a measure, such as an index, the step asks for a source that states
    how to compute the measure. The step also asks for the figures that this source names.
  Example plan step: "Look for a stated elasticity of import growth to GDP growth. If no source
  states one, find the import growth and GDP growth series for the same years."
- A comparison is not a calculation. The plan asks research to find each value, not their
  difference.
- When the user gives an instruction to calculate a figure, omit the instruction from the query
  and the plan. Keep the figure.
- Do not ask the user how to compute a figure.

Rounding:
- When the user gives an instruction to round a figure, omit the instruction from the query and
  the plan.
- The plan does not mention the precision of figures.

Conversion:
- When the user gives an instruction to convert a figure, keep the target unit as the unit of the
  figure, in the query and in every plan step that looks for the figure.

The note:
- When the user gives an instruction to calculate, round or convert a figure, tell the user in one
  sentence, the note, that Deep Research does not do the requested operations, and what the report
  gives instead.
- Never promise or offer an operation.
- A request for a figure with no such instruction needs no note, also when the figure needs a
  calculation or has a unit.
- Write the note once in a reply. When the reply presents the block that `update_plan` returns,
  write the note directly before the block.

Examples:
- "What was the inflation in Canada in 2023, rounded to one decimal?"
  Note: "Deep Research does not round figures: the report gives each figure at the precision of
  its source."
  Query: "What was the inflation in Canada in 2023?"
- "What were the exports of Brazil in 2022, converted to US dollars?"
  Note: "Deep Research does not convert figures: the report gives each figure in the unit of its
  source."
  Query: "What were the exports of Brazil in 2022 in US dollars?"
- "What was the average inflation in Canada over 2010–2020? Compute it from the annual values."
  Note: "Deep Research does not calculate figures: if no source states the figure, the report
  gives the figures it is computed from."
  Query: "What was the average inflation in Canada over 2010–2020?"
- "What was the government debt of Italy as a share of GDP in 2023?"
  Note: none.
  Query: "What was the government debt of Italy as a share of GDP in 2023?"
```

`PREP_AGENT_SYSTEM`, Stage 3, the sentence on when to call `approve_plan`:

```
Call `approve_plan` only when the message clearly approves the plan and asks for no change to the
query or the plan.
```

`PREP_AGENT_SYSTEM`, Stage 1, the exception to the sentence that keeps the formatting requests,
and the rule on named periods:

```
Keep the user's formatting requests in it, such as a unit: the report is written from this
query, and a request left out of it is lost. Add no formatting request of your own.
Exception: a request to calculate, round or convert a figure. Follow the section "Unsupported
operations".
...
- A period named by an event or an era, such as a war or a presidency, gets its
  years in parentheses after the name. Write the years wherever the query or the
  plan names that period.
  - A period with a start and an end gets both years. Example: "during the Second
    World War" becomes "during the Second World War (1939–1945)".
  - A period that starts at an event and has not ended gets only the start year.
    Example: "since the fall of the Berlin Wall" becomes "since the fall of the
    Berlin Wall (1989)".
  - An open end that names no event stays as the user wrote it. Examples: "until
    now", "from 2020". Add no date to it.
```

`PREP_AGENT_SYSTEM`, Stage 2, the rules on details and on plan steps:

```
- The restated query and the plan keep what the user asked for. Do not distort it:
  - do not add a detail that the user did not state. Example: when the user asks to compare two
    forecasts, do not add "in the same publication";
  - do not drop a detail that the user stated, in the query or in a plan step. Exception: a
    request to calculate, round or convert a figure. Follow the section "Unsupported operations".
- When the user asks to compare two values, do not assume that they come from one source. Exception:
  the user says that they come from one source.
- A plan step names where to look, as the rules on data sources below say. This is not an added
  detail.
- A plan step names a data source by its name. It does not name a series, an indicator or a value
  from the description of a data source: research chooses them. A plan step writes the requested
  figure in the words of the query. Example: for "the real exports of Japan", write "real
  exports", also when a dataset lists a series named "Exports".
```

`PREP_AGENT_SYSTEM`, the section "Data sources available to research", the sentences on the
descriptions:

```
Use the descriptions as a topic map — hints on where to find relevant information.
They show examples, not everything a source holds. Use them only to choose the sources to search.
Do not match the request to the series, units or values that they list: research does that.
```

`QUERY_REVIEW_SYSTEM`, the cases in which the query check asks for the time period:

```
Ask about the time period in each of these cases:
- The query names no time period and no event or era. Words such as "outlook",
  "overview", "trends" or "current state" do not name a time period.
- A bare "latest", "recent" or "lately" has nothing else to anchor it.
- The query names an event or era that you do not recognize.
```

`QUERY_REVIEW_SYSTEM`, the questions that the query check does not ask:

```
A figure that needs a calculation, and a figure in a unit or a currency that the user names, are
clear subjects. Do not ask how to calculate or convert a figure, such as a formula or an exchange
rate. Do not ask which figure or unit to report instead.
```

The `update_query` tool's description, its second paragraph: "Call this first with a faithful
restatement of the user's request. For a request to calculate, round or convert a figure, follow
the section "Unsupported operations" of your instructions. Call this again with a refined query
after the user answers clarifying questions."

`PLAN_RECORDED`, the `update_plan` tool's response:

```
Plan successfully updated. Present this block to the user VERBATIM, with no changes to the labels,
wording, order, or numbering:

**Research query:** {query}

**Plan:**
{plan}

Then ask whether they approve the plan or want changes. Do not write again a sentence that you
already wrote in this turn, such as the note about the operations that Deep Research does not do.
```

## Work outside this repository

Listed so that the change is complete; none of it is done in this repository.

- **Channel configuration.** A client rule that tells the writer to convert or round values, where
  a channel has one, is removed from the channel's application properties, which are then
  regenerated.
- **Output-quality policies.** The faithful-relay policy's rule 4, its definition of a calculation,
  any client rule entry that converts values, and the requirement entry behind rule 4 are updated,
  with the deviation from the requirement's original wording recorded.
- **Eval.** The eval needs to cover this behaviour.
- **Deployment order.** On each environment, the StatGPT release with PRs #799 and #804, and the
  dataset configurations that set `decimalPlaces` and `fractionToPercent`, are live before this
  change is deployed, and any client rule that converts or rounds is removed in the same deployment. Otherwise
  the reports show fractions and long decimals again.

## No changes required

- `RESEARCH_AGENT_SYSTEM_PROMPT` and the research review prompt: they say nothing about units,
  notation or rounding, and research takes the values as the tools return them.
- `src/dial_deep_research/app/research/source_selection.py`: its "Unit" term says that a scale word
  is notation, not a different unit. That decides whether a value matches the requested fact, not
  how the report writes it, so it stays true.
- `_CLIENT_RULES_BLOCK`, `_CLIENT_WRITER_RULES_CONTEXT` and the `client_rules` field description in
  `app_properties.py`: the client-rule precedence does not change (Decision 6).
- The clarity check of `update_query`, apart from its time-period rules (Decision 5b) and its
  three sentences on calculated and converted figures (Decision 5f).
- `docs/architecture.md`: no node, edge, state field or turn boundary changes.
- The README, `app_properties.py`, `dial_conf/core/applications-template.json` and
  `docs/generated-app-schema.json`: no setting or application property changes.
- The citation and References code (`citations.py`, `references.py`): it handles markers, not
  figures.

## Risks / Trade-offs

- **[Risk] A fraction series that the data layer does not convert, named with a percentage, reads as
  a percentage** — for example a stored `0.031` under a name "…, percent" becomes "0.031%", wrong by
  a factor of 100. → Mitigation: the owner's assumption that StatGPT converts every such series;
  each dataset's `fractionToPercent` configuration; the deployment order above.
- **[Risk] Unconfigured datasets show raw values.** A channel whose datasets set no `decimalPlaces`
  shows values such as `2.156555`. → Mitigation: the dataset configuration in StatGPT.
- **[Risk] A client rule that asks to convert or round would win over rule 4**, because client rules
  keep their precedence (Decision 6). → Mitigation: such a rule is removed from the channel
  configuration, and the output-quality policy records that a client rule must not ask for it.
- **Mixed notation in one report.** A dataset value `3.512%` next to a publication's `3.5%`, or a
  publication's `USD 1.2 trillion` next to another's `USD 950 billion`, is harder to compare at a
  glance. Accepted: each value carries its own unit and scale, and the risk of a wrong number
  outweighs the readability cost.
- **The model may still round out of habit.** The rule names the changes it must not make, and the
  grounded review judges the value against the transcript. The eval needs to cover this behaviour.
- **[Risk] A dataset tool other than the data query tool returns stored values.** Deep Research
  offers every tool of a server when the server sets no `tools_to_include`
  (`src/dial_deep_research/app/mcp_tools.py`), and a server can expose a tool meant for a UI that
  returns the raw values, unconverted and unrounded. Rule 4 would relay them as given. → Mitigation:
  a channel's `tools_to_include` lists only the tools meant for the model.
- **[Accepted] A cited data query opens values that differ from the report's figure.** The data
  explorer link and the attachments keep the stored values at full precision, so a reader who opens
  the citation can see the stored fraction where the report gives a percentage. This is the data
  layer's design and outside this change.
