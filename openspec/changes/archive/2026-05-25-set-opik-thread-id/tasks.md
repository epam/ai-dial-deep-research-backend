## 1. Extraction helper

- [x] 1.1 Add `extract_thread_id(request)` in `src/dial_deep_research/utils/tracing.py`: today reads `X-CONVERSATION-ID` from `request.headers`, strips it, returns the value if non-empty else `None`; wraps the body in a broad `try/except Exception` returning `None` so any failure path is silent.
- [x] 1.2 Add a one-line docstring noting the name is generic but only DIAL is wired today.

## 2. Tracer wiring

- [x] 2.1 Extend `build_opik_tracer(settings, thread_id=None)` to accept an optional `thread_id` and pass it through to `OpikTracer(thread_id=thread_id)` when not `None`; the disabled-tracing short-circuit stays unchanged.
- [x] 2.2 In `src/dial_deep_research/app/agent.py`, remove the `self._opik_tracer = build_opik_tracer(opik_settings)` line from `__init__`; initialize `self._opik_tracer = build_opik_tracer(opik_settings, thread_id=extract_thread_id(request))` at the top of `run(self, request)` instead.
- [x] 2.3 Update the import block in `agent.py` to bring in `extract_thread_id` alongside `build_opik_tracer`.

## 3. Tests

- [x] 3.1 Add a unit test for `extract_thread_id` covering: (a) header present with non-empty value → returns the trimmed value; (b) header absent → returns `None`; (c) header present-but-empty/whitespace → returns `None`; (d) `request.headers` raises on access → returns `None` (use a mock `Request` to force the failure).

## 4. Verification

- [x] 4.1 Run `make lint` and `make test`; fix any issues.
- [x] 4.2 With `OPIK_TRACING_ENABLED=true` and `make opik-up`, issue two turns of one DIAL conversation through the chat UI and confirm in the Opik UI that both traces share a single thread (the same `thread_id`, grouped under Threads).
- [x] 4.3 Issue a chat completion without `X-CONVERSATION-ID` (raw curl) and confirm the trace appears, ungrouped, exactly as today.
