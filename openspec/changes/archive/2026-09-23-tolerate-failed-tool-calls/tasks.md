## 1. Classification foundations

Nothing else can be built first: the middleware, the relayed message and the turn-level resolver
all depend on these.

- [x] 1.1 Add an exception-group flattening helper to `app/error_resolution.py` that returns the leaves of a wrapper, recursing through nested wrappers, and returns a non-wrapper unchanged
- [x] 1.2 Apply the unwrap across the whole of `resolve_exception`, not only `_extract_error_details` — `_resolve_status_or_type`, `_resolve_httpx_status_or_type` and the mid-stream rule all branch on the exception's own type, so unwrapping for extraction alone leaves them matching the wrapper
- [x] 1.3 Use the first leaf for the status, failure kind and message when a wrapper holds several, per design decision 5
- [x] 1.4 Add the immediate-retry predicate: a callable over `httpx.TransportError` except `httpx.ReadTimeout`, `UnsupportedProtocol`, `LocalProtocolError` and `ProxyError`, plus HTTP 502 and 503, excluding 429, returning true only when **every** leaf is retryable. Keep it separate from `resolve_exception(...).retryable`, which answers a different question and is true for 429
- [x] 1.5 Extend `tests/test_error_resolution.py` with wrapped-failure cases, including that a task-group-wrapped 502 resolves to the retryable service message rather than the generic fallback

## 2. MCP transport

- [x] 2.1 Set `timeout: 5` and `sse_read_timeout: 300` on each connection built in `build_mcp_client` (`app/mcp_tools.py`): lower the adapter's 30 s connect default, which the retry budget multiplies, and keep its 300 s read default explicitly, since `mcp` 1.x hangs a call whose read times out mid-response (design decision 1b)
- [x] 2.2 Delete `enable_tool_error_handling()` and its call site, leaving the explicit clearing of the handler on the application-called file-sharing tool in place
- [x] 2.3 Rewrite the two assertions in `tests/test_mcp_client.py` that pin the deleted behaviour (`handle_tool_error` on the agent tools at line 246, and on the dataset-metadata tool at line 326) to assert the adapter's own handler is left installed instead

## 3. The retry middleware

- [x] 3.1 Add a module with a `ToolRetryMiddleware` subclass configured `max_retries=2`, the predicate from 1.4 as `retry_on`, and the prebuilt's default backoff
- [x] 3.2 Override `_handle_failure` to compose the relayed message from the tool name, the exception class, the HTTP status where there is one, and one of the three verdicts. Never `str(exc)`, a URL, an endpoint or a traceback — the default formatter's `str(exc)` is the internal endpoint, and that content reaches the DIAL stage body as well as the model
- [x] 3.3 Map failures to verdicts: retry-now for transport failures and 502/503 whose retries are spent; retry-later for 429 and for server errors excluded from the in-process retry such as 500 and 504; will-not-help for everything else, including a read timeout. A group gets retry-now or retry-later only when every leaf does, and its failure kind and status come from the first leaf. The retry-later text says to gather other evidence first and come back, and must leave the tool callable again when nothing else is outstanding
- [x] 3.4 Emit the log records the spec requires — tool name, failure kind, attempt count — on every retry and every relayed failure, following the logging policy: structure only, never arguments, output or the failure's own text. `_handle_failure` logs the relayed failure; a retry is logged by wrapping, in `awrap_tool_call` only, the handler the parent calls once per attempt, because a retry that succeeds never reaches `_handle_failure`, and the prebuilt logs nothing
- [x] 3.5 Add unit tests for the subclass covering the three verdicts and asserting no endpoint appears in any composed message

## 4. Wiring

- [x] 4.1 Add the middleware to the research-agent graph in `app/research/nodes.py`
- [x] 4.2 Add it to the playground graph in `app/playground/agent.py`
- [x] 4.3 Leave the preparation agent alone — it binds no MCP tools — and confirm no other `create_agent` call site needs it

## 5. Prompts

- [x] 5.1 Research-agent: a tool may fail, the result carries a verdict, one action per verdict, and an allowance of at most two repeat calls to the same failed tool, stated as a number and counted across the whole research
- [x] 5.2 Research-agent: the allowance is its own and is not the total number of attempts, so it must not reason about the in-process retries behind it
- [x] 5.3 Research-review: a result saying a tool failed is not evidence, and the evidence it would have given is unavailable — not planned again and not counted as coverage; a result the image budget dropped is not a tool failure, and whether to plan its work again follows the rest of the findings and the slots the drop message reports
- [x] 5.4 Report node: when evidence the answer or a plan item depends on could not be retrieved, state that and what cannot be concluded, never naming the tool, the error or the attempt count
- [x] 5.5 `REPORT_REVIEW_SYSTEM_PROMPT`: add the same rule to its never-include list. Its checklist is closed — "Check exactly these" — so the boundary in 5.4 is unenforced without this
- [x] 5.6 Research-agent: a no-verdict error that names no argument mistake is treated as not worth retrying, an image-budget drop is not a failed call, and a plan item whose only tool may no longer be called counts as done

## 6. Integration harness

Written after the implementation so it asserts real behaviour rather than an intention.

- [x] 6.1 Build the harness: an in-process MCP server whose tools fail on demand, plus a scripted model, asserting what the **next model call** receives
- [x] 6.2 Case: a server-reported `isError` result with text content reaches the agent carrying the server's own content, with no verdict
- [x] 6.3 Case: a transport failure is retried and relayed
- [x] 6.4 Case: an `ExceptionGroup`-wrapped 502 is retried exactly twice, then relayed — this is the case a tuple-valued `retry_on` would silently stop retrying
- [x] 6.5 Case: a 429 is called once, never retried in process, and relayed with the retry-later verdict
- [x] 6.6 Case: a parallel batch where one call fails and the siblings' results still reach the agent
- [x] 6.7 Case: a retry that succeeds — the agent sees one successful result, one stage, and the log still carries a record
- [x] 6.8 Case: the relayed message contains no endpoint, host name or deployment identifier
- [x] 6.9 Case: a server-side exception is relayed rather than aborting the turn
- [x] 6.10 Keep expectations literal — a 502 retried twice, a 429 not retried — and never import the retryable-status set into an assertion or parametrize over it, or the tests would follow the code under test wherever it went
- [x] 6.11 Case: a read timeout is called once and relayed with the will-not-help verdict

## 7. Documentation

- [x] 7.1 Update `docs/architecture.md`, including the claim at lines 378-380 that a tool error does not end an iteration — true only after this change — plus the in-process retry and the three-verdict relay
- [x] 7.2 Run `make format` and `make lint`
