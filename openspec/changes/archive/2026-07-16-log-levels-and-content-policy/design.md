# Design: Log Levels & Content Policy

Adopts the policy designed in
[epam/ai-dial-quickapps-backend#434](https://github.com/epam/ai-dial-quickapps-backend/issues/434),
adapted to this service's flow (preparation agent → research graph → report; optional
playground channel).

## Context

INFO-level logs say almost nothing about what a request did. The lifecycle — request arrival,
the preparation outcome, research iterations, tool executions, report generation, completion —
produces no records at any level. Meanwhile nothing states what content may appear in a log
record:

- `utils/prompt_logging.py` (`PromptLoggingMiddleware`) logs complete prompts — system message,
  full conversation, tool payloads — at INFO. It is unwired dead code today (issue #11), but
  nothing prevents wiring it up as-is.
- The `sdk-aware-logging-config` change pinned `openai`/`httpx`/`httpcore` to `LOG_LEVEL`, so
  `LOG_LEVEL=DEBUG` alone floods aggregated logs with complete chat-completion request bodies —
  the `openai` client logs them at DEBUG. DEBUG is routinely enabled in live environments during
  incidents.

### Audit of current call sites

The full inventory of today's log records (the design's first input):

| Group | Sites | Assessment |
|---|---|---|
| Startup summaries | `factory.py` (app created, playground registered), `tracing.py` (Opik configured) | Correct — one-time, structural. |
| Per-request tool loading | `mcp_tools.py` (per-server fetch/filter summary, totals — 3 INFO sites) | Correct — metadata-only (tool names are structure). |
| Recoverable conditions | `nodes.py` (report stream-drop retry, WARNING), `image_attachments.py` (upload/download failure placeholders, 2 WARNINGs), `error_resolution.py:266` (extraction fallback, DEBUG) | Right level; the download record logs a URL un-stripped. |
| History fallbacks | `history.py` — "No custom content found" (WARNING), "Custom content is not a dictionary" (WARNING), "Failed to validate DIAL state" (`logger.exception` → ERROR) | Wrong levels — the first two are routine legacy-turn fallbacks; the third is a handled, degraded continue. The pydantic error text also embeds persisted conversation content. |
| Config validation | `properties.py` ("application properties failed validation", WARNING with full `ValidationError`) | Right level (hands onward to the final owner), wrong shape — pydantic renders input values, which may include client prompt content. |
| Model construction | `llm.py` ("Creating chat model with params", INFO) | Routine per-request noise — belongs at DEBUG. (`api_key` is a `SecretStr`, so it is already masked.) |
| Payload dump | `prompt_logging.py` (full LLM request, INFO) | Content-rule violation; unwired today. |
| The single ERROR | `error_resolution.py:456` (`error_reference`, stack trace) | Correct — already implements the ownership rule. |
| Request lifecycle | — | **Absent entirely.** Nothing records arrival, preparation outcome, iterations, tool executions, or completion. |

## Goals / Non-Goals

**Goals:**

- INFO alone reconstructs what a request did during an incident: arrival, preparation outcome,
  each model call, each tool execution by name with duration and outcome, each research
  iteration's verdict, completion.
- No user/AI message content, tool-call argument values, response bodies, header values, or URL
  query strings are emitted by this repo's own call sites at **any** level — including DEBUG.
  Payload-capable third-party loggers are capped so raising a log level alone never brings
  payloads into the pipeline.
- Payload-bearing debug logging exists only behind an explicit opt-in switch, with truncation.
- Level semantics are written down once (the `logging-policy` spec) so reviews can enforce them.
- Existing mislevels are fixed so the INFO channel stays readable.

**Non-Goals:**

