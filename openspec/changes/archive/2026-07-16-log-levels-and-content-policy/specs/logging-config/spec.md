# logging-config

## MODIFIED Requirements

### Requirement: Managed loggers propagate to root

The configuration SHALL pin a fixed, exported set of managed loggers — `dial_deep_research`,
`uvicorn`, `uvicorn.access`, `uvicorn.error`, `httpx`, `httpcore`, `openai`, `aidial_sdk` — each
to an empty handler list and an explicit `propagate: True`, so their records route through the
root logger's handlers. This SHALL undo any prior configuration of those loggers, including the
DIAL SDK's import-time dictConfig (which severs `uvicorn` from root and gives `aidial_sdk` a
private WARNING handler) and the uvicorn CLI's default config. Each managed logger's level SHALL
be the `LOG_LEVEL` setting, with two exceptions: `dial_deep_research`, whose level SHALL be the
`DEEP_RESEARCH_LOG_LEVEL` setting, and the payload-capable loggers `openai`, `httpx`, and
`httpcore`, whose level SHALL be capped at INFO (the more severe of `LOG_LEVEL` and INFO) while
`LOG_PAYLOADS` is false — these loggers emit request/wire payloads at DEBUG, so raising
`LOG_LEVEL` alone SHALL never bring payloads into the pipeline. When `LOG_PAYLOADS` is true, the
cap is lifted and `LOG_LEVEL` applies to them as to any managed logger.

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

#### Scenario: Payload-capable loggers are capped at INFO while the switch is off

- **WHEN** `LOG_LEVEL=DEBUG` and `LOG_PAYLOADS` is false (the default) and `configure_logging`
  runs
- **THEN** `openai`, `httpx`, and `httpcore` DEBUG records reach no handler, while other managed
  loggers' DEBUG records reach the console

#### Scenario: The payload switch lifts the cap

- **WHEN** `LOG_LEVEL=DEBUG` and `LOG_PAYLOADS=true` and `configure_logging` runs
- **THEN** `openai`, `httpx`, and `httpcore` DEBUG records reach the console

#### Scenario: The cap never lowers a stricter global level

- **WHEN** `LOG_LEVEL=WARNING` and `LOG_PAYLOADS` is false and `configure_logging` runs
- **THEN** `openai`, `httpx`, and `httpcore` INFO records reach no handler

### Requirement: Env-driven logging settings

The `Settings` model SHALL expose logging fields with default field-name → env-var mapping and
no aliases: `log_format` (`LOG_FORMAT`), defaulting to a pipe-separated format containing
`%(levelprefix)s`, `%(asctime)s`, `%(process)d`, `%(name)s`, `%(otel_context)s`, and
`%(message)s`; `log_date_format` (`LOG_DATE_FORMAT`), defaulting to `%Y-%m-%d %H:%M:%S`;
`deep_research_log_level` (`DEEP_RESEARCH_LOG_LEVEL`), validated exactly like `log_level` (five
stdlib level names, case-insensitive input, uppercase normalized) and defaulting to `INFO`;
`log_payloads` (`LOG_PAYLOADS`), a boolean defaulting to `false`; and `log_payloads_max_length`
(`LOG_PAYLOADS_MAX_LENGTH`), a positive integer defaulting to `2000`. The existing `log_level`
field is unchanged.

#### Scenario: Defaults load without environment overrides

- **WHEN** `Settings` is instantiated with none of the logging variables set
- **THEN** `log_format` contains `%(otel_context)s`, `log_date_format` equals
  `%Y-%m-%d %H:%M:%S`, `deep_research_log_level` equals `INFO`, `log_payloads` is `False`, and
  `log_payloads_max_length` equals `2000`

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

#### Scenario: Non-positive truncation cap is rejected

- **WHEN** `LOG_PAYLOADS_MAX_LENGTH=0` is passed to `Settings`
- **THEN** instantiation raises a Pydantic `ValidationError` referencing the
  `log_payloads_max_length` field
