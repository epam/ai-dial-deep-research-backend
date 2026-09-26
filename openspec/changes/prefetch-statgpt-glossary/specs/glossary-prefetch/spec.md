## Purpose

Puts a channel's whole glossary into the context of the model calls that plan the research, run it
and write the report, so the report can use the glossary's terminology. The app fetches the
glossary once per turn from the channel's StatGPT MCP server, with retries, and renders it as one
string.

## ADDED Requirements

### Requirement: The glossary is fetched once per turn from the server that configures it

When a channel's `statgpt` MCP server configures a `glossary` (see **application-config-schema**),
the app SHALL fetch the glossary once per turn, before the preparation agent's first model call,
and SHALL use that one result for every model call of the turn, research included. A turn of the
playground deployment SHALL fetch the glossary once, before the playground agent's first model
call, under the same rules.

A channel whose servers configure no `glossary` SHALL make no glossary call, and its prompts SHALL
carry no glossary.

The fetch SHALL call the two tools the configuration names — the list-terms tool and the
term-definitions tool — by those names. It SHALL NOT first fetch the server's tool list: the names
come from the configuration, and a name the server does not advertise surfaces as a failed call,
which the retry rules below already handle. The server's `tools_to_include` filter SHALL NOT
affect the fetch, because the filter states which tools a model is offered, and the fetch is made
by the app.

The fetch SHALL use an MCP client constructed for the turn, with the same connection and
credentials as the turn's other MCP traffic to that server (see **dial-agent-with-mcp**), and each
tool call SHALL run in an MCP session of its own, so a failure that ends one session cannot fail
another call.

Every call SHALL be bounded by a fixed deadline. A call that has not returned by its deadline
SHALL count as a failed call. The bound is needed because the MCP transport's read timeout does not
end a call, and without it one call that never returns would hold the turn before preparation
starts.

The fetched glossary SHALL NOT be persisted to the turn state. It lives for the turn only, and the
next turn fetches it again.

#### Scenario: One fetch serves the whole turn

- **WHEN** a turn on a channel with a glossary runs preparation and then research
- **THEN** the list-terms tool SHALL be called in one fetch before the preparation agent's first
  model call, and the research calls SHALL receive the glossary that fetch produced, with no second
  fetch

#### Scenario: A channel without a glossary makes no glossary call

- **WHEN** a turn runs on a channel whose `statgpt` server sets no `glossary`
- **THEN** no list-terms or term-definitions call SHALL be made, and no prompt SHALL carry a
  glossary

#### Scenario: The tool filter does not stop the fetch

- **WHEN** the server's `tools_to_include` names neither glossary tool
- **THEN** the app SHALL still fetch the glossary, and neither glossary tool SHALL be offered to a
  model

#### Scenario: A call that never returns is cut off

- **WHEN** a term-definitions call receives no response
- **THEN** the call SHALL count as failed once its deadline passes, and its terms SHALL be
  re-requested in the next round

### Requirement: The list of terms is requested with at most three attempts

The app SHALL call the list-terms tool with no arguments, and SHALL make at most **three
attempts** in total. An attempt SHALL count as failed when the call raises, when the result is
marked as an MCP error, when it does not return by its deadline, or when its structured content
does not carry a `terms` array of records with a `term` string. Any failed attempt SHALL be
retried while attempts remain, whatever the kind of failure. The attempts SHALL be separated by a
growing delay with jitter, on the order of one second before the second attempt and two seconds
before the third.

When all three attempts fail, the glossary result SHALL be the failure text described in **The
glossary is rendered as one string**, no term-definitions call SHALL be made, and the turn SHALL
continue.

A list with no terms SHALL be a successful result: no term-definitions call SHALL be made, and the
glossary SHALL render as an empty array.

A cancelled turn SHALL NOT be retried or converted into the failure text: cancellation SHALL
propagate.

#### Scenario: A transient failure is retried

- **WHEN** the first list-terms attempt fails with HTTP 502 and the second succeeds
- **THEN** the app SHALL use the second attempt's list, and SHALL make no third attempt

#### Scenario: Three failures give the failure text

