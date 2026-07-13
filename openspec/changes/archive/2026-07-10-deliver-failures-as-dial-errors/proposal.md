# Proposal: deliver-failures-as-dial-errors

## Why

When a turn fails, the app funnels every exception through one handler that logs it and
appends a single fixed sentence to the assistant message via `choice.append_content`
(`_FRIENDLY_ERROR` in `app/completion.py`), completing over HTTP 200. Two non-exception
outcomes — application properties that cannot be resolved (`_NOT_CONFIGURED`) and a
conversation whose research has already been handed off (`_RESEARCH_STARTED`) — are shown the
same way, as ordinary assistant content. This is the exact anti-pattern the QuickApps backend
removed in its *User-Facing Error Message Resolution* work (design doc
`ai-dial-quickapps-backend/docs/designs/error_message_resolution.md`, issue #411, PR #412):

- **The real cause is thrown away.** The DIAL error protocol carries a `display_message` field
  that upstream components author specifically for end users, plus a machine-readable `code`
  (e.g. `content_filter`, `context_length_exceeded`). The current handler reads neither, so a
  precise, user-safe explanation that already exists is replaced by one generic sentence.
- **Mid-stream model failures degrade worst.** The report node streams tokens from the LLM; a
  model that dies mid-stream surfaces as a plain `openai.APIError` with the DIAL error body
  attached — invisible to the current handler, which just appends the generic sentence.
- **"The error has been logged" is a dead end.** The user-visible text carries no correlation
  id, so an administrator has nothing to grep the logs for.
- **The failure is delivered as a fake success.** Appending error text over HTTP 200 means DIAL
  Chat renders it as a normal assistant reply (no error state, no "Regenerate response"), the
  error text is **replayed to the LLM as history on every later turn**, and DIAL Core's
  analytics record the request as a `200` success — application failures are invisible to
  status-based monitoring.

## What Changes

The change is contained in the `app` layer: a new error-resolution helper plus a rewritten
top-level handler in `app/completion.py`. It mirrors the QuickApps design, adapted to this
repo's simpler surface (synchronous stages, no execution-time `finally` stage).

- **Normalize** any supported exception (`openai` LLM errors, `aidial_sdk.exceptions.HTTPException`,
  raw `httpx` errors) into one `ErrorDetails` value object (status, code, type, internal
  message, display message), best-effort and total — diagnosing an error can never itself fail.
- **Resolve** the user-facing message by a fixed precedence: `display_message` → error-code map
  (`content_filter`, `context_length_exceeded`, …) → status/type map → mid-stream stream-failure
  rule → internal-condition map → generic fallback. Each resolution is classified retryable or
  not, and only retryable resolutions get "Please try again later." appended.
- **Handle mid-stream failures** (plain `openai.APIError` carrying a DIAL error body) as
  first-class citizens instead of the generic fallback.
- **Stamp an error reference** (8 hex chars) into both the server log record and the user-facing
  message, making the log entry findable.
- **Deliver through the DIAL error protocol** — raise `aidial_sdk.exceptions.HTTPException` built
  from the resolution instead of appending chat text. The SDK renders it as a non-200 response
  (non-streaming requests, failures before the choice opens) or an SSE `{"error": ...}` chunk in
  the open 200 stream (streaming requests). Partial report content already streamed stays
  visible; the error text stays out of LLM-visible history.
- **Never emit a balancer-retriable status** (429/502/503/504): client-attributable causes keep
  their natural non-retriable 4xx; everything else becomes 500, with the true cause preserved in
  `code`.
- **Convert both non-exception outcomes to protocol errors.** `_NOT_CONFIGURED` (application
  properties cannot be resolved) and `_RESEARCH_STARTED` (research already handed off) become
  turn-aborting protocol errors carried by internal-condition exceptions with curated,
  non-retryable messages — they no longer render as fake-success assistant content, and the
  research-already-handed-off turn no longer persists a spurious assistant message + state.
- **Stop masking a DIAL Core outage as "not configured."** Property *validation* failure becomes
  the not-configured condition; a property *fetch* failure (Core unreachable/5xx) propagates to
  the top-level handler and resolves through the service/status ladder to an accurate message.

Out of scope: any message catalog / i18n / per-deployment customization of the canned texts;
error-class telemetry; retry-policy changes; a QuickApps-style error-injection sample app; and
changes to the per-tool `handle_tool_error` recovery, Opik-tracing absorption, or image
rehydration absorption (those failures are deliberately swallowed and never abort the turn).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dial-agent-with-mcp`: the **error-handling** contract changes. The *Top-level error funnel
  with friendly assistant message* requirement is **removed** and replaced by a *Failures
  delivered as DIAL protocol errors* requirement: failures (and the two turn-aborting app
  conditions) are resolved to accurate, user-safe messages carrying an error reference and
  delivered through the DIAL error protocol, never as fake-success HTTP 200 content.

## Impact

- **Code**: new `app/error_resolution.py` (`ErrorDetails`, `ResolvedError`, extractor, precedence
  resolver, message constants, the two internal-condition exception types);
  `app/completion.py` (rewritten `chat_completion` handler — error reference, log, resolve, raise
  `HTTPException`; `_load_properties` split into fetch-vs-validation; `_run_turn` raises the app
  conditions instead of appending content; no state persisted on the error path).
- **Config / ops**: none — no new env vars, no config-schema change, no DI wiring outside the
  module. `ApplicationProperties` is untouched.
- **Tests & docs**: resolver unit tests (extraction, precedence, retryability, no-leak,
  numeric-code backfill) and handler tests (reference formatting, outgoing-status downgrade, both
  app conditions delivered as protocol errors, mid-stream in-stream delivery);
  `tests/test_application_properties_resolution.py` updated (now expects a protocol error, not
  friendly content); README error/"not configured" wording (line ~84) updated.
- **Dependencies**: none new (`openai` and `httpx` are already transitive via
  `langchain-openai` / `aidial-*`; `aidial_sdk.exceptions.HTTPException` is already present).
- **Behavior (BREAKING for API consumers)**: failures change wire shape — a failing turn is now a
  non-200 error or an in-stream error chunk instead of a 200 completion whose content is an error
  sentence. Failed turns no longer produce assistant messages in history. The two app conditions
  render as error states rather than replies. DIAL Chat handles all of this natively; raw API
  consumers that treated failures as successful completions must handle error responses and
  in-stream error chunks, and should classify by `code` (the true cause) rather than by
  `status_code` (which may be downgraded, e.g. a `500` carrying `code: "429"`).
