## ADDED Requirements

### Requirement: Transient LLM stream drops retried in-app

Every LLM chat-completion call the app makes SHALL be retried in-app when it fails with a
transient mid-stream connection drop — the connection dying after response headers arrived,
surfaced as `httpx.RemoteProtocolError` (peer closed the connection mid-body) or
`httpx.ReadError` (connection reset while reading). The OpenAI client's own `max_retries` covers
only failures before a response starts, so without this a single dropped stream aborts the whole
turn.

This applies to every LLM call surface: the preparation, playground, and researcher agent model
calls; the structured review calls (query review, plan review, research review); and the
report-writing stream. The retry budget is 2 retries per call (3 attempts total) with exponential
backoff and jitter. A retry re-issues the failed call from scratch with the same inputs; partial
tokens the failed attempt already streamed to the user are not retracted, so a retried call MAY
render duplicated partial text in the chat (accepted: observed drops occur at stream start, and a
rare visual duplicate is preferred over losing a long research turn).

When the budget is exhausted, the last exception SHALL propagate unchanged to the top-level
handler and deliver through the DIAL error protocol per **Failures delivered as DIAL protocol
errors**. Exceptions other than the two transient-drop shapes SHALL NOT trigger this retry; they
keep their existing handling.

#### Scenario: Stream drops once at the start of an agent model call
- **WHEN** an agent model call's stream dies with `httpx.RemoteProtocolError` and the retried
  call succeeds
- **THEN** the turn SHALL complete normally with no error delivered to the user

#### Scenario: Stream drops persistently
- **WHEN** an LLM call fails with `httpx.RemoteProtocolError` on every attempt in the budget
- **THEN** the app SHALL stop after 3 attempts and deliver the failure through the DIAL error
  protocol, resolved as the retryable network-drop message with an error reference

#### Scenario: Report stream drops after partial content
- **WHEN** the report-writing stream drops mid-content and a retry succeeds
- **THEN** the turn SHALL complete with the retried report; content already streamed by the
  failed attempt MAY remain visible above it, and the persisted report SHALL be the retried
  attempt's full text only

