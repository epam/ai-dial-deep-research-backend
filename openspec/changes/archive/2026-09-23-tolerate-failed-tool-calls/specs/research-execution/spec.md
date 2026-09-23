## ADDED Requirements

### Requirement: Research-agent and research-review act on a failed tool call

A tool call that fails reaches research-agent as an error result rather than ending the turn, per
the **tool-call-fault-tolerance** capability. Both nodes that see those results SHALL be told what
to do with them, because the behaviour of a model that is handed a failure without instruction is
unspecified and varies between runs.

**Research-agent.** Its prompt SHALL state that a tool call may fail and that the failed result
carries a verdict on retrying, and SHALL give it one action per verdict, matching the three the
**tool-call-fault-tolerance** capability defines:

- *Retrying may help* — research-agent MAY call the same tool again.
- *Retry later* (the tool is rate limited) — research-agent SHALL prefer to move on to other work
  in the same iteration and return to the tool afterwards if the evidence is still wanted, because
  reordering its work is the only way it can let a rate limit clear. Where no other work is
  outstanding it MAY call the tool again directly; even that repeat lands a model round-trip after
  the rejection, and stranding the agent would abandon the evidence rather than delay it.
- *Retrying will not help* — research-agent SHALL NOT call that tool again for the same evidence;
  it SHALL seek it from another tool, or proceed without it.

A failed result that carries no verdict is the tool's or its server's own error message.
Research-agent SHALL correct its arguments and call again, within the allowance, when the message
names a mistake in them, and SHALL otherwise treat it as *retrying will not help*. A result the
image budget substituted is not a failed call: it follows the **image-budget** capability and does
not count against the allowance.

The prompt SHALL state the retry allowance as a specific number rather than leaving it to the
model's judgement, because an unstated allowance produces a different number of attempts on every
run and cannot be tested. That allowance SHALL be **at most two repeat calls to the same failed
tool**, counted across the whole research rather than per iteration: calls made in earlier
iterations count, and a later plan asking for the same evidence does not renew them. Having spent
it, research-agent SHALL move on. Evidence that only a tool research-agent may no longer call could
provide SHALL NOT keep the iteration from ending: the plan item counts as done without it.

The allowance is the agent's alone and SHALL NOT be described to it as the total number of
attempts, because each call the agent makes already carries the retries of **In-process retries
precede the relay** in the **tool-call-fault-tolerance** capability. Three agent-level calls at
three attempts each therefore invoke the tool up to nine times for one piece of evidence in the
whole research.
The agent's retry is worth having despite that duplication because it lands a model round-trip
after the in-process retries gave up — tens of seconds into the failure rather than the three
seconds they cover — which is a different interval over which an outage may clear.

The arithmetic differs for the two other verdicts. A rate-limited call carries no in-process
retries, so each agent-level attempt is **one** invocation and the whole allowance costs three attempts,
spread across the other work research-agent does in between; that spacing is the point of
returning to it rather than repeating it at once. A call marked as not worth retrying costs one
attempt in total, because research-agent is told not to repeat it at all — the allowance is a
ceiling on a model that ignores that instruction, not an expected path.

**Research-review.** Its prompt SHALL state that a result saying a tool failed is not evidence,
and that the evidence it would have given is unavailable, because research-agent has already
retried it as far as its allowance permits. Research-review SHALL NOT plan that evidence again and
SHALL NOT treat a failed tool as coverage; an item whose only missing evidence is unavailable this
way needs no further step. Planning it again would renew research-agent's allowance in every
iteration, multiplying the calls to a failed tool by the iteration cap.

Its prompt SHALL also state that a result the image budget substituted is not a tool failure and
is not evidence. Whether its content is still missing is judged from the rest of the findings, and
what may be fetched again is what the substituted result itself says about the image slots left;
the prompt SHALL NOT restate that message.

Neither node SHALL be told to abandon the iteration because a tool failed.

#### Scenario: Research-agent retries a tool the result says is worth retrying

- **WHEN** research-agent receives an error result stating that retrying may help
- **THEN** it MAY call the same tool again within the same iteration, and the iteration SHALL continue either way

#### Scenario: The retry allowance is spent and research-agent moves on

