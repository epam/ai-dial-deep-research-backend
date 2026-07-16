# Design

## Context

The failure mode is a mid-stream connection drop on an LLM call: response headers (200) arrive,
then the chunked SSE body ends prematurely. The OpenAI client retries only pre-response failures,
so these propagate as raw `httpx.RemoteProtocolError` (clean early close) or `httpx.ReadError`
(reset) — the retry has to live in the app.

## Decisions

### One exception tuple, three retry mechanisms

The transient-drop exception tuple lives in `utils/llm.py` as the single source of truth. The
app's LLM calls come in three shapes, each with its own idiomatic retry hook:

1. **Agents built with `create_agent`** (preparation, playground, researcher): langchain's
   `ModelRetryMiddleware(max_retries=2, retry_on=<tuple>, on_failure="error")`. Backoff defaults
   (exponential, initial 1 s, jitter) match the chosen budget. A shared factory in
   `utils/llm.py` builds it so all agents stay in sync.
2. **Structured-output `ainvoke` calls** (query review, plan review, research review):
   `Runnable.with_retry(retry_if_exception_type=<tuple>, stop_after_attempt=3)` — same budget,
   library-provided exponential jittered backoff.
3. **The report node's `llm.astream` loop**: neither hook applies to a hand-rolled `async for`,
   so a small retry loop restarts the stream on a transient drop. The accumulated chunk list is
   reset per attempt, so the persisted report is always a single attempt's full text.

### `on_failure="error"`, never synthetic messages

`ModelRetryMiddleware`'s default `on_failure="continue"` injects the failure as a message for the
model to react to. That would violate the failures-as-DIAL-errors requirement (errors must reach
the user via the DIAL error protocol, not as fake model output), so exhausted retries re-raise.

### Retry set: exactly the two transport-drop shapes

`RemoteProtocolError` and `ReadError` are the two surfaces of "the connection died mid-stream".
Timeouts and status errors keep their existing handling (OpenAI-client retries where applicable,
then error resolution); mid-stream `openai.APIError` events are deliberately not retried — they
can carry deterministic causes such as content-filter terminations.

### Duplicate-partial-text trade-off

A retried call re-issues from scratch; tokens the failed attempt already streamed to the DIAL
choice cannot be retracted, so the user may see a partial fragment followed by the full retried
output. Graph/agent state is unaffected (nodes commit messages only on success). Observed drops
occur at stream start, before content tokens, so in practice duplicates should be rare.

### Constants, not settings

The budget and backoff are code constants. No env knobs until a real need appears — this keeps
the README env table and the application-properties schema untouched.

### Error classification when retries are exhausted

`httpx.ReadError` is a `httpx.NetworkError` subclass and already resolves to the retryable
service network-error message. `httpx.RemoteProtocolError` is a `ProtocolError` (not a
`NetworkError`) and today falls through to the generic non-retryable HTTP message — the resolver
gets an explicit branch mapping it to the same retryable network-error resolution. Its sibling
`LocalProtocolError` (a client-side bug) stays non-retryable.
