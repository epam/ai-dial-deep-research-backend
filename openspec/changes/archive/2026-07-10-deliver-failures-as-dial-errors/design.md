# Design: deliver-failures-as-dial-errors

## Context

Today `DeepResearchCompletion.chat_completion` wraps the whole turn in one `try/except` inside
`response.create_single_choice()` and, on any exception, logs it and appends a fixed
`_FRIENDLY_ERROR` sentence via `choice.append_content` — completing over HTTP 200. Two
non-exception outcomes inside `_run_turn` are shown the same way, as ordinary assistant content:
`_NOT_CONFIGURED` (when `_load_properties` cannot resolve/validate the DIAL application
properties) and `_RESEARCH_STARTED` (when a prior turn already handed research off).

A turn makes downstream calls from three surfaces, and their errors arrive in a small number of
shapes:

1. **LLM calls** — the prep agent and the research graph's nodes call the DIAL Core LLM endpoint
   through `langchain-openai`'s `AzureChatOpenAI`. Failures surface as `openai.APIError`
   subclasses: `APIStatusError` (4xx/5xx with a status), `APITimeoutError`, `APIConnectionError`,
   and — for a model that dies **after** the report node started streaming — a plain
   `openai.APIError` carrying the DIAL error body but no HTTP status.
2. **DIAL Core file/state operations** — `aidial_client.AsyncDial` (image upload during persist,
   `set_state`) and `request.request_dial_application_properties()` (aidial-sdk). These raise
   `aidial_sdk.exceptions.HTTPException` or `httpx` errors.
3. **The RAG MCP server** — via `langchain-mcp-adapters`; connection/tool failures surface as
   `httpx` errors (per-tool errors are caught by `handle_tool_error` and never bubble).

