# logging-config Delta Spec

## ADDED Requirements

### Requirement: dictConfig-based root logging

The application SHALL configure process logging via `logging.config.dictConfig` with exactly one
console `StreamHandler` on the root logger, whose formatter is the OTEL-aware formatter and whose
level comes from the `LOG_LEVEL` setting. The configuration SHALL use
`disable_existing_loggers: False`, and applying it SHALL be idempotent apart from replacing root
handlers.

#### Scenario: Root owns the single console handler

- **WHEN** `configure_logging` has run
- **THEN** the root logger has exactly one handler, a `StreamHandler` whose formatter is the
  OTEL-aware formatter, and the root level equals the configured `LOG_LEVEL`

#### Scenario: A record is emitted exactly once

- **WHEN** an application logger (e.g. `dial_deep_research.x`) logs an INFO message after
  `configure_logging` has run
- **THEN** the message appears exactly once on the console output

### Requirement: Managed loggers propagate to root

The configuration SHALL pin a fixed, exported set of managed loggers — `dial_deep_research`,
`uvicorn`, `uvicorn.access`, `uvicorn.error`, `httpx`, `httpcore`, `openai`, `aidial_sdk` — each
to an empty handler list and an explicit `propagate: True`, so their records route through the
root logger's handlers. This SHALL undo any prior configuration of those loggers, including the
DIAL SDK's import-time dictConfig (which severs `uvicorn` from root and gives `aidial_sdk` a
private WARNING handler) and the uvicorn CLI's default config. Each managed logger's level SHALL
be the `LOG_LEVEL` setting, except `dial_deep_research`, whose level SHALL be the
`DEEP_RESEARCH_LOG_LEVEL` setting.

#### Scenario: SDK import-time config is overridden

- **WHEN** the DIAL SDK's import-time logging config has been applied and `configure_logging`
  runs afterwards
- **THEN** `uvicorn` and `aidial_sdk` have no handlers of their own and `propagate` is `True`

#### Scenario: Managed loggers reach a root handler exactly once

- **WHEN** a handler is attached to the root logger after `configure_logging` (as the DIAL SDK
  does with its OTLP export handler during `DIALApp` construction) and each managed logger emits
  one record
- **THEN** that handler receives exactly one record per managed logger

#### Scenario: App-logger level pin filters below-threshold records

- **WHEN** `DEEP_RESEARCH_LOG_LEVEL` is at its default (`INFO`) and a `dial_deep_research.*`
  logger emits a DEBUG record
- **THEN** no handler receives the record

### Requirement: OTEL-aware log formatting

The console formatter SHALL subclass `uvicorn.logging.DefaultFormatter` and expose an
`otel_context` field to the format string. When the log record carries an `otelTraceID`
attribute that is truthy and not the literal string `"0"`, `otel_context` SHALL render as
`[trace_id=<id> span_id=<id> resource.service.name=<name> trace_sampled=<bool>] | `; otherwise it
SHALL render as the empty string, so log lines are unchanged when no trace is active.

#### Scenario: No OTEL attributes on the record

- **WHEN** a record without `otelTraceID` is formatted
- **THEN** the output contains no `trace_id=` and ends with the message unmodified

#### Scenario: Instrumentor ran but no span is active

- **WHEN** a record with `otelTraceID == "0"` is formatted
- **THEN** the output contains no `trace_id=` block

#### Scenario: Active trace renders the context block

- **WHEN** a record with a real `otelTraceID`, `otelSpanID`, `otelServiceName`, and
  `otelTraceSampled` is formatted
- **THEN** the output contains the
  `[trace_id=… span_id=… resource.service.name=… trace_sampled=…] | ` block before the message

### Requirement: Env-driven logging settings

The `Settings` model SHALL expose three new fields with default field-name → env-var mapping and
no aliases: `log_format` (`LOG_FORMAT`), defaulting to a pipe-separated format containing
`%(levelprefix)s`, `%(asctime)s`, `%(process)d`, `%(name)s`, `%(otel_context)s`, and
`%(message)s`; `log_date_format` (`LOG_DATE_FORMAT`), defaulting to `%Y-%m-%d %H:%M:%S`; and
`deep_research_log_level` (`DEEP_RESEARCH_LOG_LEVEL`), validated exactly like `log_level` (five
stdlib level names, case-insensitive input, uppercase normalized) and defaulting to `INFO`. The
existing `log_level` field is unchanged.

#### Scenario: Defaults load without environment overrides

- **WHEN** `Settings` is instantiated with none of the three variables set
- **THEN** `log_format` contains `%(otel_context)s`, `log_date_format` equals
  `%Y-%m-%d %H:%M:%S`, and `deep_research_log_level` equals `INFO`

#### Scenario: Date format override reaches the console output

- **WHEN** `LOG_DATE_FORMAT=%H:%M` is set and `configure_logging` runs with the resulting
  settings
- **THEN** the timestamp field of an emitted log line matches `HH:MM`

#### Scenario: App level is independent of the global level

- **WHEN** `DEEP_RESEARCH_LOG_LEVEL=DEBUG` is set and `LOG_LEVEL` is left at `INFO`
- **THEN** `dial_deep_research.*` DEBUG records reach the console while other managed loggers
  (e.g. `httpx`) remain at `INFO`

#### Scenario: Invalid app level is rejected

- **WHEN** `DEEP_RESEARCH_LOG_LEVEL=ifno` is passed to `Settings`
- **THEN** instantiation raises a Pydantic `ValidationError` referencing the
  `deep_research_log_level` field

### Requirement: Ordering relative to the DIAL SDK

The logging configuration module SHALL import `aidial_sdk` before applying its dictConfig, so the
SDK's import-time logging config always lands first and the application config has the last word.
`configure_logging` SHALL run before `DIALApp` construction at the process entry point, so the
OTLP logging handler the SDK attaches to the root logger (when `OTEL_LOGS_EXPORTER` is set) is
not stripped by the application's `dictConfig`.

#### Scenario: Entry point configures logging before building the app

- **WHEN** the process starts via `python -m dial_deep_research`
- **THEN** `configure_logging` executes before `create_app()` is called

#### Scenario: Handlers attached to root after configuration keep receiving records

- **WHEN** a handler is added to the root logger after `configure_logging` has run
- **THEN** subsequent records from managed loggers reach that handler