- **WHEN** research-agent has called the same failed tool twice more after its first failure, counting calls in earlier iterations, and it fails again
- **THEN** research-agent SHALL stop calling that tool for that evidence and SHALL either seek it from another tool or continue without it

#### Scenario: Research-agent defers a rate-limited tool while other work remains

- **WHEN** research-agent receives an error result saying the tool is rate limited, and other evidence in the iteration is still ungathered
- **THEN** it SHALL carry on with that other work before calling the tool again, and SHALL NOT call it again as its next action

#### Scenario: Research-agent retries a rate-limited tool when nothing else remains

- **WHEN** research-agent receives an error result saying the tool is rate limited, and there is no other evidence left to gather in the iteration
- **THEN** it MAY call that tool again as its next action, within its retry allowance, rather than ending the iteration without the evidence

#### Scenario: Research-agent routes around a tool that cannot recover

- **WHEN** research-agent receives an error result stating that retrying now will not help
- **THEN** it SHALL NOT keep calling that tool, and SHALL either seek the evidence from another tool or continue without it

#### Scenario: Research-review does not plan evidence a failed tool left missing

- **WHEN** a plan item is unsupported by the findings because the tool that would have covered it failed
- **THEN** research-review SHALL NOT include that evidence in the next plan, and SHALL NOT judge the item covered by the failed result

#### Scenario: A failed tool does not hold the iteration open

- **WHEN** the only tool that could provide a plan item's evidence has failed and research-agent may no longer call it for that evidence
- **THEN** research-agent SHALL treat that plan item as done without the evidence and SHALL be able to end the iteration with `finish_iteration`

#### Scenario: A failed tool does not end the iteration

- **WHEN** one of several tool calls in an iteration fails and is relayed as an error result
- **THEN** research-agent SHALL continue the iteration and SHALL still end it by calling `finish_iteration`

## MODIFIED Requirements

### Requirement: Researcher investigates with forced tool choice and a finish_iteration sentinel

The research-agent node SHALL be a tool-calling agent over the MCP-loaded tools plus one
sentinel tool, `finish_iteration`. The agent SHALL be run with **forced tool choice**
(every model call issued with `tool_choice="any"`) so that every model step emits a
tool call and the model cannot produce a free-form assistant message (in particular,
it cannot write a summary or a report).

A research-agent iteration SHALL therefore end **only** when research-agent calls
`finish_iteration`. That tool SHALL be declared `return_direct=True`, so the agent
loop returns as soon as it executes, with no further model round-trip. Since the
loop's only other exit is a tool-call-free assistant message, which forced tool choice
makes unreachable, `finish_iteration` is the single exit from a research-agent iteration
and research-agent cannot stop early. `finish_iteration` SHALL be a no-op signal that only
ends the iteration; it SHALL NOT decide whether to review or report. Research-agent's
prompt SHALL contain no report-writing instructions.

A research-agent that never calls `finish_iteration` SHALL be bounded by the step budget
of the **A per-graph-run step budget bounds every graph run** requirement below.

#### Scenario: research-agent cannot emit a free-form report

- **WHEN** the research-agent model is invoked at any step of an iteration
- **THEN** it SHALL be constrained to call a tool (an MCP tool or `finish_iteration`) and SHALL NOT be able to return a free-form assistant message containing a summary or report

#### Scenario: finish_iteration ends the iteration

- **WHEN** research-agent calls `finish_iteration`
- **THEN** the current research-agent iteration SHALL end immediately (no additional model call) and control SHALL pass to research-review

#### Scenario: A tool the server rejects does not abort research

- **WHEN** an MCP server rejects a tool call and reports it in its own result, for example because argument validation refused it
- **THEN** the error SHALL be returned to research-agent as an error `ToolMessage` carrying the server's own content, and surfaced as a stage marked ❌, and research-agent MAY try again within the allowance of **Research-agent and research-review act on a failed tool call** without failing the turn

#### Scenario: A tool that fails before the server answers does not abort research either

- **WHEN** a tool call fails without a result from the server — a transport failure, a gateway error, or an unexpected exception
- **THEN** it SHALL reach research-agent as an error `ToolMessage` too, composed by the app per the **tool-call-fault-tolerance** capability rather than by the tool adapter, and the turn SHALL NOT abort
