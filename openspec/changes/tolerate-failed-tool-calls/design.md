## Context

See `proposal.md` — Why, for the motivation and the recorded incident. This section carries only
the mechanics that constrain the approach, all of them read from the installed source rather than
inferred.

**Why a tool failure escapes today.** `BaseTool.arun` (`langchain_core` 1.4.9,
`tools/base.py:1211-1226`) has three `except` branches. `ValidationError` and `ToolException`
consult a flag; `except (Exception, KeyboardInterrupt)` re-raises unconditionally.
`langchain-mcp-adapters` 0.3.0 raises its `ToolException` subclass **only** for
`CallToolResult(isError=True)` — its own docstring says transport and conversion failures are
deliberately not `ToolException` subclasses — so every transport failure lands in the third
branch. `create_agent` builds its `ToolNode` without `handle_tool_errors`
(`langchain/agents/factory.py:1061`), so `_default_handle_tool_errors` applies, which returns a
message only for `ToolInvocationError` and re-raises everything else (`langgraph_prebuilt` 1.1.0,
`tool_node.py:383-391`). With no tool-call middleware configured, `ToolNode._arun_one` calls
`_execute_tool_async` directly with no surrounding `try` (`tool_node.py:1190-1193`), so nothing
catches the re-raise.

**Why sibling results are lost.** `ToolNode._afunc` fans out with `asyncio.gather` and no
`return_exceptions` (`tool_node.py:858`). Probed: `gather` propagates the **chronologically**
first failure — not the first in argument order — and does not cancel its siblings, which run to
completion with their results discarded. That matches the incident exactly, where two sibling
`query_datasets` calls finished on the server 15 and 17 seconds after the turn had died.

**Why the failure arrives wrapped.** The MCP streamable-HTTP client runs its request inside an
anyio task group (`mcp/client/streamable_http.py:647`), which raises one container per failed
task. Probed against a real `httpx.HTTPStatusError`: the concrete type is `ExceptionGroup`,
`isinstance(group, Exception)` is `True` so `except Exception` still catches it,
`isinstance(group, httpx.HTTPStatusError)` is `False`, and `str(group)` is
`"unhandled errors in a TaskGroup (1 sub-exception)"`. Both facts matter — type matching fails
silently, and the message names no cause.

**What the middleware already does.** `ToolRetryMiddleware.awrap_tool_call`
(`langchain/agents/middleware/tool_retry.py:351-411`, installed 1.3.12) catches `Exception`,
re-raises `GraphBubbleUp`, and when `should_retry_exception` returns `False` calls `_handle_failure`
**immediately without retrying**. With `on_failure="continue"` that returns a
`ToolMessage(status="error")`. So one middleware already performs both the retry and the
conversion. `retry_on` accepts a tuple or a callable; `should_retry_exception`
(`middleware/_retry.py:68-84`) does `isinstance(exc, retry_on)` for a tuple.

**Exception hierarchy.** Verified: `httpx.HTTPStatusError` is **not** a subclass of
`httpx.TransportError` — it sits beside `RequestError` under `HTTPError` — while
`TimeoutException`, `NetworkError` and `ProtocolError` all are. A transport-only predicate
therefore misses an HTTP status error even after unwrapping.

## Goals / Non-Goals

**Goals:**

- Put the failure handling **below** `asyncio.gather`, so the batch's other results survive.
- Keep the expensive decision (route around a dead tool) with the agent and the cheap one (retry a
  stale connection) in process.
- One place that unwraps concurrency wrappers, used by both the tool-level and turn-level
  classifiers, so the two cannot drift.
- Lock the behaviour in tests, because every failure mode here is silent rather than loud.

**Non-Goals:**

