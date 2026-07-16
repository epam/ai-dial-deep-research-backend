# Log Levels & Content Policy

- **Issue:** [#20](https://github.com/epam/ai-dial-deep-research-backend/issues/20)
  (resolves [#11](https://github.com/epam/ai-dial-deep-research-backend/issues/11))
- **Approach adopted from:**
  [epam/ai-dial-quickapps-backend#434](https://github.com/epam/ai-dial-quickapps-backend/issues/434)

## Why

INFO-level logs say almost nothing about what a request did: nothing records request arrival,
the preparation outcome, research iterations, tool executions, or completion — so a production
incident cannot be triaged at INFO. At the same time there is no policy for what content belongs
in a log record: `PromptLoggingMiddleware` (unwired dead code today) logs complete prompts at
INFO, and the `openai`/`httpx`/`httpcore` loggers follow `LOG_LEVEL`, so raising the level alone
floods aggregated logs with full chat-completion request bodies — a privacy hazard when DEBUG is
enabled in a live environment during an incident.

## What Changes

- **Level semantics** are written down: what DEBUG/INFO/WARNING/ERROR mean for this service,
  including the single-writer ownership rule for ERROR (one failure → one ERROR record, logged
  by the layer that owns final handling — the existing `error_resolution` pattern).
- **An INFO request skeleton** is added: metadata-only lifecycle events (request received,
  preparation completed, per-iteration model activity, tool executions with duration and
  outcome, report generated, request completed) so INFO alone reconstructs what a request did.
- **A content rule** (allowlist) applies at all levels, DEBUG included: structure (roles,
  counts, sizes, names, ids, durations, statuses) is allowed; content (message bodies,
  tool-call arguments, response bodies, header values, URL query strings) is forbidden.
- **A payload-debugging switch** is added: `LOG_PAYLOADS` (default `false`) and
  `LOG_PAYLOADS_MAX_LENGTH` (default `2000`). `PromptLoggingMiddleware` is wired into both
  agents, emits at DEBUG only when the switch is on, truncated — never as a side effect of a
  log level.
- **Payload-capable third-party loggers** (`openai`, `httpx`, `httpcore`) are capped at INFO
  while `LOG_PAYLOADS=false`, regardless of `LOG_LEVEL`. Operationally **BREAKING** for anyone
  relying on `LOG_LEVEL=DEBUG` to see their wire logs (the cap is the point of the change).
- **Existing call sites are rebalanced** per an audit: routine outcomes demoted to DEBUG,
  content-bearing fields stripped to structure.

Out of scope: the dead tool-schema dump aid
([#10](https://github.com/epam/ai-dial-deep-research-backend/issues/10)) — it writes files,
not log records.

## Capabilities

### New Capabilities

- `logging-policy`: level semantics for the service, the content allowlist rule, the INFO
  request-skeleton event list, the payload-switch gating of the app's own content-bearing
  records (`PromptLoggingMiddleware`), and the level rebalance of existing call sites.

### Modified Capabilities

- `logging-config`: two new env settings (`LOG_PAYLOADS`, `LOG_PAYLOADS_MAX_LENGTH`); the
  managed-logger level rule changes — `openai`/`httpx`/`httpcore` are capped at INFO while
  `LOG_PAYLOADS=false` instead of unconditionally following `LOG_LEVEL`.

## Impact

- `src/dial_deep_research/utils/logging_config.py` — third-party cap.
- `src/dial_deep_research/settings.py` — new settings fields.
- `src/dial_deep_research/utils/prompt_logging.py` — switch-gated, DEBUG, configurable cap;
  wired into the preparation and playground agents and the research graph.
- Skeleton events in `app/completion.py`, `app/preparation/runner.py`,
  `app/research/runner.py`, `app/playground/*`.
- Rebalanced call sites in `app/history.py`, `app/mcp_tools.py`,
  `utils/image_attachments.py`.
- `README.md` env-var table, `.env.example`; `CLAUDE.md` gets the policy conventions.
- No API changes. Log wording is not a stable interface, but scraping keyed on current
  records needs adjustment; INFO volume grows by the skeleton and shrinks by demotions.
