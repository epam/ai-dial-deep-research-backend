## 1. Python project scaffolding (uv)

- [x] 1.1 Create `pyproject.toml`: project metadata, `requires-python = ">=3.13,<3.14"`, runtime deps (`aidial-sdk[telemetry] (>=0.32.0,<0.33.0)`, `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv`), dev deps under `[dependency-groups].dev` (`black`, `isort`, `ruff`, `mypy`, `pytest`, `pytest-asyncio`)
- [x] 1.2 Add `.python-version` containing `3.13` (uv reads this automatically)
- [x] 1.3 Configure tooling in `pyproject.toml`: `[tool.black]` line-length 100, skip-string-normalization; `[tool.isort]` profile `black`, line_length 100, `src_paths = ["src"]`; `[tool.ruff]` target py313, line-length 120, a `lint.select` subset with `E501` kept in `ignore` so it doesn't fight black; `[tool.mypy]` basic, include `aidial_sdk.*` follow-untyped-imports override
- [x] 1.4 Run `uv sync` to generate `uv.lock` and commit both `pyproject.toml` and `uv.lock`
- [x] 1.5 Add `.gitignore` entries for `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.env`, `dial_conf/core/logs/`

## 2. App server source

- [x] 2.1 Create package layout `src/dial_deep_research/__init__.py` + `src/dial_deep_research/app/__init__.py` (use `src/` layout)
- [x] 2.2 Implement `src/dial_deep_research/settings.py`: a `DialAppSettings(BaseSettings)` pydantic-settings class with fields `APP_HOST` (default `"0.0.0.0"`), `APP_PORT` (default `5000`), `DIAL_URL` (default `"http://core:8080"`), `DIAL_APP_NAME` (default `"Echo"`); expose a singleton `dial_app_settings`
- [x] 2.3 Implement `src/dial_deep_research/app/completion.py`: `EchoCompletion(ChatCompletion)` whose `chat_completion(request, response)` extracts the last `user` message, opens a choice via `with response.create_choice() as choice:`, and streams `"echo: " + text` through `choice.append_content(...)`. Tolerate non-text attachments and empty content.
- [x] 2.4 Implement `src/dial_deep_research/app/factory.py`: a `create_app() -> DIALApp` function. Instantiate `DIALApp(dial_url=dial_app_settings.dial_url, add_healthcheck=True, telemetry_config=TelemetryConfig(service_name=dial_app_settings.dial_app_name, tracing=TracingConfig(), metrics=MetricsConfig()))`, register the echo handler via `app.add_chat_completion("echo", EchoCompletion(), heartbeat_interval=5)` (built-in helper — a custom multi-deployment dispatch is not needed)
- [x] 2.5 Implement `src/dial_deep_research/__main__.py` as the entrypoint: load `.env` (best-effort `try/except`), configure root logging, import `create_app()`, call `uvicorn.run(create_app(), host=dial_app_settings.app_host, port=dial_app_settings.app_port, log_config=None)`
- [x] 2.6 Add a minimal `configure_logging(level, use_color)` helper (or inline configuration in `__main__.py`)
- [x] 2.7 Verify the SDK's built-in `/health` endpoint responds 200 once the app is running (no additional code needed because `add_healthcheck=True`)

## 3. Tests

- [x] 3.1 Add `tests/test_echo.py` covering: single-turn echo, multi-turn history echoes only last user message, empty last-user-message case, non-text attachments are tolerated
- [x] 3.2 Add `tests/test_health.py` asserting the health endpoint returns 200
- [x] 3.3 Ensure `make test` (pytest) passes locally

## 4. DIAL core configuration

- [x] 4.1 Create `dial_conf/core/config.json` registering application `echo` → `http://app:5000/openai/deployments/echo/chat/completions` with `forwardAuthToken: true`, plus `keys.dial_api_key` (project `dial-deep-research`, role `default`) and `roles.default.limits` allowing the `echo` application
- [x] 4.2 Create `dial_conf/settings/settings.json` with `server.port=8080`, `identityProviders.test` with `disableJwtVerification=true`, encryption block, `applications.includeCustomApps=true`
- [x] 4.3 Create `dial_conf/settings/gflog.xml`

## 5. Dockerfile (uv-native) — REVERTED

> Originally built, then deleted in the host-first pivot: the app now runs on the
> host via `uv run python -m dial_deep_research`, DIAL core reaches it via
> `host.docker.internal:5000`. See design.md → "Decision: Host-first app execution".
> Tasks below record the work that was done and subsequently removed.