- **The LangChain / OpenAI dependency upgrade.** `ToolRetryMiddleware` in the installed 1.3.12
  already does the job, so the upgrade buys only a nicer API. Against that: `langchain-openai`
  1.6.3 permits `openai<4.0.0,>=2.45.0`, so a resolve would take openai 3.17.0, whose 3.0.0
  release makes HTTPX2 the default HTTP client. That would silently break
  `TRANSIENT_STREAM_DROP_ERRORS` in `utils/llm.py` and every `httpx` branch in
  `error_resolution.py`, with no harness in place to catch it. Upgrade after this change, not
  before — the sequence is implement, then harness, then upgrade, so the harness is there to
  catch what the upgrade breaks. It is a follow-up rather than a dead end: it unlocks
  `ToolErrorMiddleware` (see decision 1), and it can be taken as a LangChain-only move by pinning
  `openai<3.0.0`, which `langchain-openai` permits.
- **`ToolCallLimitMiddleware`.** Handing the retry decision to the model introduces a loop risk.
  Deferred by the user's call to the existing graph recursion limit and iteration cap, with the
  prompt's bounded retry allowance as the near-term guard.
- **A `try`/`finally` around `_persist`** (`app/completion.py:100`). Not an oversight: the
  **Failures delivered as DIAL protocol errors** requirement states the app SHALL NOT persist
  state on a turn that aborts. Changing it means amending that requirement, which belongs to
  issue #60.
- **Node-level failures** — a failed research-review call or first report draft still end the
  turn. Issues #60 and #62.
- **The preparation agent.** It binds no MCP tools, so no transport failure can reach it.

## Decisions

### 1. One `ToolRetryMiddleware` rather than a retry plus a separate error converter

A **subclass of `ToolRetryMiddleware`** with `max_retries=2` and `retry_on=<callable>`, on the
research-agent and playground graphs — three attempts per agent-level call, on the prebuilt's
default backoff of roughly 1 s before the first retry and 2 s before the second (±25% jitter, per
`calculate_delay` in `middleware/_retry.py`).

**Not `on_failure="continue"`, which was the first draft and is unusable.** Its default formatter
is `f"Tool '{tool_name}' failed after {n} {attempt_word} with {exc_type}: {exc_msg}. Please try
again."` where `exc_msg = str(exc)` (`middleware/tool_retry.py:249-255`). For the recorded incident
that string is the internal cluster endpoint and the deployment id — exactly what decision 6 and
the relay requirement forbid. The leak would not stop at the model either: the runner passes the
`ToolMessage` content into the stage body (`app/research/runner.py:820-826`) and
`_render_output_section` falls back to `str(content)` (`utils/dial_stages.py:277-283`), so the
endpoint would render in the chat UI under an **Error** heading. The same formatter also appends
"Please try again." unconditionally, contradicting the will-not-help verdict.

The callable form of `on_failure` does not fix it alone: `OnFailure = Literal["error", "continue"]
| Callable[[Exception], str]` (`middleware/_retry.py:22`), so the callable never receives the tool
name, and `langchain_openai` strips `ToolMessage.name` before the request anyway. Overriding
`_handle_failure` is the one place `tool_name`, `exc` and `attempts_made` are in scope together
(`tool_retry.py:257-259`), so it composes the message and logs the relayed failure. It cannot log a
retry that succeeds, because such a retry never reaches it. So the subclass also overrides
`wrap_tool_call` and `awrap_tool_call` to wrap the handler before handing it to the parent. The
parent calls that handler once per attempt, so an attempt that starts after a failure is a retry,
and the wrapper logs it there with the failure that caused it. `tool_retry.py` contains no logging
at all, and no other middleware in this project implements `wrap_tool_call`. A subclass inherits
the backoff, the budget and the `GraphBubbleUp` exclusion, so this does not reopen the rejection
of a hand-written middleware below.

**`ToolErrorMiddleware` is the public successor, once the upgrade lands.** Its handler is
`on_error(exc, request) -> str | list[ContentBlock] | None`, so it receives the `ToolCallRequest`
and can name the tool without touching a private method — the documentation presents it for
exactly this sanitising purpose, and returning `None` lets an exception propagate, which would
also let genuine bugs in our own code bubble up instead of being converted. It needs
`langchain>=1.3.14` against our installed 1.3.12, so it is unavailable here; that signature is
read from the documentation rather than from source, unlike every other library claim in this
design.

