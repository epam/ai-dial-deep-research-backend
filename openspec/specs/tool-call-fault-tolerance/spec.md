# tool-call-fault-tolerance Specification

## Purpose

What happens when a tool call fails: which failures are retried in process before the agent ever
sees them, how every other failure is delivered to the agent as a result it can act on rather than
as an exception that ends the turn, and what the delivered message may and may not say.

## Requirements

### Requirement: A failing tool call is delivered to the agent, not raised to the turn

A tool call that fails SHALL produce a tool result marked as an error and SHALL NOT abort the turn.
This holds for every failure a tool call can produce — the tool server reporting an error, a
transport failure reaching it, a protocol-level error, or an unexpected exception in the tool
itself — and it holds however that failure is shaped, including when a concurrency runtime wraps it.

The agent SHALL then decide what to do: call the same tool again, call a different one, or continue
without that evidence. Choosing a different source is a research decision, so it belongs to the
agent and SHALL NOT be made on its behalf by absorbing the failure silently or by ending the turn.

This applies to every agent that can call a tool loaded from an MCP server. The preparation agent
is out of scope because it binds no such tools; a change that gives it any SHALL bring it in scope.

Sibling tool calls issued in the same step SHALL be unaffected: their results SHALL reach the agent
alongside the failed one, rather than being discarded because a peer failed.

#### Scenario: One tool call in a parallel batch fails

- **WHEN** the agent issues three tool calls in one step and one of them fails with a transport error that retrying does not fix
- **THEN** the agent SHALL receive three tool results — two successful and one marked as an error — and the turn SHALL continue

#### Scenario: Every research iteration completed so far survives a tool failure

- **WHEN** a tool call fails during a later research iteration, after earlier iterations have gathered findings
- **THEN** the turn SHALL NOT be delivered as a protocol error, and the findings gathered before the failure SHALL remain available to the rest of the run

#### Scenario: A tool that keeps failing does not trap the run

- **WHEN** a tool fails on every call the agent makes to it during a turn
- **THEN** each failure SHALL be delivered as an error result, and the run SHALL still reach a report or a stated inability to answer rather than aborting

### Requirement: In-process retries precede the relay, for failures a fresh attempt can fix

Before a failure is relayed to the agent, the app SHALL retry the tool call, and only when the
failure is one that a fresh attempt can plausibly fix. The budget SHALL be **two retries — three
attempts in total** for one call the agent made. An attempt is one invocation of the tool, not
one HTTP request: each invocation opens its own session, so it costs several requests. Retrying
here is worthwhile even so, because those requests carry no tokens, whereas relaying the same
decision to the agent costs a full model round-trip over the whole accumulated context.

The retries SHALL be separated by a growing delay with jitter, on the order of a second before the
first and two seconds before the second. The delay is what makes the second retry worth having:
the first retry's value is a fresh connection, which is immediate, but two attempts microseconds
apart test the same conditions twice.

A failure is not always immediate, so the budget SHALL bound the waiting inside the attempts as
well as between them. The app SHALL set the tool transport's own timeouts rather than inheriting
the client library's defaults, because those defaults are chosen for a single attempt and this
requirement multiplies them. Connecting and writing SHALL be bounded at a few seconds, since a
reachable server answers immediately and only an unreachable one waits; reading the response SHALL
keep a much longer bound, because a tool doing real work legitimately takes tens of seconds to
answer and cutting it off would fail calls that were going to succeed.

A failure SHALL be retried when it is a transport-level failure — a connection that could not be
established, timed out while connecting, was reset, or died mid-response — or when it carries HTTP
status 502 or 503, where a gateway could not reach the service behind it. Every other failure SHALL
be relayed without a retry, including any other HTTP status and any error the tool server itself
reports.

A read timeout — nothing received from the server for the whole of the read bound — SHALL NOT be
retried, and SHALL be relayed with the verdict that retrying will not help. A working tool server
keeps its response alive while the tool runs, so a read timeout marks a path that is stuck rather
than a tool that is slow, and every repeat would wait out the whole bound again.