- [x] 5.1 ~~Create `Dockerfile`: `FROM python:3.13-slim`, copy `uv` binary via `COPY --from=ghcr.io/astral-sh/uv:<pinned-tag> /uv /uvx /bin/`~~
- [x] 5.2 ~~Set `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never`; create non-root user~~
- [x] 5.3 ~~`WORKDIR /opt/app`; copy `pyproject.toml` and `uv.lock`; run `uv sync --frozen --no-install-project --no-dev` with a `--mount=type=cache,target=/root/.cache/uv` cache mount to install deps~~
- [x] 5.4 ~~Copy `./src` into the image; run `uv sync --frozen --no-dev` once more to install the project itself; switch to the non-root user~~
- [x] 5.5 ~~`EXPOSE 5000`; `CMD ["uv", "run", "python", "-m", "dial_deep_research"]`~~

## 6. Docker Compose

- [x] 6.1 Create `docker-compose.yml` (Compose V2 syntax, no `version:` key) with services `core`, `chat`, `themes`, `redis` using pinned tags (`epam/ai-dial-core:0.42.0`, `epam/ai-dial-chat:0.36.0`, `epam/ai-dial-chat-themes:0.10.0`, `redis:7.2.4-alpine3.19`) *(top-level `name:` later dropped — directory name provides it)*
- [x] 6.2 Wire `core` with env vars (`AIDIAL_SETTINGS`, `JAVA_OPTS`, `aidial.config.files`, `aidial.redis.singleServerConfig.address`) and volumes for `./dial_conf/settings` and `./dial_conf/core/config.json`; add named volumes for logs + data
- [x] 6.3 Wire `chat` on port 3000, `DIAL_API_HOST=http://core:8080`, `DIAL_API_KEY=${DIAL_API_KEY}`, `THEMES_CONFIG_HOST=http://themes:8080`, `AUTH_DISABLED=true`, and an enabled-features string
- [x] 6.4 Wire `themes` on port `3001:8080`
- [x] 6.5 Wire `redis` with a constrained memory/policy command
- [x] 6.6 ~~Create `docker-compose.app.yml` layering the `app` service~~ *(reverted in host-first pivot — app runs on host, not in compose)*
- [x] 6.7 Add `.env.example` documenting `DIAL_API_KEY=dial_api_key` (and any other vars required)

## 7. Makefile

- [x] 7.1 Create `Makefile` *(`.PHONY` declarations later dropped as ceremony — see design.md)*
- [x] 7.2 Define `UV ?= uv`, `SRC_DIRS = src tests`, `MYPY_DIRS = src`, and `COMPOSE_INFRA = docker compose -f docker-compose.yml`; bare `make` defaults to `help` because it's the first target *(`COMPOSE_APP` variable and `.DEFAULT_GOAL` later removed during cleanup)*
- [x] 7.3 Implement `help` (prints target descriptions via awk on lines containing `## ` marker), `init_venv` (`$(UV) venv`), `install` (`$(UV) sync`)
- [x] 7.4 Implement `format`: `$(UV) run ruff check $(SRC_DIRS) --fix`, then `$(UV) run black $(SRC_DIRS)`, then `$(UV) run isort $(SRC_DIRS)` (auto-fixes everything auto-fixable in one pass)
- [x] 7.5 Implement `lint`: `$(UV) run ruff check`, `$(UV) run mypy`, `$(UV) run black --check`, `$(UV) run isort --check-only --diff` — formatting checks last so fixes to ruff/mypy findings don't immediately re-break them
- [x] 7.6 Implement `test`: `$(UV) run pytest tests`
- [x] 7.7 Implement `run`: `$(UV) run python -m dial_deep_research` *(originally `docker compose run --build --rm -p 5000:5000 app`; switched to host-run in host-first pivot)*
- [x] 7.8 Implement `up`: `$(COMPOSE_INFRA) up -d`; `down`: `$(COMPOSE_INFRA) down`; `logs`: `$(COMPOSE_INFRA) logs -f`; `cleanup`: `$(COMPOSE_INFRA) down --volumes` *(originally named `stop`; renamed to `down` for symmetry with `up`)*
- [x] 7.9 Make `install` surface a readable error if `uv` is not on PATH (check with `command -v uv` and point at the install one-liner)

## 8. Documentation

- [x] 8.1 Write `README.md` covering: prerequisites (Docker, `curl -LsSf https://astral.sh/uv/install.sh | sh`), `cp .env.example .env`, `make install`, `make up`, open `http://localhost:3000`, select `Echo` application, send `"hello"`, `make stop`
- [x] 8.2 Note in the README that this is scaffolding for deep research and link `generic-rag` (the future MCP source)
- [x] 8.3 Call out in the README that this repo uses **uv** as its packaging tool

## 9. Validation

- [x] 9.1 Run `make install && make lint && make test` on a clean checkout and confirm all pass
- [x] 9.2 Run `make up` + `make run`, open the chat UI, select `echo`, send `"hello"`, and confirm `"echo: hello"` is streamed back
- [x] 9.3 Verify `make down` and `make cleanup` tear down infra (and volumes) cleanly  *(smoke-tested: `make up`, `make down`, `make run` all work)*
- [x] 9.4 Run `openspec validate bootstrap-echo-dial-app` and resolve any issues before handing off
