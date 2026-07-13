# Tasks: deliver-failures-as-dial-errors

## 1. Error-resolution module (`app/error_resolution.py`)

- [x] 1.1 Add `ErrorDetails` (frozen pydantic model: `status_code: int | None`, `code: str | None`, `error_type: str | None`, `message: str | None`, `display_message: str | None`). `error_type` never influences resolution; it is forwarded to the log record and the outgoing wire `type` only.
- [x] 1.2 Add `ResolvedError` (frozen model: `message: str`, `retryable: bool`, `details: ErrorDetails`).
- [x] 1.3 Add the message constants, split by retryability: retryable-classified constants carry the cause only; non-retryable constants carry cause + specific advice; **no** constant carries the retry phrase. Include an AI-model family, a service family, `_MSG_AI_MODEL_STREAM_FAILURE`, the code-map messages (content-filter, context-length), and `_FALLBACK_MESSAGE`.
- [x] 1.4 Add the code map (`content_filter`, `context_length_exceeded`, `truncate_prompt_error`), all non-retryable.
- [x] 1.5 Implement the best-effort/total extractor: `_unwrap_error_body` (`body.get("error", body)`), numeric-`code` → `status_code` backfill, and per-shape extraction for `openai.APIError` (status from the exception, other fields from the unwrapped body), `aidial_sdk.exceptions.HTTPException` (native attributes), and `httpx.HTTPStatusError` (status + best-effort JSON body). Malformed/absent bodies yield empty `ErrorDetails`, never an exception.
- [x] 1.6 Implement `resolve_exception(e) -> ResolvedError` with the precedence: `display_message` (sanitized: stripped, plain text, capped ~500 chars; terminal, never retry-suffixed) → code map → status/type map (openai + httpx ladders returning unresolved on a miss) → stream-failure rule (plain `openai.APIError`, not `APIStatusError`) → internal-condition map (§2) → fallback. Append `"Please try again later."` exactly once, only for retryable resolutions.
- [x] 1.7 Confirm the module leaks no raw internal detail: only `display_message` and curated constants can reach `ResolvedError.message`; `ErrorDetails.message` (internal) is never used for user text. (Covered by `test_internal_message_never_leaks_into_user_text`.)

## 2. Internal-condition exceptions and the two app conditions

- [x] 2.1 In `app/error_resolution.py`, define `ApplicationNotConfiguredError` (no status; message = today's `_NOT_CONFIGURED` wording; non-retryable) and `ResearchAlreadyHandedOffError` (status 409; message = today's `_RESEARCH_STARTED` wording; non-retryable).
- [x] 2.2 In the internal-condition map (precedence rule 5), resolve `ApplicationNotConfiguredError`, `ResearchAlreadyHandedOffError`, and `langgraph.errors.GraphRecursionError` (curated non-retryable "research exceeded its step budget" wording) to their messages.
- [x] 2.3 In `app/completion.py`, `_run_turn` raises `ResearchAlreadyHandedOffError` where it currently appends `_RESEARCH_STARTED` and persists — **removed** that `choice.append_content` + `_persist` (no state persisted on this path).
- [x] 2.4 In `app/completion.py`, split `_load_properties` (D5): a `model_validate` failure raises `ApplicationNotConfiguredError`; a fetch failure from `request_dial_application_properties()` propagates unchanged. `_run_turn` no longer branches on a `None` return / appends `_NOT_CONFIGURED`.

## 3. Protocol-error delivery in `app/completion.py`

- [x] 3.1 Add `_outgoing_status_code(resolved)` returning the resolved status when in `{400, 401, 403, 404, 409, 413, 422}`, else `500`.
- [x] 3.2 Add `_raise_dial_error(e)`: generate an 8-hex-char reference (`uuid.uuid4().hex[:8]`), `resolve_exception(e)`, log one `logger.exception` record with the reference + `details` + `retryable`, then raise `aidial_sdk.exceptions.HTTPException` with `display_message` = `message` = `"{resolved.message} (error reference: {ref})"`, `status_code` from §3.1, `code` from `details.code`, `type` from `details.error_type` else `invalid_request_error`(<500)/`runtime_error`(≥500).
- [x] 3.3 Rewrite `chat_completion`: keep `with response.create_single_choice() as choice`, wrap `_run_turn` in `try/except Exception as e: _raise_dial_error(e)`. Removed `_FRIENDLY_ERROR` and the `choice.append_content(_FRIENDLY_ERROR)` call.
- [x] 3.4 Confirm no state is persisted when the turn aborts (the raise leaves `chat_completion` before `_persist`).

## 4. Tests

- [x] 4.1 Resolver unit tests: extraction from each shape (openai `APIStatusError`, plain mid-stream `APIError`, `aidial` `HTTPException`, `httpx.HTTPStatusError`), the openai body-unwrap, and the numeric-`code` → status backfill.
- [x] 4.2 Precedence tests: `display_message` wins and is not retry-suffixed; `content_filter` / `context_length_exceeded` resolve via the code map; a status ladder miss falls through; a mid-stream `APIError` with no usable body hits the stream-failure rule; unknown → fallback.
- [x] 4.3 Retryability tests: retryable resolutions end with "Please try again later." exactly once; non-retryable ones carry their own advice and no retry phrase.
- [x] 4.4 No-leak test: for an exception carrying internal detail (stack text, endpoint) the resolved `message` contains none of it — only the sanitized display message or a curated constant.
- [x] 4.5 Handler tests: the delivered `HTTPException` carries `display_message` ending `(error reference: <8 hex>)`; the outgoing status is downgraded per §3.1 (e.g. an upstream 429/503 → 500 with `code` preserved) and never 429/502/503/504.
- [x] 4.6 App-condition tests: an unconfigured request and a research-already-handed-off request each deliver a protocol error (not friendly content), non-retryable, with the expected status (500 and 409); the handed-off turn persists no state (the 409 error response carries no choice/state).
- [x] 4.7 Update `tests/test_application_properties_resolution.py` — invalid/missing properties now produce a protocol error, not friendly assistant content; a *fetch* failure resolves to a service message, not "not configured".
- [x] 4.8 Boundary: swallowed Opik-tracing / image-rehydration / per-tool errors do **not** reach the funnel — covered by existing `test_thread_id_extraction` (extractor is total) and `test_image_attachments` (rehydration/upload failures replace with a text placeholder and proceed); `test_valid_properties_reach_the_prep_agent` confirms a successful turn stays 200. `make test` is green (130 passed).

## 5. Docs and spec reconciliation

- [x] 5.1 README: updated the "not configured" wording (line ~84) to describe protocol-error delivery instead of a friendly reply. Environment-variables table unchanged (no env vars added/removed).
- [x] 5.2 Reconciled the stale "friendly error string" / funnel vocabulary in the baseline `dial-agent-with-mcp` spec at archive time: Purpose paragraph (now describes protocol-error delivery), *Reconstruction of LangChain history* rehydration-failure scenario, and the *Opik tracing* requirement + tracing-failure scenario. Behavior unchanged, only vocabulary (design D7).

## 6. Verify and finalize

- [x] 6.1 `make format` and `make lint` are clean.
- [ ] 6.2 End-to-end on the local stack: trigger an LLM failure and confirm DIAL Chat renders an error state (red box), partial report content stays visible, and the reference appears in both the chat text and the server log. Confirm the unconfigured and research-already-handed-off paths render as errors. (Requires the running stack — not run here.)
- [x] 6.3 `openspec validate --change deliver-failures-as-dial-errors --strict` passes.