A failure excluded from the in-process retry because an *immediate* repeat cannot help it — a
server error such as 500 or 504 — SHALL nonetheless be relayed with the retry-later verdict rather
than the will-not-help one. The reasoning that keeps it out of a retry three seconds later is the
same reasoning that makes one tens of seconds later worth attempting.

When a failure carries several underlying causes at once, it SHALL be retried only if **every** one
of them is retryable. A retry re-runs the whole call, so one permanent cause among several makes
the retry pointless.

#### Scenario: An unreachable tool fails fast rather than once per default timeout

- **WHEN** the tool server cannot be reached at all and the call exhausts its attempts
- **THEN** the time spent SHALL be bounded by the app's own connect timeout on each attempt, not by the transport library's default, so an unreachable tool costs the turn seconds rather than minutes

#### Scenario: A slow but working tool is not cut off

- **WHEN** a tool connects immediately and then takes tens of seconds to produce its answer
- **THEN** the call SHALL succeed, because the bound on reading a response is much longer than the bound on establishing the connection

#### Scenario: A stale connection is retried and succeeds

- **WHEN** a tool call fails because the connection to the tool server was reset, and the retried call succeeds
- **THEN** the agent SHALL receive the successful result and SHALL NOT be told that anything failed

#### Scenario: A gateway error exhausts the retries and is then relayed

- **WHEN** a tool call fails with HTTP 502 and both retries fail the same way
- **THEN** the app SHALL invoke the tool three times for that call — no more — and SHALL relay the last failure to the agent as an error result

#### Scenario: A rejected request is relayed without a retry

- **WHEN** a tool call fails with an HTTP status that indicates the request itself was rejected, such as 403
- **THEN** the app SHALL call the tool once, SHALL NOT retry it, and SHALL relay the failure immediately

#### Scenario: A read timeout is relayed without a retry

- **WHEN** a tool call fails because nothing arrived from the server for the whole read bound
- **THEN** the app SHALL call the tool once, SHALL NOT retry it, and SHALL relay the failure with the verdict that retrying will not help

#### Scenario: A mixed failure is not retried

- **WHEN** one tool call fails with two causes at once, one retryable and one not
- **THEN** the app SHALL NOT retry it and SHALL relay the failure to the agent

### Requirement: Rate limiting is not retried in process, but the agent may return to it

A tool call rejected for rate limiting — HTTP status 429 — SHALL NOT be retried in process. The
in-process retries span about three seconds while a rate limit's retry-after interval runs from
seconds to minutes, so they would rarely outlast it, and every attempt against a limiter that is
already refusing can consume quota or extend the window it is enforcing.

The failure SHALL instead be relayed to the agent marked as worth retrying **later, not
immediately** — a verdict distinct both from a failure the agent may repeat at once and from one
it should not repeat at all. The agent's own retry lands at least a model round-trip after the
rejection, and later still when it does other work in between, and that is an interval a short
rate limit can clear.

The relayed message SHALL say that the tool is rate limited and that the agent should gather other
evidence first and come back to it afterwards if still needed. Reordering its work is the only
form of waiting available to an agent that cannot sleep.

Where no other work is outstanding, the message SHALL NOT leave the agent with nothing to do. It
SHALL permit calling the tool again directly in that case, because even a direct repeat arrives a
model round-trip after the rejection — seconds, not microseconds — which is the spacing that
mattered. Withholding the retry there would abandon the evidence rather than delay it.

The relayed message SHALL NOT carry the retry-after interval. The agent cannot honour a stated
number of seconds, so naming one would only invite the immediate repeat this requirement exists
to prevent.

#### Scenario: A rate-limited tool call reaches the agent without an in-process retry

- **WHEN** a tool call is rejected with HTTP 429
- **THEN** the app SHALL call the tool once, SHALL NOT retry it in process, and the agent SHALL receive an error result naming the rate limit

#### Scenario: The agent is told to come back rather than to stop

