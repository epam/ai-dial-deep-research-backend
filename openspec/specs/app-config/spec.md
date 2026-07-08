# app-config Specification

## Purpose
TBD - created by archiving change validate-log-level-setting. Update Purpose after archive.
## Requirements
### Requirement: Validated log level setting

The `DialAppSettings` class SHALL expose a `log_level` field restricted to the five stdlib logging level names — `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Input matching is case-insensitive: the value SHALL be uppercased before comparison, and the normalized uppercase form SHALL be the loaded value. Any value that does not normalize to one of the five allowed names SHALL cause `DialAppSettings` instantiation to fail with a Pydantic `ValidationError` that identifies the `log_level` field.

#### Scenario: Default value loads
- **WHEN** `DialAppSettings()` is instantiated with no `LOG_LEVEL` environment variable set
- **THEN** `log_level` equals `"INFO"` and no validation error is raised

#### Scenario: Canonical uppercase value loads
- **WHEN** `LOG_LEVEL=DEBUG` is passed to `DialAppSettings`
- **THEN** `log_level` equals `"DEBUG"` and no validation error is raised

#### Scenario: Mixed-case value is normalized
- **WHEN** `LOG_LEVEL=warning` (or `Warning`, `WaRnInG`) is passed to `DialAppSettings`
- **THEN** `log_level` equals `"WARNING"` — the allowed uppercase form — with no validation error

#### Scenario: Unknown value is rejected
- **WHEN** `LOG_LEVEL=ifno` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `log_level` field

### Requirement: Validated heartbeat interval setting

The `DialAppSettings` class SHALL expose a `heartbeat_interval` field of type `int` driven by the `HEARTBEAT_INTERVAL` environment variable, representing the seconds between keep-alive heartbeats emitted by the DIAL chat-completion endpoint during long-running responses. The field SHALL default to `5`. Only strictly positive integers SHALL be accepted; zero, negative, or non-integer values SHALL cause `DialAppSettings` instantiation to fail with a Pydantic `ValidationError` identifying the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` alias). The value SHALL be the sole source of the heartbeat interval passed to `app.add_chat_completion(...)` — no other hardcoded literal for this parameter SHALL remain in application code.

#### Scenario: Default value loads
- **WHEN** `DialAppSettings()` is instantiated with no `HEARTBEAT_INTERVAL` environment variable set
- **THEN** `heartbeat_interval` equals `5` and no validation error is raised

#### Scenario: Valid positive override loads
- **WHEN** `HEARTBEAT_INTERVAL=30` is passed to `DialAppSettings`
- **THEN** `heartbeat_interval` equals `30` (as `int`) and no validation error is raised

#### Scenario: Zero is rejected
- **WHEN** `HEARTBEAT_INTERVAL=0` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` env alias)

#### Scenario: Negative value is rejected
- **WHEN** `HEARTBEAT_INTERVAL=-1` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` env alias)

#### Scenario: App factory consumes the setting
- **WHEN** `create_app()` registers the `deep-research` chat completion
- **THEN** the heartbeat interval passed to `app.add_chat_completion(...)` SHALL equal `dial_app_settings.heartbeat_interval`, and no integer literal for this parameter SHALL appear in `factory.py`

### Requirement: Dedicated OpikSettings class for Opik tracing configuration

The repository SHALL expose a dedicated `OpikSettings` pydantic-settings class in `src/dial_deep_research/settings.py`, sibling to the existing `DialAppSettings` and `McpSettings` classes. `DialAppSettings` SHALL NOT be extended with Opik fields. `OpikSettings` SHALL declare the env-var prefix `OPIK_` at the class level (via `SettingsConfigDict(env_prefix="OPIK_")`) so that terse field names map to the `OPIK_*` environment-variable convention. The class SHALL expose exactly two fields:

- `tracing_enabled: bool = False` — driven by `OPIK_TRACING_ENABLED`. The single source of truth for whether the deep-research agent attaches an Opik tracer; all activation logic in the app SHALL key off this flag.
- `project_name: str = "deep-research"` — driven by `OPIK_PROJECT_NAME`. The Opik project under which traces are grouped. The default groups all traces from this repo under a single project that matches the DIAL deployment id, avoiding the SDK's catch-all "Default Project"; contributors can override via `OPIK_PROJECT_NAME` for ad-hoc experiments.

The class SHALL be instantiated once at module import time as `opik_settings = OpikSettings()`, mirroring the existing `dial_app_settings` and `mcp_settings` singletons. Per the project rule against per-field aliases, the fields SHALL NOT carry `alias=` arguments — env-var mapping comes solely from the field name plus the class-level `env_prefix`.

The deep-research app targets a **local self-hosted Opik instance only** (started via `make opik-up`). The app SHALL configure the Opik SDK with `use_local=True` (so the SDK's local-deployment defaults apply) plus `project_name=settings.project_name` when tracing is enabled, and SHALL NOT expose configuration for Comet-hosted Opik (api key, workspace, URL override). Contributors who need a non-local Opik instance can configure the SDK directly via its native env vars / `~/.opik.config` and bypass this class.

#### Scenario: Default — tracing disabled
- **WHEN** the process starts with no `OPIK_*` environment variables set
- **THEN** `opik_settings.tracing_enabled` SHALL be `False`, `opik_settings.project_name` SHALL be `"deep-research"`, no validation error SHALL be raised, and the app SHALL NOT initialize the Opik SDK at startup

#### Scenario: Tracing enabled with explicit project name override
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and `OPIK_PROJECT_NAME=my-experiment` set
- **THEN** `opik_settings.tracing_enabled` SHALL be `True`, `opik_settings.project_name` SHALL be `"my-experiment"`, and the app SHALL configure the Opik SDK with `use_local=True` and that project name

#### Scenario: Tracing enabled with default project name
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and no `OPIK_PROJECT_NAME` set
- **THEN** `opik_settings.project_name` SHALL be `"deep-research"`, and the app SHALL configure the Opik SDK with `use_local=True` and that project name (the SDK's catch-all "Default Project" SHALL NOT be used)

#### Scenario: DialAppSettings is untouched
- **WHEN** this change lands and the repository is built
- **THEN** `DialAppSettings` SHALL retain exactly the fields it had before this change (no `opik_*` fields added) — Opik configuration lives entirely on `OpikSettings`