#### Scenario: Non-transient failures are not retried in-app
- **WHEN** an LLM call fails with an HTTP status error (e.g. 400) or a timeout
- **THEN** the in-app stream-drop retry SHALL NOT engage; the failure keeps its existing handling
  (the OpenAI client's own retries and the DIAL error protocol)

## MODIFIED Requirements

### Requirement: Failures delivered as DIAL protocol errors

The app SHALL resolve every turn-aborting failure to an accurate, user-safe message and deliver it
through the **DIAL error protocol**, never as fake-success HTTP 200 assistant content. This applies
whether an exception reaches the top-level handler or a known turn-aborting condition holds (a turn
"cannot produce its intended answer").

**Cause resolution.** The app SHALL normalize the failure into a common view (HTTP status, error
`code`, error `type`, internal message, and user-safe `display_message`) extracted best-effort
from the supported exception shapes (`openai` LLM errors, `aidial_sdk.exceptions.HTTPException`,
raw `httpx` errors); normalization SHALL be total — a malformed or absent error body yields an
empty view, never a second exception. The app SHALL then choose the user-facing message by a fixed
precedence, most-specific first:

1. the upstream's own `display_message`, used verbatim (rendered as plain text and length-capped),
   with nothing appended;
2. a curated error-`code` map (at least `content_filter` and `context_length_exceeded`);
3. a status/type map with wording specific to the failing surface (AI model vs a required
   service), including timeout, connectivity, and mid-stream connection-drop causes — a
   transport-level stream drop (`httpx.RemoteProtocolError`, reaching the resolver only after
   the in-app retries per **Transient LLM stream drops retried in-app** are exhausted) SHALL
   resolve to the retryable service network-error message, never the generic non-retryable HTTP
   fallback;
4. a dedicated mid-stream rule for a plain `openai.APIError` (an LLM that failed after the report
   node began streaming) that carries no usable status or code;
5. curated messages for known internal conditions (research step-budget exhaustion; the two
   turn-aborting app conditions below);
6. a generic fallback.

Each resolution SHALL be classified retryable or not; the app SHALL append a single "try again
later" sentence only to retryable resolutions, and SHALL NOT append it to a `display_message`
resolution or to any non-retryable resolution (which carries its own advice). User-facing text
SHALL contain only the upstream `display_message` (user-safe by DIAL contract) or curated wording
— never a raw stack trace, endpoint, header, or the internal error message.

**Error reference.** Every failure handled at the top level SHALL be stamped with a short opaque
reference (8 hex characters) that appears in both the user-facing message (suffixed as
`(error reference: <ref>)`) and a single server log record that also carries the stack trace, the
normalized internal details, and the retryable classification.

**Delivery.** The handler SHALL raise `aidial_sdk.exceptions.HTTPException` built from the
resolution (`display_message` and `message` both set to the composed user-facing text + reference;
`code` and `type` propagated from the normalized details) so the SDK delivers it as a non-200
error body (for non-streaming requests, or failures before the choice opens) or as an in-stream
`{"error": ...}` chunk terminating the open 200 stream (for streaming requests, i.e. any failure
after the choice opens). Any partial report content already streamed SHALL remain visible with the
error rendered beneath it. The app SHALL NOT append the error as ordinary assistant `content`, and
SHALL NOT persist state on a turn that aborts.

**Outgoing-status policy.** The app SHALL NOT emit a status DIAL Core's balancer treats as
retriable (429, 502, 503, 504). A client-attributable status (one of 400, 401, 403, 404, 409, 413,
422) SHALL pass through; every other cause — upstream rate limits and outages, stream failures,
timeouts, unknown internal errors — SHALL be emitted as 500. The true cause SHALL be preserved in
`code`, so a 500 MAY carry `code: "429"`; consumers classify by `code`, not `status_code`.

**Turn-aborting app conditions.** The two outcomes that previously rendered as friendly assistant
content SHALL instead be delivered as protocol errors: an application whose properties cannot be
**validated** (unconfigured) SHALL resolve to a non-retryable "not configured — contact your
administrator" message (outgoing 500), and a conversation whose research has already been handed
off SHALL resolve to a non-retryable "start a new conversation" message (outgoing 409). A failure
to **fetch** the properties from DIAL Core (as opposed to validate them) SHALL propagate to the
top-level handler and resolve through the status/type map to a service message, rather than being
reported as "not configured".

**Absorbed failures are unaffected.** Failures that are deliberately swallowed and never abort the
turn SHALL NOT trigger this path: per-tool errors caught by `handle_tool_error` (surfaced as an
`error ❌` stage), Opik-tracing failures, and image-rehydration failures. These continue to let the
turn complete normally.

#### Scenario: Upstream failure carrying a display message
- **WHEN** an LLM call fails with an error whose DIAL body carries a `display_message`
- **THEN** the app SHALL deliver that `display_message` verbatim (plain text, length-capped) as the
  user-facing error text with the error reference appended, and SHALL NOT append a "try again
  later" sentence to it

#### Scenario: LLM failure mid-stream after partial content
- **WHEN** the report node has already streamed some assistant content and the LLM then fails
  mid-stream (a plain `openai.APIError` with no usable status/code)
- **THEN** the app SHALL deliver an in-stream `{"error": ...}` chunk terminating the stream, the
  already-streamed partial content SHALL remain visible, and the error text SHALL be the dedicated
  mid-stream message (retryable, so "try again later"-suffixed) plus the error reference — never the
  generic fallback

#### Scenario: Exhausted stream-drop retries resolve retryable
- **WHEN** an LLM call fails with `httpx.RemoteProtocolError` after the in-app retry budget of
  **Transient LLM stream drops retried in-app** is exhausted
- **THEN** the resolved user-facing text SHALL be the service network-error message with the "try
  again later" sentence appended plus the error reference, classified retryable — never the
  generic non-retryable HTTP message

#### Scenario: Context-length and content-filter causes get actionable text
- **WHEN** the model rejects the request with `code: "context_length_exceeded"` or
  `code: "content_filter"`
- **THEN** the code map SHALL resolve it to the actionable message (shorten the messages / rephrase
  the message) ahead of the status ladder, classified non-retryable

#### Scenario: MCP server unreachable
- **WHEN** the MCP server cannot be reached at the configured endpoint during a turn
- **THEN** the app SHALL log the failure with an error reference and deliver a DIAL protocol error
  whose user-facing text is the resolved service/connectivity message plus the reference — not an
  HTTP 200 completion carrying error content

#### Scenario: Genuinely unknown failure is stamped and logged
- **WHEN** an unexpected exception with no usable error body reaches the top-level handler
- **THEN** the app SHALL deliver the generic fallback message suffixed with an error reference, and
  SHALL write one server log record carrying that same reference together with the stack trace, so
  the reference the user reports can be grepped to the log entry

#### Scenario: Never emits a balancer-retriable status
- **WHEN** the resolved cause is an upstream 429, 502, 503, or 504 (or a mid-stream failure whose
  backfilled status is one of these)
- **THEN** the app SHALL emit outgoing HTTP 500 with the true cause preserved in `code` (e.g.
  `code: "429"`), and SHALL NOT emit 429/502/503/504

#### Scenario: Failed turn is kept out of LLM-visible history
- **WHEN** a turn aborts and is delivered as a protocol error
- **THEN** the app SHALL NOT write the error text into assistant `content` and SHALL NOT persist
  turn state, so a subsequent turn (e.g. after DIAL Chat regenerates) does not replay the error
  text to the model

#### Scenario: Unconfigured application delivered as a protocol error
- **WHEN** a request's DIAL application properties cannot be validated
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 500) whose text is
  the "not configured — contact your administrator" message plus an error reference, and SHALL NOT
  run any agent or append the message as assistant content

#### Scenario: Research-already-handed-off delivered as a protocol error
- **WHEN** a request arrives on a conversation whose research was already handed off on an earlier
  turn
- **THEN** the app SHALL deliver a non-retryable protocol error (outgoing HTTP 409) whose text is
  the "start a new conversation" message plus an error reference, and SHALL NOT append that message
  as assistant content nor persist any state for the turn

#### Scenario: Property fetch failure is not masked as "not configured"
- **WHEN** fetching the application properties from DIAL Core fails (e.g. Core unreachable or a
  5xx), as opposed to the properties failing validation
- **THEN** the failure SHALL propagate to the top-level handler and resolve through the status/type
  map to a service message with the appropriate retryability, rather than being reported as "not
  configured"