- **WHEN** the agent receives a rate-limit error result
- **THEN** that result SHALL tell it to gather other evidence first and return to this tool afterwards if still needed, and SHALL NOT tell it that the tool cannot be used again

#### Scenario: A rate limit with no other work left does not strand the agent

- **WHEN** the agent receives a rate-limit error result and has no other evidence left to gather in the iteration
- **THEN** the result SHALL leave it free to call the tool again directly, rather than requiring work that does not exist

#### Scenario: The retry-after interval is withheld from the agent

- **WHEN** a rate-limit rejection carries a retry-after interval
- **THEN** that interval SHALL NOT appear in the result the agent receives

### Requirement: A failure wrapped by a concurrency runtime is unwrapped before classification

Work that runs concurrently reports its failures inside a wrapper holding every task that failed,
even when only one did. Such a wrapper matches none of the failure types anything classifies by,
and its own message names no cause, so any decision taken on the wrapper rather than on its
contents is taken blind.

Every classification of a failure — whether it is worth retrying, what it is called, and what the
user or the agent is told — SHALL therefore be made on the failures the wrapper holds, not on the
wrapper. Wrappers nested inside wrappers SHALL be resolved all the way down. This applies to the
turn-level classification of **Failures delivered as DIAL protocol errors** in the
**dial-agent-with-mcp** capability as well as to the tool-level decisions above.

Where a wrapper holds more than one failure, the **first** leaf SHALL supply the status and the
failure kind of the relayed result, and the message and retryable classification at the turn
level. The leaves of one wrapper describe the same dead connection from different tasks, so no
leaf tells a better story than another and a fixed rule beats an arbitrary one. The decisions about
retrying are the exception: the in-process retry and the relayed verdict SHALL weigh every leaf,
because one permanent cause makes any retry pointless.

#### Scenario: A wrapped transport failure is classified by its real cause

- **WHEN** a tool call fails and the failure arrives wrapped in a concurrency runtime's container holding a single HTTP 502
- **THEN** the retry decision and the relayed message SHALL both be based on the 502, exactly as if it had arrived unwrapped

#### Scenario: A wrapped failure that aborts a turn is classified by its real cause

- **WHEN** a wrapped failure does reach the turn-level handler
- **THEN** the user-facing message and the retryable classification SHALL be those of the failure inside the wrapper, not the generic fallback used for an unrecognized failure

### Requirement: A cancelled turn is never converted into a tool result

Cancellation is not a tool failure. When a turn is cancelled while a tool call is in flight, the
cancellation SHALL propagate and SHALL NOT be retried, converted into an error result, or reported
to the agent as a failed tool.

#### Scenario: Cancellation during a tool call propagates

- **WHEN** a turn is cancelled while a tool call is in flight
- **THEN** the cancellation SHALL propagate unchanged, and no error result SHALL be added to the conversation

### Requirement: The relayed failure names its cause and carries no internal detail

This requirement governs the failures **the app relays itself** — those that reached it as an
exception. A failure the tool server reports in its own result is not one of them: the tool
adapter converts it before the app sees it, and it reaches the agent carrying the server's own
content, with no status and no verdict, as **The tool adapter's own error conversion is left in
place** requires. The two paths are deliberately different, because the server's own error text is
written for the model while an exception's is not.

The error result the agent receives SHALL identify the tool that failed, name the kind of failure,
carry the HTTP status where the failure has one, and state a verdict on retrying. The verdict is
what makes the result actionable: without it the agent has to infer transport semantics, and will
repeat failures that cannot succeed while abandoning ones that would.

The verdict SHALL be one of three, because the right next action differs in each case:

| Verdict | When | What the agent does |
| --- | --- | --- |
| Retrying may help | The in-process retries were spent on a transport failure other than a read timeout, or on a 502/503 | Call the tool again if the evidence is still wanted |
| Retry later | The failure may clear, but not within seconds — the tool is rate limited, or returned a server error the in-process retries do not cover | Gather other evidence first, then come back if still needed; call it again directly when nothing else is outstanding |
| Retrying will not help | Any other failure — a rejected request, a read timeout, a permanent error | Use another source or continue without the evidence |