- **WHEN** all three list-terms attempts fail
- **THEN** the glossary result SHALL be the failure text, no term-definitions call SHALL be made,
  and the turn SHALL continue to the preparation agent

### Requirement: Definitions are requested in concurrent batches, in at most three rounds

After the list succeeds, the app SHALL request the definition of every listed term through the
term-definitions tool, whose argument is `{"terms": [<term name>, ...]}`.

- **Batches.** A round SHALL split the terms it requests into batches of at most
  `max_terms_per_definitions_call` names, and SHALL send all of that round's batches concurrently.
  The app SHALL never send a batch larger than the limit, because the server rejects such a call
  whole and fetches nothing for it.
- **Rounds.** The app SHALL run at most **three rounds**. The first round requests every listed
  term. Each later round requests every term that did not resolve in the round before, split into
  new batches, and runs only when at least one such term exists. Later rounds SHALL be separated
  from the round before by a growing delay with jitter, on the order of one second before the
  second round and two seconds before the third.
- **What resolves a term.** A batch call counts as failed under the same conditions as a list-terms
  attempt, with `definitions` in place of `terms`. A term resolves when a successful call's
  `definitions` carries a record whose `term` equals the listed name after surrounding whitespace
  is trimmed from both and both are case-folded. A term does not resolve when its batch call failed,
  when the call reports it under `notFound`, or when the call's answer names it nowhere. A record
  that matches no term the batch requested SHALL be ignored.
- **After the last round**, a term that did not resolve SHALL stay in the glossary without a
  definition.

#### Scenario: A glossary larger than the limit is split into batches

- **WHEN** the list has 25 terms and the limit is 10
- **THEN** the first round SHALL send three concurrent calls, requesting 10, 10 and 5 terms

#### Scenario: Only the unresolved terms are re-requested

- **WHEN** in the first round one batch of 10 fails and the other batches resolve every term they
  requested
- **THEN** the second round SHALL request exactly those 10 terms, and a third round SHALL run only
  if some of them still do not resolve

#### Scenario: A term reported as not found is re-requested

- **WHEN** a successful batch call reports one requested term under `notFound`
- **THEN** that term SHALL be requested again in the next round, while rounds remain

#### Scenario: A term still unresolved after three rounds stays listed

- **WHEN** a term does not resolve in any of the three rounds
- **THEN** it SHALL appear in the glossary without a definition, and no fourth round SHALL run

### Requirement: The glossary is rendered as one string

The glossary result SHALL be one string: the line `Glossary terms:`, a newline, and a JSON array.
The array SHALL carry one object per listed term, in the order the list-terms tool returned them.
Each object SHALL start with an `index` field, an integer counting from 1 in that order, followed
by:

- for a resolved term, every field of its record in the term-definitions answer, in the order the
  answer gives them;
- for an unresolved term, every field of its record in the list-terms answer, with a `definition`
  field set to `null` directly after `term`.

Characters outside ASCII SHALL be written as themselves rather than as `\u` escapes, because
glossary terms carry typographic quotes and dashes, and an escape costs tokens and reads worse.

When the list-terms tool failed three times, the string SHALL be the line `Glossary terms:`, a
newline, and the text `failed to obtain list of terms`.

The rendered objects exist only inside this string, which is never persisted as a list, so the
`index` field cannot be re-slotted by the DIAL SDK's chunk merge.

#### Scenario: Resolved and unresolved terms side by side

- **WHEN** the list returns `Primary Commodity Prices` and `World Economic Outlook` in that order,
  and only the second resolves
- **THEN** the string SHALL be `Glossary terms:` followed by a newline and an array whose first
  object is `{"index": 1, "term": "Primary Commodity Prices", "definition": null}` and whose second
  object starts with `"index": 2` and carries the definition record's fields

#### Scenario: A failed list gives the failure text

- **WHEN** all three list-terms attempts fail
- **THEN** the string SHALL be `Glossary terms:` followed by a newline and
  `failed to obtain list of terms`

### Requirement: The glossary reaches the calls that plan, research and write

The **data-sources string** of a turn SHALL be the instance's `prompts.data_sources_descriptions`,
followed, when the channel configures a glossary, by a blank line and the rendered glossary
string. On a channel without a glossary it SHALL be `prompts.data_sources_descriptions` unchanged.

