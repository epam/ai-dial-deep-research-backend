# Design: sdk-aware-logging-config

## Context

Logging today is a bare `logging.basicConfig(level, format)` in
`src/dial_deep_research/utils/logging_config.py`, called from `__main__.py` before
`create_app()`. Meanwhile the DIAL SDK applies its own `dictConfig` at import time
(`aidial_sdk/application.py`): `uvicorn` gets `propagate=False` with a private handler, and
`aidial_sdk` gets a WARNING level with a private handler. Because `basicConfig` only touches the
root logger, those pins survive: SDK and uvicorn records bypass root entirely, and when
`OTEL_LOGS_EXPORTER` is set the OTLP `LoggingHandler` the SDK attaches to root never sees them.
Log lines also carry no trace correlation even though the app already enables SDK telemetry
(`TelemetryConfig` in `app/factory.py`) and the SDK supports `OTEL_PYTHON_LOG_CORRELATION`.

The quickapps backend solved the same problem with `LoggingConfig` + `OtelAwareFormatter` +
`LoggingSettings`; this design ports that shape, adapted to this repo's conventions.

## Goals / Non-Goals

**Goals:**

- One console handler on the root logger; every logger of interest routes through it.
- Records also reach any handler attached to root after configuration — in particular the OTLP
  export handler the SDK adds during `DIALApp` construction.
- OTEL trace context (`trace_id`/`span_id`) in log lines when a trace is active, invisible
  otherwise.
- Env-driven format, date format, global level, and a separate app-logger level.

**Non-Goals:**

- No new telemetry features (exporters, instrumentation) — the SDK already owns those.
- No JSON/structured log output.
- No change to `uvicorn.run(..., log_config=None)` — already correct.
- No separate `LoggingSettings` model (see Decisions).

## Decisions

1. **Own the process logging via `dictConfig`, applied at the existing call site.**
   `configure_logging` keeps its name and call site (`__main__.main()`, before `create_app()`),
   but its body becomes a `logging.config.dictConfig` mirror of quickapps' `LoggingConfig`.
   Ordering is load-bearing in both directions:
   - The module imports `aidial_sdk` before applying its config, so the SDK's import-time
     `dictConfig` always lands first and ours has the last word regardless of caller import
     order.
   - `dictConfig` strips existing root handlers, and the SDK appends its OTLP handler to root
     during `DIALApp` construction — so `configure_logging` must keep running before
     `create_app()`. This is recorded as a comment at the definition.

2. **Managed-logger list pinned to no-handlers + `propagate=True`.**
   `dial_deep_research`, `uvicorn`, `uvicorn.access`, `uvicorn.error`, `httpx`, `httpcore`,
   `openai`, `aidial_sdk` — the quickapps list with the app logger swapped. These are the loggers
   the SDK or uvicorn actively configure, plus the noisy HTTP/LLM clients whose levels we pin.
   `propagate: True` stays explicit because `dictConfig` leaves `propagate` untouched when the
   key is absent, and prior configs (SDK, uvicorn CLI) set it to `False`. Other libraries
   (`langchain`, `langgraph`, `mcp`) don't self-configure handlers, so they inherit root's level
   and handler with no pin needed. The list is a module constant so tests can snapshot/restore
   exactly the touched loggers.

3. **`OtelAwareFormatter` subclasses `uvicorn.logging.DefaultFormatter`, same module.**
   Gives `%(levelprefix)s` and colors for free (the SDK's own format uses the same base). It
   sets `record.otel_context` to a `[trace_id=… span_id=… …] | ` block only when
   `record.otelTraceID` exists and is not the literal `"0"` — the two shapes produced when
   `OTEL_PYTHON_LOG_CORRELATION` is off or no span is active. Unlike quickapps (three files under
   `config/`), formatter and config live together in `utils/logging_config.py`: the formatter is
   only ever referenced by the dictConfig's `"()"` factory key (passed as the class object), and
   this repo is small enough that a package split buys nothing.

4. **Logging settings live on the single `Settings` model.**
   `settings.py` is documented as "the single settings model, all env-driven"; a separate
   `LoggingSettings` (quickapps' choice) would break that and CLAUDE.md forbids new aliases
   anyway. New fields, default env mapping: `log_format` (`LOG_FORMAT`), `log_date_format`
   (`LOG_DATE_FORMAT`), `deep_research_log_level` (`DEEP_RESEARCH_LOG_LEVEL`, `LogLevel`-typed
   like `log_level`). The default format is quickapps' pipe-separated layout with
   `%(otel_context)s` ahead of the message.

5. **`configure_logging` takes keyword-only values, not `Settings`.**
   `configure_logging(*, log_level, app_log_level, log_format, log_date_format)` keeps the util
   importable without a valid environment (`Settings` requires `DIAL_URL`) and keeps tests
   explicit. `__main__` forwards the four fields from `settings`.

## Risks / Trade-offs

- [Global logging state leaks between tests] → tests use a snapshot/restore fixture over root +
  the managed-logger constant (ported from quickapps' `reset_logging_state`).
- [Running the app through the uvicorn CLI would bypass `configure_logging`] → unchanged from
  today; the supported entry point is `python -m dial_deep_research`, and the explicit
  `propagate: True` pins mean even a uvicorn-CLI default config applied *before* ours is fully
  undone.
- [Default log format changes shape (pipes, level prefix first)] → log format is not an API;
  anyone needing the old shape sets `LOG_FORMAT`.
- [`use_colors=True` forces ANSI codes even when output is piped] → mirrors quickapps and the
  SDK's own default config; acceptable for parity, overridable later if an aggregator chokes.

## Migration Plan

Single deploy; no data or config migration. Rollback = revert the commit. Existing `LOG_LEVEL`
values keep working unchanged.

## Open Questions

_None._
