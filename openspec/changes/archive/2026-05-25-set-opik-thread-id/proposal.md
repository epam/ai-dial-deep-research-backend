## Why

Every chat turn currently lands in Opik as its own top-level `LangGraph` trace with no `thread_id`, so the UI shows every turn as an isolated record instead of grouping them under a conversation. Opik's "Threads" view — and per-conversation token totals, annotations, and replay — only activates when traces share a `thread_id`. The DIAL Chat UI already passes a stable conversation identifier on each request via the `X-CONVERSATION-ID` header; we just have to read it and feed it to `OpikTracer`.

## What Changes

- Build the per-request `OpikTracer` with a `thread_id` extracted from the incoming DIAL request, so every turn of one conversation joins a single Opik thread.
- Introduce a thread-id extraction helper named generically (no `dial` in the name); its body, today, only knows how to read DIAL's `X-CONVERSATION-ID`. On any failure — header absent, value empty, request shape unexpected — it returns `None` and the tracer is constructed without a thread id (falling back to today's per-turn behaviour). The generic name leaves the door open for additional sources later, even though we don't expect to add any.
- Move tracer construction out of `AgentRunner.__init__` (which has no `request`) into `run()`, where the request is available.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `dial-agent-with-mcp`: the existing "Opik tracing of agent runs when configured" requirement gains a thread-id behavior — when tracing is enabled and the incoming request carries a DIAL conversation id, the tracer SHALL be constructed with that id as `thread_id`; when the id is unavailable for any reason, tracing SHALL continue without a `thread_id` (no failure surfaced to the user).

## Impact

- Code: `src/dial_deep_research/utils/tracing.py` (extend `build_opik_tracer` signature with `thread_id`; add `extract_thread_id(request)` helper that today handles DIAL only); `src/dial_deep_research/app/agent.py` (move tracer construction into `run()` so it can read the request).
- No new dependencies, no config changes (`OpikSettings` unchanged), no DIAL/MCP protocol changes.
- Behavioural change visible only inside Opik UI: turns of one DIAL conversation now appear as one thread instead of N isolated traces. When the conversation id is absent (raw API client, eval harness, future non-DIAL callers), behaviour is identical to today.
- Tests: a small unit test on `extract_thread_id` covering the happy path, the missing-header path, and an unexpected-shape path returning `None`.