This is the same problem, and largely the same error shapes, that the QuickApps backend solved
in its *User-Facing Error Message Resolution* change (design:
`ai-dial-quickapps-backend/docs/designs/error_message_resolution.md`; runtime doc:
`docs/error_handling.md`; issue #411, PR #412). This design ports that solution, adapted to two
ways this repo is **simpler**:

- **Stages are synchronous.** `ResearchRunner._handle_tool_message` opens and closes each tool
  stage in one `with self._choice.create_stage(...)` block, with no `await` inside. There is no
  stage held open across the failure point, so there is **no deferred-stage-close registry** to
  fix (QuickApps needed one). An in-flight `with` block still closes as failed when an exception
  propagates through it, which is what we want.
- **No execution-time `finally` stage.** `chat_completion` has no `finally` that appends a
  bookkeeping stage after the turn, so there is nothing to suppress when an error is in flight
  (QuickApps had to gate its execution-time stage behind a failure flag).

## Goals / Non-Goals

**Goals:**
- Surface the upstream's `display_message` whenever one exists, regardless of which client
  library delivered the error.
- Classify by error `code` (`content_filter`, `context_length_exceeded`, …) before falling back
  to status-class messages, so actionable causes get actionable text.
- Handle mid-stream LLM failures (plain `openai.APIError` with a DIAL body) as first-class.
- Stamp every handled failure with an error reference present in both the log and the
  user-facing text.
- Classify each resolution retryable/not and append "Please try again later." only to retryable
  ones.
- Deliver failures through the DIAL error protocol (raise `HTTPException`) so DIAL Chat renders
  an error state, steers to regenerate, and keeps the text out of LLM history.
- Never emit a status DIAL Core's balancer treats as retriable (429/502/503/504).
- Convert both turn-aborting app conditions (`_NOT_CONFIGURED`, `_RESEARCH_STARTED`) to protocol
  errors.
- Never leak raw internal detail (stack traces, endpoints, headers) into user-facing text — only
  `display_message` and curated canned messages.

**Non-Goals:**
- No message catalog / i18n / per-deployment message customization (the module concentrates the
  strings, which is the prerequisite; externalizing them is deferred).
- No error-class telemetry (the `retryable` flag is the natural dimension; wiring it into
  monitoring is deferred).
- No retry-policy changes (the openai client keeps its built-in retries).
- No QuickApps-style error-injection sample app in this change.
- No change to failures that are **deliberately absorbed** and never abort the turn: per-tool
  errors caught by `handle_tool_error`, Opik-tracing failures, and image-rehydration failures.
  These never reach the new handler.
- No deferred-stage-close registry (not needed here — see Context).

## Decisions

### D1 — Port the resolver into a new `app/error_resolution.py`
Add `ErrorDetails` (frozen model: `status_code`, `code`, `error_type`, `message`,
`display_message`), a best-effort/total `_extract_error_details` over the openai / aidial / httpx
shapes (with the openai body unwrap `body.get("error", body)` and the numeric-`code` → status
backfill), `ResolvedError` (frozen model: `message`, `retryable`, `details`), and
`resolve_exception(e) -> ResolvedError` implementing the precedence:

1. `display_message` (sanitized: stripped, plain text, capped ~500 chars; terminal, never
   retry-suffixed).
2. Code map: `content_filter`, `context_length_exceeded`, `truncate_prompt_error` → curated
   non-retryable messages.
3. Status/type map: openai and httpx ladders (AI-model wording vs service wording), keyed on the
   normalized `status_code`; each ladder returns *unresolved* on a miss so precedence continues.
   `APITimeoutError`/`APIConnectionError` type branches resolve here.
4. Stream-failure rule: a plain `openai.APIError` (no `APIStatusError`) unresolved by 1–3 gets a
   dedicated `_MSG_AI_MODEL_STREAM_FAILURE`, retryable — terminal for the mid-stream path.
5. Internal-condition map (see D4).
6. Generic fallback, non-retryable.

All message constants follow the retryability split: retryable-classified constants carry the
cause only (the retry sentence is appended by the resolver exactly once), non-retryable constants
carry cause + specific advice; no constant carries the retry phrase itself.
- *Alternative — keep the single generic sentence.* Rejected: that is the problem.
- *Alternative — depend on / import QuickApps' resolver.* Rejected: separate repos, different
  internal exceptions; a ~200-line self-contained module is clearer than a cross-repo dependency.

### D2 — Deliver via `aidial_sdk.exceptions.HTTPException`, stamped with an error reference
Replace the `choice.append_content(_FRIENDLY_ERROR)` handler with a `__handle_exception` that:
generates an 8-hex-char reference (`uuid.uuid4().hex[:8]`), calls `resolve_exception`, logs one
`logger.exception` record carrying the reference, the resolved `details`, and `retryable`, then
raises `HTTPException(status_code=…, message=display, display_message=display, code=…, type=…)`
where `display = f"{resolved.message} (error reference: {ref})"`. `message` mirrors
`display_message` (DIAL Chat surfaces only `display_message` on the mid-stream path; internal
detail lives in logs, reachable via the reference). The raise propagates out of
`create_single_choice()`; the SDK delivers it as a non-200 body (pre-choice / non-streaming) or an
in-stream `{"error": ...}` chunk (streaming, which is every failure once the choice is open).
- *Verified:* `HTTPException.__init__` accepts `status_code`, `message`, `display_message`,
  `code`, `type`. `Choice.__exit__` returns falsy, so a raise inside the `with` propagates.

### D3 — Outgoing-status policy (never 429/502/503/504)
`_outgoing_status_code(resolved)` returns the resolved `status_code` when it is in the
client-attributable set `{400, 401, 403, 404, 409, 413, 422}`, else `500`. This is the QuickApps
set plus `409` (for the research-already-handed-off condition, D4); `409` is non-retriable by DIAL
Core's balancer, so it passes through safely. The `type` defaults to `invalid_request_error` for
`< 500` and `runtime_error` otherwise when the upstream supplied none. The true cause stays in
`code`, so a `500` may legitimately carry `code: "429"` — consumers classify by `code`, not
`status_code`.
- *Rationale:* DIAL Core retries 429/502/503/504 for the app's single synthetic upstream, cannot
  (retry budget of one), and then discards the app's error body — so emitting those would lose the
  explanation. Verified behavior carried over from the QuickApps design.

### D4 — Represent the two app conditions as internal-condition exceptions
Add two exception types in `app/error_resolution.py`:
- `ApplicationNotConfiguredError` — carries no HTTP status → resolves to the existing
  `_NOT_CONFIGURED` wording, non-retryable → outgoing **500** ("contact your administrator" fits;
  the cause is a deployment/config problem the user cannot fix).
- `ResearchAlreadyHandedOffError` — carries status **409 Conflict** → resolves to the existing
  `_RESEARCH_STARTED` wording, non-retryable → outgoing **409** (the request conflicts with the
  conversation's terminal state; "start a new conversation" is the advice).

`_run_turn` raises these instead of appending content and returning; the internal-condition map
(precedence rule 5) also maps `langgraph.errors.GraphRecursionError` (the research
`_RECURSION_LIMIT` ceiling) to a curated non-retryable message, analogous to QuickApps'
`OrchestratorExceedMaxIterationsException`. On these paths the turn persists **no** state — a
failed/aborted turn leaves no trace, and DIAL Chat drops the error from history on regenerate; the
research-already-handed-off state was already persisted by the turn that ran research, so
re-persisting it is unnecessary.
- *Alternative — raise `HTTPException` directly from `_run_turn` for these two.* Rejected: routing
  them through the same resolver/handler keeps one delivery path and centralizes the message text
  in one module.

### D5 — Split property *fetch* failure from property *validation* failure
`_load_properties` today catches every exception and returns `None`, masking a DIAL Core outage as
"not configured." Change it so a **validation** failure (`ApplicationProperties.model_validate`
raising) becomes `ApplicationNotConfiguredError`, while a **fetch** failure
(`request.request_dial_application_properties()` raising, e.g. Core unreachable/5xx) **propagates**
to `__handle_exception` and resolves through the service/status ladder to an accurate message.
- *Alternative — keep swallowing both as "not configured".* Rejected: it hides a real, retryable
  service outage behind a misleading "ask your administrator to configure the app" message —
  exactly Problem-Statement item 1 of the reference design.

### D6 — No stage/finally hygiene work is needed
Documented here because it is a visible divergence from the QuickApps design: this repo's tool
stages are opened and closed synchronously (D-context), so no deferred-close registry is added,
and `chat_completion` has no execution-time `finally` stage to suppress. An in-flight `with
create_stage(...)` already closes as failed when the exception propagates.

### D7 — Defer stale-vocabulary reconciliation to spec-sync/archive
The delta removes the *Top-level error funnel* requirement and adds the protocol-error
requirement. Three places in the **baseline** `dial-agent-with-mcp` spec still describe the old
funnel with the phrase "friendly error string": the capability **Purpose** paragraph, the
*Reconstruction of LangChain history* → "Rehydration failure does not abort the turn" scenario,
and the *Opik tracing* → "Tracing failure does not break the turn" scenario. The latter two
describe **absorbed** failures whose behavior does not change — only the counterfactual vocabulary
is stale — and the new requirement states the absorbed-failure boundary explicitly, so they are
not contradicted. Rather than restate those two large requirements verbatim (transcription risk)
just to retouch one phrase each, the vocabulary is reconciled by hand at spec-sync/archive time,
mirroring how the `per-request-dial-auth` change deferred its own Purpose/README prose. Tracked in
tasks §5 and Open Questions.

## Risks / Trade-offs

- **Trusting `display_message`.** It is user-safe by DIAL contract and every hop is DIAL-operated
  infrastructure. Mitigated by plain-text rendering and the ~500-char cap; the alternative
  (ignoring it, as today) is the problem being removed.
- **Streaming turns are logged by DIAL Core as 200.** Once the choice opens, every failure is an
  in-stream error chunk over 200, so Core's analytics still see 200 for streaming requests. The
  error chunk is present in the logged body, and the app's own log record (keyed by the error
  reference) gives full operator visibility. Still a strict improvement over today, where the
  failure is indistinguishable from success in both places.
- **`aidial_client` error shapes.** If `AsyncDial` raises something that is neither an
  `aidial_sdk` `HTTPException` nor an `httpx` error, extraction yields empty `ErrorDetails` and the
  turn resolves to the generic fallback (still stamped, still logged, still a protocol error).
  Verify the actual shapes during implementation (Open Questions).
- **Wire-shape change is breaking for raw API consumers** (see proposal Impact). DIAL Chat is
  unaffected; a raw consumer that read error text out of the completion must switch to reading the
  error response / in-stream error chunk and classify by `code`.

## Migration Plan

- **Deployment/config**: none — no env vars, no schema, no DI changes. Deploying the new build is
  the whole migration.
- **Rollback**: revert the code change; behavior returns to the friendly-content funnel. Code-only,
  no data migration.
- **Consumers**: DIAL Chat needs nothing. Non-Chat/API consumers must handle non-200 errors and
  in-stream `{"error": ...}` chunks and classify by `code`.

## Open Questions

- What exception types does `aidial_client.AsyncDial` raise for Core 4xx/5xx and network failures
  (httpx passthrough vs a wrapped type)? Confirm the extractor covers them; extend
  `_extract_error_details` if a new shape appears. (Resolve during implementation.)
- The `dial-agent-with-mcp` **Purpose** paragraph and the two absorbed-failure scenarios still say
  "friendly error string" / "HTTP 200" (see D7). These are reconciled by hand at spec-sync/archive;
  confirm the exact replacement wording then.
- README line ~84 ("A request without valid properties gets a friendly 'not configured' reply.")
  and `tests/test_application_properties_resolution.py` assert the old friendly-content behavior;
  both are updated to expect a protocol error (tasks §4, §5).