When a failure carries several causes, the verdict SHALL weigh every one of them, as the retry
does: retrying may help only when every cause is one the in-process retries cover, and retry later
only when every cause is one that may clear with time — a transport failure other than a read
timeout, a rate limit, or a server error. Any other mix means retrying will not help.

A two-way verdict is not enough: collapsing "retry later" into "will not help" abandons evidence a
short rate limit would have released, and collapsing it into "may help" sends the agent straight
back at a limiter that is still refusing.

The result SHALL be composed from those parts. It SHALL NOT be the failure's own text, a URL, an
endpoint, a host name, a deployment identifier, or a stack trace. A transport failure's own message
routinely names the internal address of the service that failed, and the conversation the result
joins is both shown to the model and persisted.

#### Scenario: A relayed failure is actionable without being revealing

- **WHEN** a tool call fails with an HTTP error whose own message contains the internal address of the service
- **THEN** the result the agent receives SHALL name the tool, the kind of failure, and the status, and SHALL contain neither that address nor any other endpoint

#### Scenario: The verdict distinguishes all three cases

- **WHEN** one tool call fails with a transport error after its in-process retries, another with a rate-limit rejection, and a third with a rejected request such as 403
- **THEN** the first result SHALL state that retrying may help, the second that the tool is rate limited and should be returned to after other work, and the third that retrying will not help

### Requirement: Tool retries and relayed failures are recorded in the logs

A retried tool call leaves no trace anywhere a reader can see it. It produces one tool result
whatever attempt succeeded, so the conversation records a single call; the persisted turn state is
built from those same messages, so it records a single call too; and the stage the call renders as
is keyed on the tool result, so one stage appears whether the call took one attempt or two. The
only visible effect is that the stage's elapsed time silently includes the retry. A failure the
agent routes around is likewise invisible: the turn completes and produces a report.

The log record is therefore the sole trace of either, and it SHALL exist. Every retried tool call
and every failure relayed to the agent SHALL be logged, carrying the tool name, the kind of
failure, and the attempt count. Without it, a tool server degrading steadily — succeeding only on
retries, or failing into evidence the agent works around — is indistinguishable from one that is
healthy, until it starts breaking turns.

Retries SHALL NOT be surfaced as stages of their own. A retry that succeeds within milliseconds is
not something the reader can act on, and the failed attempt is not a research action; the reader's
view stays one stage per tool call the agent made.

These records follow the **logging-policy** capability: structure only — names, counts, statuses,
outcomes — and never the tool's arguments, the tool's output, or the failure's own text.

#### Scenario: A retry that succeeds is still visible

- **WHEN** a tool call fails, is retried, and the retry succeeds
- **THEN** the logs SHALL carry a record naming the tool and the kind of failure, even though the turn completed normally

#### Scenario: A retried call renders as one stage, not two

- **WHEN** a tool call fails, is retried, and the retry succeeds
- **THEN** the reader SHALL see one stage for that tool call, reporting success, and the conversation and the persisted turn state SHALL each record one tool result

#### Scenario: Log records carry no payloads

- **WHEN** a tool call fails and both the retry and the relay are logged
- **THEN** neither record SHALL contain the tool's arguments, its output, or the failure's own message text

### Requirement: The tool adapter's own error conversion is left in place

The MCP tool adapter already converts a tool result the server marks as an error into an error
result for the agent, preserving the content blocks the server sent — including image and file
content, which a failing tool may legitimately return.

The app SHALL NOT replace that conversion with one that keeps only text. Where the app needs a
failure raised rather than converted — the application-called file-sharing tool of the
**report-citations** capability — it SHALL continue to clear the conversion on that tool
explicitly, as **Tool-calling agent over MCP-loaded tools** requires.

#### Scenario: A failing tool's image content reaches the agent

- **WHEN** an MCP server reports a tool error whose content includes both text and an image
- **THEN** the error result the agent receives SHALL carry both, rather than the text alone