It would not, however, remove the subclass entirely. The logging requirement asks for the attempt
count, which exists only inside `_handle_failure`; `on_error` has the tool and the failure kind
but not the count, and intermediate retries have no hook in the prebuilt at all. So the upgrade
buys a public, better-scoped message hook and leaves either a thinner log record or this same
subclass beside it.

Taking the defaults rather than tuning them is deliberate. A zero delay was the first draft, when
the budget was a single retry whose only job was a fresh connection; with two retries it is
wasteful, because two attempts microseconds apart test the same conditions twice. About three
seconds for a tool that is simply down is absorbed inside a research step that already takes
longer, and an untuned default is one fewer number to justify and keep current.

- *Rejected: no in-process retry, the agent decides everything.* The agent cannot wait — it has no
  sleep — so its only "retry" is an immediate one, and that costs a full model round-trip: 52,455
  input tokens and 4.7 seconds in the recorded incident, plus a step against the graph budget. The
  middleware does the same thing for one HTTP request.
- *Rejected: `ToolRetryMiddleware(on_failure="error")` plus `ToolErrorMiddleware`,* as issue #53
  proposes. `ToolErrorMiddleware` needs `langchain>=1.3.14` and we run 1.3.12, and the
  `on_failure="continue"` path already returns the error `ToolMessage` for both the
  retries-exhausted and the not-retryable cases. The second middleware would add a dependency bump
  for no behaviour we need.
- *Rejected: LangGraph's node `RetryPolicy`.* It retries only exceptions that **escape** the node,
  and under this design nothing may escape.
- *Rejected: a custom `wrap_tool_call` middleware.* Available in 1.3.12 and it is what the
  LangChain docs show for a catch-all converter, but it would reimplement the backoff, the budget
  and the `GraphBubbleUp` exclusion that the prebuilt already has and tests.

### 1b. The connect timeout is set, because the budget multiplies it

`build_mcp_client` (`app/mcp_tools.py`) passed only `transport`, `url` and `headers`, so the
adapter's defaults applied: `DEFAULT_STREAMABLE_HTTP_TIMEOUT = 30 s` and
`DEFAULT_STREAMABLE_HTTP_SSE_READ_TIMEOUT = 300 s` (`langchain_mcp_adapters/sessions.py:56-57`),
combined as `httpx.Timeout(timeout, read=sse_read_timeout)` (`sessions.py:354`). Nothing in
`settings.py` or `app_properties.py` overrides them. `StreamableHttpConnection` accepts both as
optional keys, so each connection now sets both.

The two bounds measure different things. `timeout` governs connecting and writing, where a
reachable server answers at once. `sse_read_timeout` is the longest silence httpx accepts between
two reads — before the response headers, or between any two chunks of the body after them. It is
not a limit on how long the call takes.

**Connect: 5 s.** A connect timeout is issue #53's case and stays retried, so the bound is paid up
to three times: ~93 s across three attempts at the default, ~18 s at 5 s. A working tool never
needs more than a few seconds to be connected to.

**Read: 300 s, the adapter's default, set explicitly.** The first draft lowered it to 180 s, which
would have been a regression, because of how `mcp` 1.28.1 handles a read timeout once the response
has started. Read from the installed source and reproduced over a real socket:

- `_handle_sse_response` (`mcp/client/streamable_http.py:429`) catches the `ReadTimeout`, logs it
  at DEBUG and drops it. It resumes only when the server sent an SSE event id, which a stateless
  server does not.
- `ClientSession.send_request` (`mcp/shared/session.py:284-292`) waits for the response with no
  limit unless `read_timeout_seconds` is set, and nothing sets it.
