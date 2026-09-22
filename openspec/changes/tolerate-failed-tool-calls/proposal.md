## Why

One failing MCP tool call ends the whole research turn, discarding every completed iteration and
every sibling tool result. On 2026-09-21 a single TCP connection reset between DIAL Core and an
MCP server produced one HTTP 502, which ended a turn after 367 seconds and four completed research
iterations; the two sibling tool calls were never cancelled and finished on the server with nobody
left to receive them; and the user got a bare failure message in place of a report, for a blip
that the next connection, 16 milliseconds later, did not hit.

The agent has no way to react to a failed tool because the failure never reaches it. Every
transport failure escapes as an exception instead of arriving as a tool result, so the model can
neither retry the call nor route around a dead tool — decisions only it can make, since choosing a
different source is a research decision. This is GitHub issue #53, filed for a connect timeout and
now with a second, independently triggered instance.

## What Changes

- A failed tool call reaches the agent as an error `ToolMessage` instead of ending the turn. The
  agent then decides whether to try again, use a different tool, or proceed without that evidence.
- Two in-process retries precede that, for the narrow class of failures a fresh attempt fixes,
  on a growing backoff of about a second and then two. A retry costs one more invocation of the
  tool and no tokens; handing the same decision to the model costs a full agent round-trip, which
  in the recorded incident was 52,455 input tokens and 4.7 seconds. The transport's own timeouts
  are set at the same time, since the budget multiplies them and the defaults are chosen for a
  single attempt.
- Rate limiting is deliberately **not** retried in process — the retries span about three seconds
  against a `Retry-After` of seconds to minutes, and each attempt on a refusing limiter can burn
  quota. It reaches the agent instead, marked as worth returning to later, so the agent gathers
  other evidence first and comes back — reordering its work being the only way an agent that
  cannot sleep can let a limit clear. When nothing else is left to gather it may simply call the
  tool again, which still lands a model round-trip after the rejection.
- Failures wrapped by a concurrency runtime's exception group are unwrapped before anything
  classifies them. The MCP client runs its request inside a task group, so what escapes today is a
  wrapper that matches no exception type and whose message names no cause. The same unwrap
  corrects turn-level classification, which recorded the incident's 502 as non-retryable and
  resolved it to the generic unknown-failure message rather than the retryable service one. That
  misclassification is carried in the turn's single error log record and in the `code` and `type`
  propagated to whatever called the app. The reader is shown a failure either way: where this app
  runs behind another that calls it as a tool, that caller appends its own fixed text to the
  choice, identical for every Deep Research failure. So the reader sees a message but never one
  that varies with the classification, which is why a month of wrong classifications went
  unnoticed.
- The error message relayed to the agent is constructed rather than copied: the tool name, the
  exception class, the HTTP status where there is one, and a verdict on retrying — one of three,
  since retrying now, retrying after other work, and not retrying at all call for different next
  actions. The raw exception text is never relayed, because it carries the internal endpoint and
  deployment identifier of the service that failed.
- The app stops overriding the MCP adapter's own tool-error handler. The adapter already converts
  an MCP `isError` result into an error result and preserves its content blocks; the override
  replaces that with text only, silently dropping image or file content from a failed tool.
- Four prompts are told how to behave when a tool failed, each differently: the researcher can
  retry, the reviewer plans the next iteration, the report writer states the resulting gap in the
  evidence, and the report reviewer gains the rule that keeps that gap from naming the tool.
- An integration test harness exercises the real path end to end against an in-process MCP server,
  because none of this behaviour is covered today and its failure mode is silence rather than a
  crash: a wrongly shaped retry predicate removes the retry without failing anything.

## Capabilities

### New Capabilities

- `tool-call-fault-tolerance`: what happens when a tool call fails — which failures are retried in
  process and which are not, how a failure that is not retried reaches the agent, what the relayed
  message may and may not contain, and how a failure wrapped by a concurrency runtime is unwrapped
  before any of that is decided.

### Modified Capabilities

- `dial-agent-with-mcp`: the **Failures delivered as DIAL protocol errors** requirement enumerates
  the exception shapes its normalization supports. A failure arriving inside a task-group wrapper
  matches none of them and resolves to the generic non-retryable fallback, which is what produced
  the wrong classification in the incident. Normalization must reach the wrapped failure.
- `research-execution`: the researcher's and the reviewer's behaviour when a tool call fails is
  currently unspecified. The researcher gets one action per verdict — retry now, do other work and
  come back, or use another source — under a stated retry allowance; the reviewer treats evidence
  missing because a tool failed as a gap it may plan work against.
- `report-composition`: the **Reports carry no meta-annotations about the research process**
  requirement bans stating the tool calls a run took, while the report must still be able to say
  that something could not be established. The boundary needs stating: an unavailable source is
  reported as a gap in the evidence, never as a tool failure or a count of attempts.

## Impact

Code:

- `src/dial_deep_research/app/mcp_tools.py` — remove `enable_tool_error_handling` and its call
  site, the explicit clearing of the handler on the application-called tool staying; and set the
  transport's own `timeout` and `sse_read_timeout` on each connection in `build_mcp_client`,
  which today inherits the adapter's 30 s and 300 s defaults.
- `src/dial_deep_research/app/error_resolution.py` — unwrap before normalization.
- `src/dial_deep_research/app/research/nodes.py` — the research-agent middleware list.
- `src/dial_deep_research/app/playground/agent.py` — the playground middleware list.
- `src/dial_deep_research/app/research/prompts.py` — four prompts: research-agent,
  research-review, the report node, and `REPORT_REVIEW_SYSTEM_PROMPT`, whose closed checklist is
  what would otherwise leave the report's new boundary unenforced.
- A new module for the `ToolRetryMiddleware` subclass that composes the relayed message and emits
  the retry and failure log records — the prebuilt's `on_failure` hook cannot do either.
- The retry predicate and the unwrap helper; `error_resolution.py` owns classification already and
  is the design's choice for both.

Tests:

- A new integration harness with an in-process MCP server and a scripted model.
- `tests/test_mcp_client.py` — two assertions pin the behaviour this change removes and will fail:
  `handle_tool_error` on the agent tools (line 246) and on the dataset-metadata tool (line 326).
  Both need rewriting to assert the adapter's own handler is left in place instead.
- `tests/test_error_resolution.py` gains the wrapped-failure cases.

Docs:

- `docs/architecture.md` — required, not conditional: this change alters what ends a turn, which
  the project's own rule says must be updated in the same change. The page already claims at
  lines 378-380 that "A tool *error* does not end an iteration", which is false today for
  transport failures and becomes true only with this change.

Dependencies: none. The middleware this change uses is present in the installed `langchain`
1.3.12; no upgrade is required and none is proposed here.

The preparation agent is **not** affected. It binds no MCP tools, so no transport failure can
reach it, and issue #53's claim that the exposure extends to it does not hold.
