## ADDED Requirements

### Requirement: Dedicated OpikSettings class for Opik tracing configuration

The repository SHALL expose a dedicated `OpikSettings` pydantic-settings class in `src/dial_deep_research/settings.py`, sibling to the existing `DialAppSettings` and `McpSettings` classes. `DialAppSettings` SHALL NOT be extended with Opik fields. `OpikSettings` SHALL declare the env-var prefix `OPIK_` at the class level (via `SettingsConfigDict(env_prefix="OPIK_")`) so that terse field names map to the `OPIK_*` environment-variable convention. The class SHALL expose exactly two fields:

- `tracing_enabled: bool = False` — driven by `OPIK_TRACING_ENABLED`. The single source of truth for whether the deep-research agent attaches an Opik tracer; all activation logic in the app SHALL key off this flag.
- `project_name: str | None = None` — driven by `OPIK_PROJECT_NAME`. The Opik project under which traces are grouped. When unset, the Opik SDK SHALL use its built-in default (typically "Default Project").

The class SHALL be instantiated once at module import time as `opik_settings = OpikSettings()`, mirroring the existing `dial_app_settings` and `mcp_settings` singletons. Per the project rule against per-field aliases, the fields SHALL NOT carry `alias=` arguments — env-var mapping comes solely from the field name plus the class-level `env_prefix`.

The deep-research app targets a **local self-hosted Opik instance only** (started via `make opik-up`). The app SHALL configure the Opik SDK with `use_local=True` (so the SDK's local-deployment defaults apply) plus `project_name=settings.project_name` when tracing is enabled, and SHALL NOT expose configuration for Comet-hosted Opik (api key, workspace, URL override). Contributors who need a non-local Opik instance can configure the SDK directly via its native env vars / `~/.opik.config` and bypass this class.

#### Scenario: Default — tracing disabled
- **WHEN** the process starts with no `OPIK_*` environment variables set
- **THEN** `opik_settings.tracing_enabled` SHALL be `False`, `opik_settings.project_name` SHALL be `None`, no validation error SHALL be raised, and the app SHALL NOT initialize the Opik SDK at startup

#### Scenario: Tracing enabled with explicit project name
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and `OPIK_PROJECT_NAME=deep-research` set
- **THEN** `opik_settings.tracing_enabled` SHALL be `True`, `opik_settings.project_name` SHALL be `"deep-research"`, and the app SHALL configure the Opik SDK with `use_local=True` and that project name

#### Scenario: Tracing enabled without explicit project name
- **WHEN** the process starts with `OPIK_TRACING_ENABLED=true` and no `OPIK_PROJECT_NAME` set
- **THEN** `opik_settings.project_name` SHALL be `None`, and the app SHALL configure the Opik SDK with `use_local=True` and `project_name=None`, deferring to the SDK's built-in default project

#### Scenario: DialAppSettings is untouched
- **WHEN** this change lands and the repository is built
- **THEN** `DialAppSettings` SHALL retain exactly the fields it had before this change (no `opik_*` fields added) — Opik configuration lives entirely on `OpikSettings`
