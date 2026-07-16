# Proposal: sdk-aware-logging-config

## Why

The app configures logging with a bare `logging.basicConfig`, which silently coexists with the
config the DIAL SDK applies at import time: `uvicorn.*` loggers stay severed from the root logger
(`propagate=False`, private handler), `aidial_sdk` stays pinned to WARNING with its own handler,
and nothing guarantees records flow through root — where the SDK attaches its OTLP export handler
when `OTEL_LOGS_EXPORTER` is set. Log lines also carry no OTEL trace context, so correlating logs
with traces is manual. The quickapps backend already solved all of this with a
`logging.config.dictConfig`-based setup; this change ports that proven design here.

## What Changes

- Replace `logging.basicConfig` in `utils/logging_config.py` with a `dictConfig`-based
  configuration: a single console handler on the root logger, and a fixed set of managed loggers
  (`dial_deep_research`, `uvicorn`, `uvicorn.access`, `uvicorn.error`, `httpx`, `httpcore`,
  `openai`, `aidial_sdk`) pinned to no-handlers + `propagate=True` so every record routes through
  root — including to the OTLP handler the SDK attaches there when `OTEL_LOGS_EXPORTER` is set.
- Add an OTEL-aware formatter (subclass of `uvicorn.logging.DefaultFormatter`) that renders a
  `trace_id`/`span_id` block only when a real trace is active on the record.
- Add env-driven logging settings to the existing `Settings` model: `LOG_FORMAT`,
  `LOG_DATE_FORMAT`, and `DEEP_RESEARCH_LOG_LEVEL` (app-logger level, independent of the global
  `LOG_LEVEL`). Existing `LOG_LEVEL` semantics (five-name validation) are unchanged.
- Guarantee ordering: the logging config imports `aidial_sdk` first (so the SDK's import-time
  `dictConfig` lands before ours) and keeps running before `DIALApp` construction (so the SDK's
  OTLP root handler is not stripped by our `dictConfig`).
- Update the README environment-variables table for the new variables.

No breaking changes: `LOG_LEVEL` keeps its meaning and default; `uvicorn.run(..., log_config=None)`
is already in place.

## Capabilities

### New Capabilities

- `logging-config`: dictConfig-based logging for the whole process — root console handler with
  OTEL-aware formatting, managed loggers propagating to root, env-driven format/level settings,
  and the ordering guarantees relative to the DIAL SDK's own logging setup.

### Modified Capabilities

_None._ `app-config`'s existing `log_level` requirement (five-name validation, `INFO` default) is
untouched; the new settings fields' requirements live in the new `logging-config` spec.

## Impact

- `src/dial_deep_research/utils/logging_config.py` — rewritten (basicConfig → dictConfig +
  formatter class).
- `src/dial_deep_research/settings.py` — three new fields on `Settings`.
- `src/dial_deep_research/__main__.py` — call site updated to pass the new settings.
- `README.md` — environment-variables table gains `LOG_FORMAT`, `LOG_DATE_FORMAT`,
  `DEEP_RESEARCH_LOG_LEVEL`.
- `tests/` — new test module for formatter behavior and record routing.
- No dependency changes: `uvicorn.logging.DefaultFormatter` and the SDK behaviors used are already
  in the tree.
