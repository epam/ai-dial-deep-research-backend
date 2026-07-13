# app-config (delta)

## MODIFIED Requirements

### Requirement: Validated log level setting

The `Settings` class SHALL expose a `log_level` field restricted to the five stdlib logging level names — `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Input matching is case-insensitive: the value SHALL be uppercased before comparison, and the normalized uppercase form SHALL be the loaded value. Any value that does not normalize to one of the five allowed names SHALL cause `Settings` instantiation to fail with a Pydantic `ValidationError` that identifies the `log_level` field.

#### Scenario: Default value loads
- **WHEN** `Settings()` is instantiated with no `LOG_LEVEL` environment variable set
- **THEN** `log_level` equals `"INFO"` and no validation error is raised

#### Scenario: Canonical uppercase value loads
- **WHEN** `LOG_LEVEL=DEBUG` is passed to `Settings`
- **THEN** `log_level` equals `"DEBUG"` and no validation error is raised

#### Scenario: Mixed-case value is normalized
- **WHEN** `LOG_LEVEL=warning` (or `Warning`, `WaRnInG`) is passed to `Settings`
- **THEN** `log_level` equals `"WARNING"` — the allowed uppercase form — with no validation error

#### Scenario: Unknown value is rejected
- **WHEN** `LOG_LEVEL=ifno` is passed to `Settings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `log_level` field

### Requirement: Validated heartbeat interval setting

The `Settings` class SHALL expose a `heartbeat_interval` field of type `int` driven by the `HEARTBEAT_INTERVAL` environment variable, representing the seconds between keep-alive heartbeats emitted by the DIAL chat-completion endpoint during long-running responses. The field SHALL default to `5`. Only strictly positive integers SHALL be accepted; zero, negative, or non-integer values SHALL cause `Settings` instantiation to fail with a Pydantic `ValidationError` identifying the `heartbeat_interval` field. The value SHALL be the sole source of the heartbeat interval passed to `app.add_chat_completion(...)` — no other hardcoded literal for this parameter SHALL remain in application code.

#### Scenario: Default value loads
- **WHEN** `Settings()` is instantiated with no `HEARTBEAT_INTERVAL` environment variable set
- **THEN** `heartbeat_interval` equals `5` and no validation error is raised

#### Scenario: Valid positive override loads
- **WHEN** `HEARTBEAT_INTERVAL=30` is passed to `Settings`
- **THEN** `heartbeat_interval` equals `30` (as `int`) and no validation error is raised

#### Scenario: Zero is rejected
- **WHEN** `HEARTBEAT_INTERVAL=0` is passed to `Settings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field

#### Scenario: Negative value is rejected
- **WHEN** `HEARTBEAT_INTERVAL=-1` is passed to `Settings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field

#### Scenario: App factory consumes the setting
- **WHEN** `create_app()` registers the `deep-research` chat completion
- **THEN** the heartbeat interval passed to `app.add_chat_completion(...)` SHALL equal `settings.heartbeat_interval`, and no integer literal for this parameter SHALL appear in `factory.py`

## REMOVED Requirements

### Requirement: Dedicated OpikSettings class for Opik tracing configuration

**Reason**: The dedicated `OpikSettings` class no longer exists — settings were consolidated
into the single `Settings` class, and the Opik project name (which had meanwhile moved into
the YAML channel config) returns to the environment now that channel config is replaced by
DIAL application properties.

**Migration**: Use the `opik_tracing_enabled` and `opik_project_name` fields on `Settings`
(env vars `OPIK_TRACING_ENABLED`, `OPIK_PROJECT_NAME`) per the **Opik configuration on the
consolidated Settings class** requirement below.

## ADDED Requirements

### Requirement: Opik configuration on the consolidated Settings class

The `Settings` class SHALL expose exactly two Opik fields, with no per-field aliases (env-var
mapping comes solely from the field name and the class-level empty `env_prefix`):

- `opik_tracing_enabled: bool = False` — driven by `OPIK_TRACING_ENABLED`. The single source
  of truth for whether the agent attaches an Opik tracer.
- `opik_project_name: str = "deep-research"` — driven by `OPIK_PROJECT_NAME`. The Opik
  project traces are grouped under; process-level (not per application instance), because the
  Opik SDK is configured once at startup.

The app targets a local self-hosted Opik instance only (started via `make opik-up`): when
tracing is enabled, the app SHALL configure the Opik SDK with `use_local=True` and
`project_name=settings.opik_project_name`, and SHALL NOT expose configuration for
Comet-hosted Opik. Application properties SHALL NOT carry an Opik project name.

#### Scenario: Default — tracing disabled
- **WHEN** the process starts with no `OPIK_*` environment variables set
- **THEN** `settings.opik_tracing_enabled` SHALL be `False`,
  `settings.opik_project_name` SHALL be `"deep-research"`, and the app SHALL NOT initialize
  the Opik SDK at startup

#### Scenario: Tracing enabled with explicit project name override
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and
  `OPIK_PROJECT_NAME=my-experiment` set
- **THEN** the app SHALL configure the Opik SDK with `use_local=True` and project name
  `"my-experiment"`

#### Scenario: Tracing enabled with default project name
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and no `OPIK_PROJECT_NAME` set
- **THEN** the app SHALL configure the Opik SDK with `use_local=True` and project name
  `"deep-research"` (the SDK's catch-all "Default Project" SHALL NOT be used)
