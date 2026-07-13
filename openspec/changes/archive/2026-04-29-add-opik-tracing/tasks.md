## 1. Dependencies

- [x] 1.1 Add `opik` to `[project] dependencies` in `pyproject.toml` with a sensible upper bound (e.g. `opik>=1.0,<2.0`); confirm it ships the LangChain integration (`opik.integrations.langchain`) without an extra
- [x] 1.2 Run `uv sync` and commit the updated `uv.lock`

## 2. Settings

- [x] 2.1 Add a new `OpikSettings(BaseSettings)` class to `src/dial_deep_research/settings.py`, sibling to the existing `DialAppSettings` and `McpSettings`. Use `SettingsConfigDict(env_prefix="OPIK_")` so field names map to the `OPIK_*` env vars without per-field `alias=`. Two fields only: `tracing_enabled: bool = False` and `project_name: str | None = None`. Local-only by design — `tracing.py` calls `opik.configure(use_local=True, project_name=settings.project_name)`, no api-key / url-override / workspace / port plumbing.
- [x] 2.2 Add `opik_settings = OpikSettings()` at module scope alongside the existing `dial_app_settings` and `mcp_settings` singletons. Do NOT modify `DialAppSettings`.

## 3. Tracing wiring

- [x] 3.1 Create `src/dial_deep_research/app/tracing.py` exposing `configure_opik(settings: OpikSettings) -> None` (calls `opik.configure(...)` once with whichever connection fields are set, gated on `settings.tracing_enabled`) and `build_opik_tracer(settings: OpikSettings) -> OpikTracer | None` (returns `None` when the flag is off)
- [x] 3.2 In `src/dial_deep_research/app/factory.py`, call `configure_opik(opik_settings)` once at app construction time
- [x] 3.3 In `src/dial_deep_research/app/completion.py`, in `_AgentRunner.__init__` build the optional tracer via `build_opik_tracer(opik_settings)`; in `_AgentRunner.run` extend the `astream` call to pass `config={"callbacks": [tracer]}` only when `tracer is not None` — no other code path changes
- [x] 3.4 Read the `opik_settings` module-level singleton directly in `tracing.py` callers — avoid re-instantiating `OpikSettings()` per request and avoid threading it through `DeepResearchCompletion` constructors (settings are process-global, mirroring how `dial_app_settings` is consumed today)

## 4. Local Opik stack (wrapper around upstream Opik compose)

- [x] 4.1 Consult Opik's current self-host docs and upstream `docker-compose.yaml`. Confirmed: the upstream compose is ~400 lines and references several host-mounted auxiliary config files (ClickHouse XML, NGINX templates, OTel collector config). Vendoring is impractical → use a wrapper around upstream.
- [x] 4.2 Pick a specific Opik release tag to pin against (a real tag from `github.com/comet-ml/opik/releases`, not `main` / `latest`); record it as `OPIK_VERSION` in the Makefile — pinned to `2.0.17` (latest at change time, matches the SDK version on PyPI)
- [x] 4.3 Add `.opik-local/` to `.gitignore` (the auto-cloned upstream Opik repo lives here)
- [x] 4.4 Add Makefile targets `opik-up` and `opik-down` that:
    - lazily `git clone --depth 1 --branch $(OPIK_VERSION) https://github.com/comet-ml/opik.git .opik-local` if the directory doesn't exist,
    - run `docker compose -f .opik-local/deployment/docker-compose/docker-compose.yaml --profile opik up -d` (and matching `down`),
    - leave the existing `up` / `down` / `cleanup` targets untouched (verify by inspection).
- [x] 4.5 Document host ports: Opik UI at `http://localhost:5173`, SDK ingestion endpoint at `http://localhost:5173/api` (frontend NGINX proxies `/api` to backend). Confirm no collision with existing bindings (`3000`, `3001`, `5000`, `8080`).
- [ ] 4.6 Manually verify the four lifecycle scenarios: `make up` alone does not start Opik; `make down` while Opik is running does not stop it; `make opik-up` alone does not start infra; `make opik-down` while infra is running does not stop it. (The upstream compose declares `name: opik`, so this should hold by Compose's project-scoping rules.)

## 5. Documentation

- [x] 5.1 Add `OPIK_TRACING_ENABLED` and `OPIK_PROJECT_NAME` to `envvars.md` with descriptions and defaults; note that the app is local-only (calls `opik.configure(use_local=True, ...)`) and that contributors needing a non-local Opik configure the SDK directly via its native env vars / `~/.opik.config`
- [x] 5.2 Add a short "LLM tracing with Opik" section to `README.md` under the dev-loop documentation: `make opik-up` / `make opik-down`, the UI URL, the two env vars a contributor sets to opt in (`OPIK_TRACING_ENABLED=true`, optional `OPIK_PROJECT_NAME=<name>`), and how to opt back out

## 6. Validation

- [x] 6.1 Run `make lint` — black, isort, ruff, mypy all green
- [x] 6.2 Run `make test` — pre-existing tests still pass (no new automated tests are added in this change; Opik integration is verified manually below)
- [x] 6.3 Manual end-to-end smoke: `make up` + `make opik-up` → set the local opt-in env vars → `make run` → drive a multi-turn conversation through the chat UI that triggers MCP tool calls → verify the trace tree in the Opik UI matches the agent's actual behaviour (one trace per turn, with the agent run, the LLM call, and one span per MCP tool call carrying inputs/outputs)
- [ ] 6.4 Manual opt-out smoke: `make opik-down` (leaving infra up) → unset `OPIK_TRACING_ENABLED` → restart `make run` → verify chat completion still succeeds end-to-end with no Opik traffic
- [x] 6.5 Run `openspec validate add-opik-tracing --strict` and confirm clean
