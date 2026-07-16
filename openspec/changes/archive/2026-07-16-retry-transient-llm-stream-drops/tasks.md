# Tasks

## 1. Shared retry primitives (`utils/llm.py`)
- [x] Define the transient stream-drop exception tuple (`httpx.RemoteProtocolError`,
      `httpx.ReadError`) as the single source of truth
- [x] Add a factory returning the agents' `ModelRetryMiddleware` (max_retries=2,
      retry_on=the tuple, on_failure="error", default exponential backoff + jitter)

## 2. Agent model calls
- [x] `app/preparation/agent.py`: pass the retry middleware to `create_agent`
- [x] `app/playground/agent.py`: pass the retry middleware to `create_agent`
- [x] `app/research/nodes.py` `build_researcher_agent`: add the retry middleware alongside
      `ForceToolChoiceMiddleware`

## 3. Structured review calls
- [x] `app/preparation/tools.py`: wrap the query-review and plan-review LLMs with
      `.with_retry(retry_if_exception_type=<tuple>, stop_after_attempt=3)`
- [x] `app/research/nodes.py` reviewer node: same wrapping

## 4. Report stream
- [x] `app/research/nodes.py` report node: retry loop around `llm.astream` on the transient
      tuple (3 attempts, backoff), resetting the accumulated chunks each attempt

## 5. Error classification (`app/error_resolution.py`)
- [x] Resolve `httpx.RemoteProtocolError` to the service network-error message, retryable,
      ahead of the generic HTTP fallbacks (keep `LocalProtocolError` non-retryable)
- [x] Update the module docstring's httpx note accordingly

## 6. Tests
- [x] `error_resolution`: `RemoteProtocolError` → network-error message, retryable;
      `ReadError` → retryable via the existing `NetworkError` branch
- [x] Retry behavior: a call failing once with `RemoteProtocolError` then succeeding completes
      without error; failing on all attempts re-raises after 3 attempts
- [x] Report node: a retried stream resets accumulated text (persisted report contains only the
      successful attempt's output)

## 7. Verify
- [x] `make format` and `make lint`
- [x] `make test`