The data-sources string SHALL be what every model call receives in place of
`prompts.data_sources_descriptions`: the preparation agent and the query clarity check (see
**clarification-and-plan-alignment**), and the playground agent. It SHALL also be what every call
of the research graph receives — research-agent, research-review, the report writer and
report-review (see **research-execution**).

The plan approval check SHALL receive neither the data-sources string nor the glossary: it judges
whether the user approved the recorded plan, which neither bears on.

**The playground agent.** Its system prompt SHALL carry the data-sources string where it carries
`data_sources_descriptions`. Its other inputs are unchanged.

#### Scenario: The combined string reaches the preparation agent

- **WHEN** a turn runs on a channel with a glossary that listed terms
- **THEN** the preparation agent's system prompt SHALL carry the instance's
  `data_sources_descriptions` followed by a blank line and the rendered glossary string

#### Scenario: A failed fetch still reaches the prompts

- **WHEN** all three list-terms attempts failed
- **THEN** the preparation agent, the query clarity check, the playground agent and every call of
  the research graph SHALL receive the data-sources string ending in the failure text, and the
  report reviewer SHALL NOT be given the glossary-terminology check

### Requirement: An agent that can request definitions is told to request the missing ones

The system prompt of the research agent and of the playground agent SHALL carry an instruction to
call the term-definitions tool for any glossary term that has no definition and whose name looks
relevant to the task. The instruction SHALL name the tool as the agent is offered it.

The instruction SHALL appear only when both hold: the glossary's list-terms call returned at least
one term, and the term-definitions tool is among the tools bound to that agent. No other model
call SHALL carry it. Every other call sees an unresolved term only as a `null` definition.

#### Scenario: The tool is bound

- **WHEN** a research turn runs on a channel whose glossary listed terms, and the research agent's
  tools include the term-definitions tool
- **THEN** the research agent's system prompt SHALL carry the instruction, naming that tool

#### Scenario: The tool is filtered out

- **WHEN** the server's `tools_to_include` omits the term-definitions tool
- **THEN** neither the research agent's nor the playground agent's system prompt SHALL carry the
  instruction, and the glossary SHALL still reach them

### Requirement: A glossary fetch never fails the turn

No failure of the glossary fetch SHALL fail the turn. A failed list SHALL become the failure text,
and a term that did not resolve SHALL stay listed without a definition. The only exception is
cancellation, which SHALL propagate.

#### Scenario: The server is unreachable

- **WHEN** every glossary call fails because the server cannot be reached
- **THEN** the turn SHALL continue to the preparation agent with the failure text in its
  data-sources string, and no error SHALL be delivered to the user for the glossary

### Requirement: The glossary fetch is recorded in the logs

Every glossary fetch SHALL log one INFO event when it ends, carrying the server name, the number of
list-terms attempts made, the number of listed terms, the number of resolved terms, the number of
unresolved terms, the number of definition rounds run, and the fetch's duration. When the list
failed, the event SHALL carry the listed count as absent rather than as zero, so a failed list is
not read as an empty glossary.

The app SHALL log one WARNING when the list-terms tool failed three times, naming the server and
the kind of the last failure. It SHALL log one WARNING after the last round when at least one term
did not resolve, naming the server and the number of unresolved terms. Neither is an ERROR, because
the turn continues (see **logging-policy**).

These records follow the **logging-policy** content allowlist: names, counts, durations and failure
kinds. They SHALL NOT carry a term name, a definition, a tool's arguments, a tool's answer, or a
failure's own text, because term names and definitions are the client's content.

#### Scenario: A complete fetch

- **WHEN** a fetch lists 25 terms and resolves all of them in the first round
- **THEN** one INFO event SHALL state one list attempt, 25 listed, 25 resolved, 0 unresolved, one
  round and the duration, and no WARNING SHALL be logged

#### Scenario: Unresolved terms are counted, not named

- **WHEN** two terms do not resolve after three rounds
- **THEN** one WARNING SHALL state the server name and the number 2, and no log record SHALL carry
  either term's name