- The dead tool-schema dump aid (issue #10) — writes files, not log records.
- Structured JSON log output and request-scoped correlation ids — OTEL log correlation already
  stamps trace ids on every record when enabled (`otel_context` in the format); the event shape
  (stable prefix + `key=value` fields) keeps a later JSON mode possible without rewording.
- What DIAL stages show end users (stages intentionally display tool args and results to the
  requesting user) — a product surface, not server logs; needs its own policy if ever revisited.
- Metrics, tracing, and log-based alerting.

## Decisions

### 1. Level semantics

| Level | Meaning for this service | Examples |
|---|---|---|
| **DEBUG** | Developer diagnostics: control flow, intermediate values, structure summaries. Subject to the content rule like every level — payload content only via the payload switch. | Chat-model construction params, history-fallback records, payload records (switch on) |
| **INFO** | The operational narrative: startup/configuration summaries plus the per-request skeleton below. Metadata-only; bounded volume per request. | Request received, model call, tool executed, iteration reviewed, request completed |
| **WARNING** | Something unexpected happened and the service handled it; the request continues, possibly degraded. Patterns deserve attention; single occurrences don't. | Stream-drop retry, image upload/download fallback, invalid persisted state, app-properties validation failure (handed onward) |
| **ERROR** | A failure that affected the request outcome; each occurrence is worth investigating. | The `error_resolution` record with `error_reference` and stack trace |

**Ownership rule for ERROR:** a failure is logged at ERROR exactly once, by the layer that owns
its final handling. A layer that hands the failure onward — to a fallback path or by raising for
an upstream handler — logs at WARNING or not at all. In this service the final owner is
`raise_dial_error` (`error_resolution.py`), which already emits the single ERROR with an 8-char
`error_reference`. `properties.py` (validation WARNING, then raises) and `history.py` (fallback
to visible-text history) are hands-onward layers.

### 2. The INFO event list — the request skeleton

One request at INFO produces the following events, each metadata-only, as a stable message
prefix plus `key=value` fields. Owners are the components that already have the data:

| # | Event | Owner | Fields |
|---|---|---|---|
| 1 | Request received | a shared turn-lifecycle wrapper both chat completions run their turn through | deployment, message count |
| 2 | Preparation completed | `DeepResearchCompletion` (after the prep runner) | duration, `research_started`, plan step count, outstanding question count |
| 3 | Model call completed | new `ModelCallLoggingMiddleware` on all three `create_agent` graphs (preparation, researcher, playground) | agent name, duration, finish kind (tool calls / final answer), requested tool names, content length, token usage when available |
| 4 | Tool call completed | the runners' `_handle_tool_message` (the same choke point that creates the DIAL stage), through one shared event renderer | tool name, tool_call_id, duration, outcome (`success`/`error`) |
| 5 | Iteration reviewed | reviewer node | iteration number, duration, verdict (`continue`/`report`), next-plan step count |
| 6 | Report generated | report node | duration, report length |
| 7 | Request completed | the turn-lifecycle wrapper; on failure `raise_dial_error` emits it with the reference | outcome (`completed`/`failed`), total duration, `error_reference` on failure |

Notes:

- **MCP tool loading keeps its existing INFO records** (`mcp_tools.py`) — they are the
  "research/playground initialized" part of the skeleton and already metadata-only.
- **No separate "tool call started" event.** Event 3 lists the requested tool names; a hung tool
  is the requested name with no matching event 4. The `finish_iteration` sentinel gets no
  event 4 (same rule as stages) — iteration boundaries are event 5's job; it logs at DEBUG.
- **Model-call events from the researcher are per iteration step**, so a deep research turn
  produces tens of skeleton lines, not 5–10 as in a plain agent. That is proportionate: a
  research turn runs for minutes, and hung/slow model calls are exactly what needs visibility.
- **Reviewer and report nodes make direct LLM calls** (not via `create_agent`), so the
  middleware does not cover them; their own events (5, 6) carry the duration instead.
- **On failure, ERROR complements the skeleton.** The existing `error_reference` record remains
  the single ERROR; event 7 fires with `outcome=failed` and the same reference (small refactor:
  `raise_dial_error` gains the turn start time so it can emit event 7 alongside the ERROR).
- **The retry middleware sits inside the logging middleware**, so a retried model call produces
  one event 3 whose duration includes the retries (the retry itself is already a WARNING).

### 3. The content rule

Applies to **all** levels, DEBUG included.

**Allowed (structure):** roles; counts and sizes/lengths; durations; tool, deployment, model,
and agent names; identifiers (tool_call_id, `error_reference`, trace ids); statuses and outcome
enums; error codes and types; finish reasons; MIME types; HTTP status codes; header **names**;
URLs stripped to scheme, host, and path.

**Forbidden (content):** user/system/assistant/tool message bodies; tool-call argument values;
tool and LLM response bodies; attachment content; header **values**; URL query strings and
fragments (signed URLs and tokens live there).

Boundary cases:

- **URLs.** Log scheme + host + path only. DIAL relative file paths (`files/...`) are
  identifying metadata and may be logged as-is once any query string is stripped.
- **Exceptions.** Stack traces and third-party exception text are permitted — they are the
  diagnostic. The corollary is that our own code must not embed payload content in exception
  messages.
- **Pydantic `ValidationError` over content-bearing input** (persisted conversation state,
  application properties containing client prompts) is the exception to the exception: pydantic
  renders input values into the error text, so these records log the error count and the `loc`
  paths with error types — structure — never the rendered error or `exc_info` of the
  `ValidationError` itself.

The rule is an **allowlist**: when in doubt, a value is content.

### 4. The payload-debugging switch

| Variable | Default | Semantics |
|---|---|---|
| `LOG_PAYLOADS` | `false` | When `false`, content-bearing records are not emitted at all — at any level. When `true`, they are emitted at DEBUG. |
| `LOG_PAYLOADS_MAX_LENGTH` | `2000` | Per-string character cap applied to every payload value when the switch is on; longer values are truncated with an ellipsis marker. Inert when `LOG_PAYLOADS=false`. |

Both live in `Settings` with the default field-name → env-var mapping. The generic `LOG_` prefix
(not `DEEP_RESEARCH_`) is deliberate: like `LOG_LEVEL` and `LOG_FORMAT`, the switch governs the
whole pipeline, including the third-party cap.

- **The switch is additive to the level**: payload records are DEBUG-level, so content appears
  only when both `DEEP_RESEARCH_LOG_LEVEL=DEBUG` and `LOG_PAYLOADS=true` are set. Raising a
  level alone never reveals payloads.
- **`PromptLoggingMiddleware` becomes the app-side payload record** (resolves #11): moved to
  DEBUG, truncation cap from settings, and wired into all three `create_agent` graphs via a
  helper that returns the middleware only when `LOG_PAYLOADS=true` — zero overhead when off.
- **Payload-capable third-party loggers are gated by the same switch.** While
  `LOG_PAYLOADS=false`, `configure_logging` caps `openai`, `httpx`, and `httpcore` at INFO
  (the more severe of `LOG_LEVEL` and INFO); setting the switch lifts the cap and `LOG_LEVEL`
  applies as before. Their records are emitted as-is — the truncation cap governs only this
  repo's own records. Wire-level third-party debugging now requires the same opt-in as payload
  debugging, because it *is* payload debugging.
- **Reviewer/report prompts** are not covered by the middleware; payload debugging for them
  goes through the `openai` logger at DEBUG under the same switch.
- `README.md` documents both variables with an explicit warning that the switch is for local
  development and must not be enabled in shared environments.

### 5. Level rebalance — disposition of existing records

| Site | Current | New | Rationale |
|---|---|---|---|
| `history.py` "No custom content found" | WARNING | DEBUG | Routine fallback for legacy/plain assistant turns |
| `history.py` "Custom content is not a dictionary" | WARNING | DEBUG | Same routine fallback |
| `history.py` "Failed to validate DIAL state" | ERROR (`exception`) | WARNING, structure only | Handled degraded continue (ownership rule); pydantic text embeds conversation content |
| `properties.py` app-properties validation | WARNING (full error) | WARNING, structure only | Level right — hands onward; shape leaks client prompt content |
| `llm.py` "Creating chat model with params" | INFO | DEBUG | Routine per-request construction; deployment name reaches the skeleton via event 3 |
| `prompt_logging.py` LLM request dump | INFO (unwired) | DEBUG behind `LOG_PAYLOADS` | The payload switch record (§4) |
| `image_attachments.py` download failure | WARNING | WARNING, URL stripped | Level right; query string may carry signatures |
| All other audited sites | — | unchanged | Correct per the audit |

### 6. Where the policy lives

The durable policy (level semantics, content rule, skeleton, switch) is the new
`logging-policy` spec. `CLAUDE.md` gets a one-line convention pointing at it — the spec stays
the single source of truth. The `logging-config` spec is amended for the settings fields and the
third-party cap.

## Risks / Trade-offs

- [Operators lose `LOG_LEVEL=DEBUG` wire logs for `openai`/`httpx`/`httpcore`] → Documented in
  the README; the cap is the point of the change — those logs are payload dumps.
- [Scraping/alerting keyed on current wording breaks] → Log messages are not a stable
  interface; the skeleton's stable-prefix + `key=value` shape is the better hook, called out in
  the change notes.
- [Researcher model-call events inflate INFO volume on long research turns] → Bounded by the
  iteration cap and recursion limit; each event is one line of structure. Accepted for
  incident visibility.
- [The logging middleware could drift from the runners' stage bookkeeping] → Event 4 is emitted
  at the same choke point that creates the stage, from the same `PendingToolCall` timing data —
  one owner, no parallel bookkeeping.
- [`LOG_PAYLOADS=true` in a shared environment] → Off by default, DEBUG-level (needs two
  deliberate knobs), truncated, and documented with an explicit warning.

## Migration

- No API changes. Additive env vars; existing deployments see payload dumps *disappear* from
  DEBUG, which is the intended tightening.
- Operationally breaking only for consumers of third-party DEBUG wire logs (now needs
  `LOG_PAYLOADS=true`) and any scraping keyed on the rebalanced records.
