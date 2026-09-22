## 1. Classification foundations

Nothing else can be built first: the middleware, the relayed message and the turn-level resolver
all depend on these.

- [ ] 1.1 Add an exception-group flattening helper to `app/error_resolution.py` that returns the leaves of a wrapper, recursing through nested wrappers, and returns a non-wrapper unchanged
- [ ] 1.2 Apply the unwrap across the whole of `resolve_exception`, not only `_extract_error_details` — `_resolve_status_or_type`, `_resolve_httpx_status_or_type` and the mid-stream rule all branch on the exception's own type, so unwrapping for extraction alone leaves them matching the wrapper
- [ ] 1.3 Use the first leaf for the status, failure kind and message when a wrapper holds several, per design decision 5
- [ ] 1.4 Add the immediate-retry predicate: a callable over `httpx.TransportError` plus HTTP 502 and 503, excluding 429, returning true only when **every** leaf is retryable. Keep it separate from `resolve_exception(...).retryable`, which answers a different question and is true for 429
- [ ] 1.5 Extend `tests/test_error_resolution.py` with wrapped-failure cases, including that a task-group-wrapped 502 resolves to the retryable service message rather than the generic fallback

## 2. MCP transport

- [ ] 2.1 Set `timeout: 5` and `sse_read_timeout: 180` on each connection built in `build_mcp_client` (`app/mcp_tools.py`), replacing the adapter defaults of 30 s and 300 s that the retry budget would multiply
- [ ] 2.2 Delete `enable_tool_error_handling()` and its call site, leaving the explicit clearing of the handler on the application-called file-sharing tool in place
- [ ] 2.3 Rewrite the two assertions in `tests/test_mcp_client.py` that pin the deleted behaviour (`handle_tool_error` on the agent tools at line 246, and on the dataset-metadata tool at line 326) to assert the adapter's own handler is left installed instead

## 3. The retry middleware

- [ ] 3.1 Add a module with a `ToolRetryMiddleware` subclass configured `max_retries=2`, the predicate from 1.4 as `retry_on`, and the prebuilt's default backoff
- [ ] 3.2 Override `_handle_failure` to compose the relayed message from the tool name, the exception class, the HTTP status where there is one, and one of the three verdicts. Never `str(exc)`, a URL, an endpoint or a traceback — the default formatter's `str(exc)` is the internal endpoint, and that content reaches the DIAL stage body as well as the model
- [ ] 3.3 Map failures to verdicts: retry-now for transport failures and 502/503 whose retries are spent; retry-later for 429 and for server errors excluded from the in-process retry such as 500 and 504; will-not-help for everything else. The retry-later text says to gather other evidence first and come back, and must leave the tool callable again when nothing else is outstanding
- [ ] 3.4 Emit the log records the spec requires — tool name, failure kind, attempt count — on every retry and every relayed failure, following the logging policy: structure only, never arguments, output or the failure's own text. `_handle_failure` is the only place all three values are in scope, and the prebuilt logs nothing
- [ ] 3.5 Add unit tests for the subclass covering the three verdicts and asserting no endpoint appears in any composed message

## 4. Wiring

- [ ] 4.1 Add the middleware to the research-agent graph in `app/research/nodes.py`
- [ ] 4.2 Add it to the playground graph in `app/playground/agent.py`
- [ ] 4.3 Leave the preparation agent alone — it binds no MCP tools — and confirm no other `create_agent` call site needs it

## 5. Prompts

- [ ] 5.1 Research-agent: a tool may fail, the result carries a verdict, one action per verdict, and an allowance of at most two repeat calls to the same failed tool, stated as a number
- [ ] 5.2 Research-agent: the allowance is its own and is not the total number of attempts, so it must not reason about the in-process retries behind it
- [ ] 5.3 Research-review: a plan item may be uncovered because a tool failed rather than because research-agent skipped it, and that gap may be planned against in the next iteration
- [ ] 5.4 Report node: state an unreachable source as missing evidence and what cannot be concluded, never naming the tool, the failure or the attempt count
- [ ] 5.5 `REPORT_REVIEW_SYSTEM_PROMPT`: add the same rule to its never-include list. Its checklist is closed — "Check exactly these" — so the boundary in 5.4 is unenforced without this

## 6. Integration harness

Written after the implementation so it asserts real behaviour rather than an intention.

- [ ] 6.1 Build the harness: an in-process MCP server whose tools fail on demand, plus a scripted model, asserting what the **next model call** receives
- [ ] 6.2 Case: a server-reported `isError` result with text content reaches the agent carrying the server's own content, with no verdict
- [ ] 6.3 Case: a transport failure is retried and relayed
- [ ] 6.4 Case: an `ExceptionGroup`-wrapped 502 is retried exactly twice, then relayed — this is the case a tuple-valued `retry_on` would silently stop retrying
- [ ] 6.5 Case: a 429 is called once, never retried in process, and relayed with the retry-later verdict
- [ ] 6.6 Case: a parallel batch where one call fails and the siblings' results still reach the agent
- [ ] 6.7 Case: a retry that succeeds — the agent sees one successful result, one stage, and the log still carries a record
- [ ] 6.8 Case: the relayed message contains no endpoint, host name or deployment identifier
- [ ] 6.9 Case: a server-side exception is relayed rather than aborting the turn
- [ ] 6.10 Keep expectations literal — a 502 retried twice, a 429 not retried — and never import the retryable-status set into an assertion or parametrize over it, or the tests would follow the code under test wherever it went

## 7. Documentation

- [ ] 7.1 Update `docs/architecture.md`, including the claim at lines 378-380 that a tool error does not end an iteration — true only after this change — plus the in-process retry and the three-verdict relay
- [ ] 7.2 Run `make format` and `make lint`