- So the call never returns: no result, no exception, and the middleware never sees it. Probed: a
  tool silent for 6 s under a 1 s bound was still waiting 12 s later.

A lower bound therefore does not turn a long silence into a failure; it turns it into a call that
never returns. `mcp` 2.2.0 fixes this — `_resolve_abandoned_request` fails a request whose stream
ended without a way to resume — while 1.30.0, the latest 1.x release, does not. 2.x moves to
`httpx2`, which ties it to the upgrade in Non-Goals.

**A working tool is not silent.** The `mcp` server transport sends its headers as soon as it takes
the request, and pings the SSE stream every 15 s while the tool runs — the default of
`sse_starlette`, which it uses. Probed: a 20 s tool succeeded under a 16 s read bound, because the
ping at 15 s counted as a read. A multi-minute dataset query therefore stays far from either bound.
**Unverified:** whether DIAL Core forwards those pings in deployment mode. If it buffers the
stream instead, a tool that runs longer than 300 s surfaces as a read timeout before the headers.

**What a read timeout means, then.** Nothing arrived for 300 s, so the path is stuck, not slow:

| Where it sticks | What the tool call sees | Cost |
| --- | --- | --- |
| Before the response headers | `ExceptionGroup[ReadTimeout]` after 300 s (probed at 1 s) | 300 s, relayed without a retry — decision 3 |
| After the headers: pings stop, the connection stays open | Nothing; the call waits forever | Unbounded — the residual below |

- *Rejected: `sse_read_timeout` 180 s,* the first draft. Per the above it bounds nothing more, and
  it makes calls to a server that does not ping, silent for 180–300 s, hang where they succeed
  today.
- *Rejected: a session `read_timeout_seconds` now.* It would make the stuck-after-headers case fail
  as an `McpError` (code 408), but it limits the whole call rather than the silence, so it needs a
  value above the longest real tool call and a verdict of its own. Deferred.
- **Residual, accepted:** a stream that stops after its headers without closing hangs the call, and
  the iteration with it. That is equally true before this change. See Deferred.

### 2. `retry_on` as a callable, not a tuple

- *Rejected: a tuple of exception types.* `should_retry_exception` does `isinstance(exc, retry_on)`,
  which is `False` for the `ExceptionGroup` our failure actually arrives as. The middleware would
  then skip the retry and go straight to `_handle_failure` — the turn survives, so **nothing fails
  and nothing logs**; the retry simply never happens. That is the worst available failure mode, and
  it is the single most likely way this change is quietly broken by a later edit.

### 3. A dedicated retry predicate, not `resolve_exception(...).retryable`

Reusing the existing classifier was the first instinct and is wrong. It answers *"would trying
again later help?"*, which is `True` for 429 — `_resolve_service_status` maps 429 to
`(_MSG_SERVICE_RATE_LIMITED, True)`. The middleware needs *"would trying again right now, with no
delay, help?"*, which for 429 is `False`.

The predicate: `httpx.TransportError` — connect, write and pool timeouts, network errors and
remote protocol errors, per the verified hierarchy — plus HTTP 502 and 503, evaluated on the
unwrapped leaves. Four transport errors are excluded and relayed as not worth retrying:
`httpx.ReadTimeout` (below), and three that fail the same way on every attempt —
`UnsupportedProtocol` (a URL scheme httpx does not support), `LocalProtocolError` (a request
httpx refused to send) and `ProxyError` (a proxy that refused the tunnel).

- *Rejected: including 500 and 504.* An immediate repeat hits the same server-side exception or the
  same slow operation.
- *Rejected: including 429 in the in-process set.* The three seconds the retries span rarely
  outlast a `Retry-After` measured in seconds to minutes, and each attempt against a limiter that
  is already refusing can consume quota or extend its window. The agent retries it instead, from
  a distance the middleware cannot reach — see decision 6.
