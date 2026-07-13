## Why

Deep-research turns currently stream tool calls and assistant text to DIAL but leave no durable trace of what the agent did: which prompt the LLM saw, what each MCP tool returned, where time was spent, why a turn went sideways. The `aidial-sdk[telemetry]` OpenTelemetry path exposes HTTP-level spans but not LLM/agent-level structure, so debugging a "wrong answer" or "slow tool" reduces to log-grepping. Adding **Opik** (open-source LLM observability) gives us full hierarchical traces — agent run → LLM call → each MCP tool call — viewable in a local UI, with no external service required for development.

## What Changes

- **deep-research**: instrument the per-request LangChain agent with `opik.integrations.langchain.OpikTracer`, passed as a callback on `agent.astream(..., config={"callbacks": [tracer]})`. Activation is gated on configuration: when Opik is not configured the tracer SHALL NOT be attached, and the agent SHALL run exactly as today (no behaviour change, no failure).
- **app-config**: add a new dedicated `OpikSettings` pydantic-settings class in `src/dial_deep_research/settings.py` (sibling to the existing `DialAppSettings` and `McpSettings`) with two fields — `tracing_enabled` (`bool`, defaults `False`) and `project_name` (`str | None`, defaults `None`). Env vars are `OPIK_TRACING_ENABLED` and `OPIK_PROJECT_NAME`, derived from the field names plus the `OPIK_` env-prefix. The app targets a **local self-hosted Opik only** (started via `make opik-up`); the SDK is configured with `use_local=True`, so we don't need to expose api key / URL override / workspace / port — the SDK's local-deployment defaults handle them. `DialAppSettings` is **not** modified. The boolean flag is the single activation gate; default is **off** so the agent behaves identically to today unless a contributor opts in.
- **local-stack**: add `make opik-up` / `make opik-down` targets that run a local Opik trace stack as a separate Compose project, fully independent of the infra `make up` / `make down` lifecycle. Implementation delegates to Opik's upstream compose by cloning the upstream Opik repository into a gitignored `.opik-local/` directory on first `opik-up` (the upstream compose is ~400 lines and references several auxiliary config files; vendoring it into our repo is impractical and brittle). The wrapper pins a specific Opik release tag.
- **dependencies**: add `opik` to `pyproject.toml` runtime dependencies; refresh `uv.lock`.
- **docs**: document the two env vars (`OPIK_TRACING_ENABLED`, `OPIK_PROJECT_NAME`) in `envvars.md`, and add a short "LLM tracing with Opik" section to the README explaining `make opik-up`, the UI URL, and the opt-in (`OPIK_TRACING_ENABLED=true` in local config).
- **non-goals (this change)**: no Opik dataset/evaluation work, no auto-instrumentation of the OpenTelemetry path, no changes to the existing `aidial-sdk[telemetry]` setup — Opik is purely additive.

## Capabilities

### New Capabilities

(None — all changes extend existing capabilities.)

### Modified Capabilities

- `deep-research`: new requirement that the per-request agent's LLM and tool calls SHALL be traced via an Opik callback when Opik is configured, with no behaviour change when it is not.
- `app-config`: new requirement adding a dedicated `OpikSettings` class (separate from `DialAppSettings`) — explicit `tracing_enabled` boolean (default off) and an optional `project_name` field. Local-only by design (SDK called with `use_local=True`); no api key, URL override, workspace, or port surfaced — those default sensibly inside the Opik SDK and the local Opik stack.
- `local-stack`: new requirement that the repo SHALL provide `make opik-up` / `make opik-down` targets backing a separate Opik Compose lifecycle (delegating to upstream Opik's compose via a gitignored `.opik-local/` checkout), fully independent of the infra `make up` / `make down` lifecycle.

## Impact

- **Code**: `src/dial_deep_research/app/completion.py` (attach tracer to `astream`), `src/dial_deep_research/settings.py` (Opik fields), small `app/tracing.py` helper that builds the tracer or `None` based on settings.
- **Config / infra**: updated `Makefile` (`opik-up`, `opik-down` wrapping upstream Opik compose), `.gitignore` (add `.opik-local/`), `envvars.md`, `pyproject.toml`, `uv.lock`. The existing `docker-compose.yml` is **not** modified; no new compose file is added to the repo.
- **Dependencies**: new runtime dep `opik` (Python SDK + LangChain integration); new infra images for the Opik service set (TBD at implementation time from Opik's published self-host docs).
- **Untouched**: `aidial-sdk[telemetry]` OpenTelemetry path, existing `docker-compose.yml`, `make up` / `make down`, DIAL adapter, generic-RAG MCP, agent control flow, error funnel, stage rendering, message dispatch.
- **Risk**: Opik's self-host stack is multi-service and disk-heavy. Mitigation: keep it in a separate compose file behind opt-in `make opik-up`; default cold-start cost stays at zero; default tracing flag stays off.
