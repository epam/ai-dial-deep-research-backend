# Retry transient LLM stream drops

## Why

In production, LLM calls intermittently die mid-stream: the upstream returns 200 and starts the
SSE body, then the connection drops within a couple of seconds, surfacing in the app as
`httpx.RemoteProtocolError` ("peer closed connection without sending complete message body").
Incident tracing showed the drop originates upstream of the app (the model endpoint's stream ends
abnormally and the intermediaries reset the connection down the chain), so the app cannot prevent
it — only tolerate it.

Today one such drop aborts the whole turn: the OpenAI client's `max_retries` covers only failures
before a response starts, so a post-header drop is never retried, and the resolver classifies it
as a generic non-retryable HTTP error. A single dropped stream can discard many minutes of
research work.

## What Changes

- **Retry every LLM call in-app on transient stream drops** — `httpx.RemoteProtocolError` and
  `httpx.ReadError` (the reset flavor of the same event). Budget: 2 retries per call (3 attempts
  total), exponential backoff with jitter. On exhaustion the last exception propagates to the
  existing DIAL-error-protocol handler.
  - Agent model calls (preparation, playground, researcher): langchain's `ModelRetryMiddleware`.
  - Structured review calls (query review, plan review, research review): `Runnable.with_retry`.
  - Report-writing stream: a small retry loop that restarts the stream and resets the
    accumulated text each attempt.
- **Classify `httpx.RemoteProtocolError` as retryable** in error resolution (service
  network-error wording) instead of the generic non-retryable HTTP message. `httpx.ReadError`
  already resolves retryable via the network-error branch.
- Accepted trade-off: a retry after partial tokens already streamed can render duplicated partial
  text in the chat. Observed drops happen at stream start, so this is rare — and preferable to
  losing the turn.
- Alternative rejected: only reclassifying the error as retryable (no in-app retry) would still
  force the user to manually re-run long research turns.

## Capabilities

### Modified Capabilities

- `dial-agent-with-mcp`: new requirement for in-app retry of transient LLM stream drops;
  the failures-as-DIAL-errors requirement's status/type map now resolves a transport-level
  stream drop to a retryable network-error message.

## Impact

- `src/dial_deep_research/utils/llm.py` (shared retry primitives),
  `app/preparation/agent.py`, `app/playground/agent.py`, `app/research/nodes.py`,
  `app/preparation/tools.py`, `app/error_resolution.py`, tests.
- No settings, environment variables, or application-properties changes.