- *Rejected: retrying a read timeout.* It reaches the tool only when nothing arrived for the whole
  300 s read bound (decision 1b), so each retry costs another 300 s: 15 minutes per agent-level
  call, 45 with research-agent's allowance. It is relayed with the will-not-help verdict — the
  user's choice over retry-later, which would still let research-agent spend two more waits of up
  to 300 s each.
- **Evidence note:** 502 is evidence-backed (the incident's next connection succeeded 16 ms later)
  and connect timeout is issue #53's observed case. 503, and the exclusion of 500 and 504, are
  reasoning rather than observation. Worth revisiting if the logs ever show one.

### 4. The unwrap helper lives in `error_resolution.py`

Both consumers are classifiers, and that module already owns "what failed, and is it retryable".
Putting the helper anywhere else means one of the two importing from a module that is not about
error classification.

- *Rejected: a new dedicated module.* It would hold one function used by the module it would have
  to import from anyway.
- *Rejected: duplicating the unwrap at each call site.* Two copies of a subtle rule that must agree.

### 5. Flatten to leaves; retry only if every leaf is retryable

The helper returns the list of leaves, recursing through nested wrappers, rather than hunting for a
single one — otherwise the multi-member case falls straight back to today's broken classification.

- *Rejected: `any` leaf retryable.* A retry re-runs the whole call, so one permanent cause among
  several makes it pointless.
- *Rejected: selecting "the first non-retryable leaf" for the message,* which an earlier draft of
  this design proposed. Multi-member groups cannot come from parallel tool calls — `gather` raises
  one exception and `_panic_or_proceed` (`pregel/_runner.py:687`) raises one exception — so the only
  source is one tool call's own transport tasks, whose leaves describe the same dead connection.
  The first leaf tells the same story, and the selection rule would have forced splitting
  `resolve_exception` in two.

**The verdict weighs every leaf, for the same reason.** Retrying may help only when every leaf is
one the in-process retry covers. Retry later applies only when every leaf may clear with time — a
transport failure other than a read timeout, a 429, or a 5xx. Anything else means retrying will not
help. The failure kind and the HTTP status in the relayed message come from the first leaf, like
the turn-level message.

**Cancellation needs no special case.** Probed: a group holding any `BaseException` — and
`asyncio.CancelledError` is one — is a `BaseExceptionGroup`, for which `isinstance(group, Exception)`
is `False`. Every handler in the path catches `Exception`, so cancellation propagates untouched by
construction rather than by anyone remembering to exclude it. Worth stating in the spec so a later
change does not "fix" it.

### 6. The relayed message is composed, never copied

Tool name, exception class name, HTTP status where there is one, and an explicit verdict on
whether retrying now helps.

- *Rejected: relaying `str(exc)`.* The incident's real message is
  `Server error '502 Bad Gateway' for url 'http://<internal-service>/v1/deployments/<id>/mcp'` — an
  internal cluster endpoint and a deployment identifier, going into a conversation that is both
  model-visible and persisted. It also would not work: for the `ExceptionGroup` the string is
  `"unhandled errors in a TaskGroup (1 sub-exception)"`.
- *Rejected: including `Retry-After`.* The agent cannot wait, so an interval it cannot honour only
  invites the retry the design excludes.

The **verdict** is the load-bearing part. Without it the agent has to infer HTTP semantics, and the
prompt's "you may retry" would send it back at a 429.

### 7. Prompt guidance split three ways

Findings are the accumulated tool results, not a file research-agent writes, so the three nodes
need three different instructions: research-agent may retry and otherwise routes around;
research-review treats a tool-caused gap as plannable work; the report node states the evidence
gap.

- *Rejected: one shared instruction.* Asking research-agent to record findings, or the report node
  to retry, would be instructions neither can act on.

**The retry allowance is a number, not a judgement call.** Research-agent is told it may make at
most two repeat calls to a failed tool. Leaving it unstated was considered and rejected: a model
handed "retry if it seems worthwhile" retries a different number of times on every run, which is
both untestable and unbounded in cost.

The two budgets multiply, and the prompt must not imply otherwise. Each call research-agent makes
already carries the middleware's three requests, so for a **retryable** failure that never
recovers the totals are `(1 + agent retries) × 3`:

| Agent budget | Requests to the server | Backoff time | Extra model round-trips | Extra input tokens at the incident's measured 52k per call |
| --- | --- | --- | --- | --- |
| 1 | 6 | ~6 s | 1 | ~52,000 |
| 2 (chosen) | 9 | ~9 s | 2 | ~104,000 |
| 3 | 12 | ~12 s | 3 | ~156,000 |

Nine requests for one dead gateway looks large and is cheap: they carry no tokens, and the wall
clock is split between the backoff and the two model round-trips. The agent's retries earn their
place despite duplicating the middleware's because they land tens of seconds into the failure,
well past the three seconds the in-process retries cover.

**The other two verdicts cost far less.** A rate-limited call carries no in-process retries, so
the whole allowance is three requests rather than nine — spaced by whatever other work
research-agent does between them, which is the point of returning to the tool rather than
repeating it. Where no other work is outstanding, the agent may repeat it directly and the
spacing collapses to one model round-trip; that is accepted, because a few seconds is still the
interval that matters and refusing the retry would abandon the evidence rather than delay it. A
call marked not worth retrying costs one request, since research-agent is told not to repeat it at
all; there the allowance is a ceiling on a model that ignores the verdict, not an expected path.
- **Constraint discovered during research:** the report node's instruction collides with
  **Reports carry no meta-annotations about the research process**, whose third scenario bans
  stating the tool calls a run took. The wording must stay on the evidence ("this could not be
  established") and never reach the run ("the tool failed twice"). The `report-composition` delta
  pins that boundary.
- **A fourth prompt, not three.** `REPORT_REVIEW_SYSTEM_PROMPT` (`app/research/prompts.py:317-352`)
  is a closed checklist — "Check exactly these", and "Your job is to find violations of the checks
  above, and nothing else" — and its never-include list covers confidence, complexity, times,
  iteration and token counts, but not a named tool or an attempt count. The new boundary is
  therefore unenforced unless that list gains it.

### 8. Removing `enable_tool_error_handling()` is correctness, not a fix

- *Rejected: keeping it.* It is redundant — `convert_mcp_tool_to_langchain_tool` already sets
  `handle_tool_error=_handle_mcp_tool_error` (`tools.py:527,535`) and we fetch tools through
  `MultiServerMCPClient.get_tools()`, which uses that default. It is also lossy: the callback
  returns the error's content blocks, while the bool `True` returns `e.args[0]`.
- **Scope honesty:** `_MCPToolExecutionError`'s message comes from `_summarize_tool_error`, which
  joins the text of every text block. So for a text-only error payload the two paths produce
  **identical** output and this changes nothing. The only real difference is a multimodal error
  payload, where the override drops image and file blocks. This is cleanup with a narrow real
  benefit, not part of the crash fix — it should not be sold as one.

### 9. The test harness is pytest, not a runnable demo

An in-process MCP server plus a scripted model, asserting on what the **next model call** receives:
an error `ToolMessage` with what content, or a raised turn.

- *Rejected: a demo application.* Run by hand, it rots, and it cannot fail CI — which is the whole
  point, since this change's failure modes are silent.
- **Cases**, narrowed by the user: an `isError=True` text result; a transport failure; an
  `ExceptionGroup`-wrapped 502 retried exactly twice; a 429 **not** retried in process; a
  server-side exception. Three more that the requirements make load-bearing: a parallel batch where
  one call fails and the siblings' results still reach the agent (the incident's headline symptom);
  a retry that **succeeds**, asserting the log record exists even though the turn looks normal; and
  an assertion that the relayed message contains no endpoint, which is the requirement the rejected
  `on_failure="continue"` violated.
- **One case added during implementation:** a read timeout, called once and relayed as not worth
  retrying (decision 3).
- **Cases deliberately dropped:** an unknown tool name, and arguments violating the schema — the
  model can only pick from advertised tools with schema-conforming arguments, so neither is
  reachable through the agent. Image and audio error payloads — for text-only errors the two
  handlers are identical (decision 8), and audio is a latent converter failure unrelated to this
  change.

### 10. Tests share the production logic by importing it, and never share its expectations

There is no second copy of the error handling. The harness drives the real agent graph with the
real middleware, so the retry predicate and the unwrap helper are exercised as imported production
code, not reimplemented. The tests inject *failures* — a reset connection, a 502, a 429 — and
observe *behaviour*: how many attempts the server saw, and what the next model call received.

The expectations are the part that must stay independent. A test asserting "502 is retried" by
reading the production retryable-status set would pass whatever that set contains, and so could
never catch a wrong one. So the harness states its outcomes literally — a 502 is called once and
retried twice, a 429 is called once and never retried in process — and the status set is never imported into
an assertion or used to parametrize one.

- *Rejected: parametrizing the cases over the production status constant.* It reads as thorough and
  proves nothing; the test would follow the code under test wherever it went.
- *Rejected: a fixture that mirrors the retry rules in the test tree.* That is the duplication the
  question is about, and it is worse than either alternative, because a drifted copy fails in a way
  that looks like a real defect.

The one place a literal must be repeated is the retryable status set itself — 502 and 503 appear in
the predicate and their behaviour is asserted case by case in the harness. That repetition is
deliberate: the test is the independent statement of intent, and the two disagreeing is exactly the
signal wanted.

### 11. A retry is logged, not staged

A retry is invisible everywhere a reader looks, by construction. The runner builds a stage in
`_handle_tool_message` (`app/research/runner.py:794-828`), keyed on the tool call id it popped from
`_pending_tool_calls`, so one tool result yields one stage regardless of how many attempts produced
it. The conversation gets that same single result, and the persisted state is built from the
messages, so both record one call. The only residue is the stage's elapsed time, measured from
`tool_call.start` to the result's arrival, which silently absorbs the retry.

The log record is therefore the only trace, which is why the spec makes it mandatory rather than
advisory.

- *Rejected: a DIAL stage per retry.* The prebuilt middleware has no access to the choice — stages
  are driven off the graph stream by the runner, and nothing in the middleware list
  (`agent_logging_middleware`, `stream_drop_retry_middleware`, `ImageBudgetMiddleware`, forced tool
  choice) is handed one. Emitting a stage would mean the custom `wrap_tool_call` middleware
  rejected in decision 1, closing over the choice, and would reimplement the backoff, budget and
  `GraphBubbleUp` handling to do it.
- *Rejected on its merits too, not only its cost.* A retry that succeeds in milliseconds is not
  something the reader can act on, and a failed attempt is not a research action. One stage per
  tool call the agent made is the view that matches what the agent did.
- **Precedent:** the LLM stream-drop retry has the identical gap one layer up, tracked as issue #28
  ("Stream-drop retries are silent except in the report loop"), and the remedy asked for there is a
  `WARNING` log, not a stage. This change follows it rather than inventing a second convention.

## No changes required

Verified during research; listed so an implementer does not go looking.

- `src/dial_deep_research/app/research/runner.py` — already renders a failed tool as a ❌ stage:
  line 804 reads `msg.status == "error"` and threads it through `log_tool_call_completed`. Error
  `ToolMessage`s from the middleware get the existing treatment with no edit.
- `src/dial_deep_research/app/preparation/agent.py` — no MCP tools.
- `src/dial_deep_research/app/research/runner.py` — the stage path needs no edit, but note that
  whatever the relayed message contains is rendered into the stage body, which is why decision 1
  rejects the default formatter.
- The **Tool-calling agent over MCP-loaded tools** requirement — it already states that the adapter
  installs the error conversion by default and only requires the app to *clear* it on the
  application-called tool. Deleting our override does not contradict it, so it needs no delta.
- `pyproject.toml` — no dependency change.

## Deferred, and where it goes

Recorded here because it is real and this change does not do it:

- **Two existing requirements still name `handle_tool_error` as the mechanism that stops a tool
  error bubbling** — `openspec/specs/dial-agent-with-mcp/spec.md:127` (the stage requirement) and
  `:506` (the Opik scenario). After this change that is true only for errors the server reports in
  its own result; a transport failure now reaches the agent through the middleware instead. Both
  are prose describing a mechanism rather than a rule anything can violate, and correcting either
  needs a `MODIFIED` block carrying its full requirement — line 127 is one dense paragraph — so
  they are left. An implementer should not read their absence as agreement.

  The third, `openspec/specs/research-execution/spec.md:115`, **was** corrected: it granted
  research-agent an unbounded retry ("MAY retry without failing the turn") that the new allowance
  caps at two repeats, so the merged specs would have asserted both. Its requirement is carried in
  full in this change's `research-execution` delta, with that scenario rewritten and a second one
  added for failures that never reach the server.
- **A call whose response stream stops after its headers hangs** (decision 1b), as it does before
  this change. The fix is either the `mcp` 2.x upgrade — 2.2.0 fails such a request, and it brings
  `httpx2`, so it belongs with the upgrade in Non-Goals — or a session `read_timeout_seconds` set
  above the longest real tool call, with a verdict chosen for it.

## Risks / Trade-offs

- **A later edit replaces the callable `retry_on` with a tuple** → the retry silently stops firing.
  Mitigation: the harness case that asserts *exactly two retries* on an `ExceptionGroup`-wrapped 502,
  which fails the moment the predicate stops unwrapping.
- **`on_failure="continue"` also converts genuine bugs in our own code into tool results,** which is
  the opposite of the LangChain guide's "let unexpected errors bubble up" row. Mitigation: the
  required log record for every converted failure, so a real bug is visible even though the turn
  completes. Accepted deliberately: a research agent that keeps going and reports a degraded result
  beats one that dies on an unexpected `KeyError`.
- **The agent loops on a dead tool,** burning iterations. Mitigation for now: the prompt's bounded
  retry allowance plus the existing recursion and iteration caps. `ToolCallLimitMiddleware` is the
  proper guard and is deferred.
- **The report leaks process detail** while trying to state a gap. Mitigation: the
  `report-composition` delta, plus adding the case to `REPORT_REVIEW_SYSTEM_PROMPT`'s never-include
  list. The review loop does **not** already cover it — its checklist is closed and names only
  confidence, complexity, times and counts.
- **503, 500 and 504 are classified on reasoning, not evidence** (decision 3). Mitigation: they are
  a small set, the cost of being wrong is one wasted request or one missed retry, and the logs will
  show which statuses actually occur.
- **The subclass overrides `_handle_failure`, a private method.** The underscore marks it as API
  that may change without notice, and our constraint is only `langchain>=1.2.0,<2.0.0`, so a patch
  bump could change or remove it. Mitigations: the harness fails loudly if the relayed message or
  the retry count changes shape, and decision 1 names `ToolErrorMiddleware` as the public
  replacement to adopt once the upgrade lands. Accepted for now because the alternative is
  upgrading before the harness exists. The retry log records rest on one more internal behaviour:
  the parent calling the handler it is given once per attempt. The harness case for a retry that
  succeeds fails if that changes.
- **A retried tool call is not idempotent in principle.** Accepted: the MCP tools in scope are
  reads, and the failures retried are ones where the request provably did not reach the server or
  was refused by a gateway before it did.

## Migration Plan

No migration. The change is behaviour-only inside a turn, with no schema, no configuration and no
dependency movement. Rollback is reverting the commit; nothing persists across turns that a
rolled-back version would fail to read.

## Open Questions

None. The one that stood here — how to express research-agent's retry allowance — is settled in
decision 7: a stated number, two, rather than a rule without a count.
