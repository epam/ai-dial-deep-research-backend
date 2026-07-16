# Tasks: sdk-aware-logging-config

## 1. Settings

- [x] 1.1 Add `log_format`, `log_date_format`, and `deep_research_log_level` fields to
  `Settings` in `src/dial_deep_research/settings.py` (defaults and validation per the
  logging-config spec; reuse the existing `LogLevel` type for the level field)
- [x] 1.2 Extend `tests/test_settings.py` with the new-field scenarios: defaults, level
  independence at the settings layer, and rejection of an invalid
  `DEEP_RESEARCH_LOG_LEVEL`

## 2. Logging configuration

- [x] 2.1 Rewrite `src/dial_deep_research/utils/logging_config.py`: add `OtelAwareFormatter`
  (subclass of `uvicorn.logging.DefaultFormatter` with the conditional `otel_context` block),
  the exported `MANAGED_LOGGER_NAMES` constant, and a `configure_logging(*, log_level,
  app_log_level, log_format, log_date_format)` that applies the dictConfig from the design —
  importing `aidial_sdk` first, with the ordering comments at the definition
- [x] 2.2 Update the `configure_logging` call in `src/dial_deep_research/__main__.py` to
  forward the four settings fields, keeping it before `create_app()`

## 3. Tests for logging behavior

- [x] 3.1 Add `tests/test_logging_config.py` with a snapshot/restore fixture over root plus
  `MANAGED_LOGGER_NAMES`, covering: formatter renders/omits the OTEL block (absent, `"0"`,
  real trace); root owns the single console handler; a record is emitted exactly once;
  SDK import-time config is overridden (`uvicorn`/`aidial_sdk` handler-less, propagating);
  managed loggers reach a post-config root handler exactly once; app-logger DEBUG filtered at
  default level; `LOG_DATE_FORMAT` override reflected in output;
  `DEEP_RESEARCH_LOG_LEVEL=DEBUG` passes app DEBUG records while `httpx` stays at `INFO`

## 4. Docs and hygiene

- [x] 4.1 Update the README environment-variables table: add `LOG_FORMAT`, `LOG_DATE_FORMAT`,
  `DEEP_RESEARCH_LOG_LEVEL` rows next to `LOG_LEVEL`
- [x] 4.2 Run `make format`, `make lint`, and the full test suite; fix anything they surface
