## Context

Opik's `OpikTracer` accepts an optional `thread_id` kwarg. When two traces share a `thread_id`, the Opik UI groups them under its Threads view; without it, every trace stands alone. Today `utils/tracing.py:18` constructs `OpikTracer()` with no arguments, so each chat turn becomes its own record.

The DIAL Chat UI generates a stable `chatReference` per conversation and forwards it as `X-CONVERSATION-ID` on every chat-completion call (verified from `ai-dial-chat`'s `getApiHeaders`). DIAL Core proxies the header through to the deployment, where `aidial_sdk` exposes it on `request.headers` (it survives the stripping that pulls out `Api-Key` and `Authorization` into `SecretStr` fields). `request.headers` is a `Starlette` headers mapping — case-insensitive lookup, `.get()` returns `None` when absent.

Constraint: not every caller goes through the DIAL Chat UI. Raw API clients, the eval harness, and ad-hoc curl invocations will not carry the header. Tracing must keep working in those cases — just without thread grouping.

## Goals / Non-Goals

**Goals:**
- Group all turns of one DIAL conversation under one Opik thread.
- Keep tracing functional (and identical to today) when the conversation id is absent.
- Keep the extraction helper neutrally named so a future second source can slot in, even though we don't expect to add one.
- No surface change to `OpikSettings`, no new env vars, no new deps.

**Non-Goals:**
- Persisting or normalizing the conversation id beyond what DIAL provides — we use it verbatim.
- Adding tags / metadata / per-turn structured attributes to traces; out of scope for this change.
- Supporting non-DIAL transports today. The helper's shape allows future sources, but only DIAL is wired in now.
- Plumbing the conversation id into application logs (only into the Opik tracer).

## Decisions

**Decision: Generic helper name, DIAL-only body.**
The function is named `extract_thread_id(request)` (not `extract_dial_conversation_id`). Inside, it only knows how to read `X-CONVERSATION-ID` from `request.headers`. Rationale: the user explicitly asked for a generic name and a DIAL-only body — the symmetry makes the call site (`build_opik_tracer(settings, thread_id=extract_thread_id(request))`) read as a concept, not as a DIAL artifact, while keeping the implementation honest about what's actually wired up today. Alternative considered: `extract_dial_conversation_id` — rejected because it would force a rename if a second source is ever added, and bakes the transport into the call site for no benefit.

**Decision: Return `None` on any failure path, never raise.**
The helper is wrapped in a single broad `try/except Exception` returning `None`. Failure modes are: header absent (the common non-DIAL case), header empty, `request.headers` shape unexpected, attribute access mismatch on a future SDK version. None of these should fail a chat completion. Tracing-without-grouping is the documented fallback. Alternative considered: structured logging of unexpected-shape cases — declined for now to keep the helper trivial; the existing `friendly error` funnel still catches downstream tracer issues, and a `_log.debug` line in the except block is enough if we want signal.

**Decision: Construct the tracer in `run()`, not in `__init__`.**
`AgentRunner.__init__(model_config, choice)` does not have the request. Move `self._opik_tracer = build_opik_tracer(...)` from `__init__` (line 72 today) to the top of `run(self, request)` (before `_build_agent`). This is a minimal mechanical change — the tracer's lifecycle is already per-request, so this just defers construction by a few statements. Alternative considered: pass `request` into `AgentRunner.__init__` — rejected because the constructor is called from `DeepResearchCompletion.chat_completion` which already has the request, but moving the tracer's life into `run()` keeps `__init__` free of side effects and matches how the agent itself is built lazily there.

**Decision: Threshold for "valid" thread id is non-empty string.**
The helper coerces to `str(value).strip() or None`. A header present-but-empty (`X-CONVERSATION-ID:`) is treated the same as absent. Opik's `thread_id` accepts arbitrary strings — we don't try to validate UUID shape, since DIAL's `chatReference` format is not contractually fixed.

## Risks / Trade-offs

- **[Risk]** Future `aidial_sdk` releases might change how `request.headers` is exposed → **Mitigation:** the broad `except` makes that surface as "no thread grouping" rather than a 500.
- **[Risk]** A poorly behaved client could spoof `X-CONVERSATION-ID` to merge or split threads they don't own → **Mitigation:** acceptable for a tracing-only signal in a single-tenant dev deployment; we don't authorize on this field anywhere. Worth re-evaluating if Opik is ever exposed to end users.
- **[Trade-off]** The helper is intentionally DIAL-aware in its body despite the generic name. A reader scanning for "where do we use DIAL conversation ids?" won't grep-find the helper. Mitigated by a one-line docstring naming DIAL as the current source.
- **[Trade-off]** No logging when the header is absent. Means we won't notice if DIAL ever stops forwarding it. Acceptable: the Opik UI itself surfaces this (traces revert to ungrouped), which is the operator-visible signal.

## Migration Plan

No migration. The change is purely additive — turns without `X-CONVERSATION-ID` are unaffected, turns with it gain thread grouping. No data backfill (past traces stay ungrouped in Opik, which is fine — they're for debugging, not retention). Rollback is a single-file revert of `utils/tracing.py` and `app/agent.py`.

## Open Questions

None. The header name is confirmed from `ai-dial-chat` source; `request.headers` exposure is confirmed from `aidial_sdk.deployment.from_request_mixin`; `OpikTracer(thread_id=...)` is part of `opik.integrations.langchain`'s documented API.
