## Context

`dial-deep-research/` is a fresh repo that will eventually host a DIAL application implementing deep-research orchestration over the generic-rag MCP server. Today it contains only OpenSpec scaffolding. Before doing anything domain-specific we need a working local dev loop: a DIAL-protocol app server that a developer can hit through the DIAL chat UI running in Docker Compose.

Constraints:
- Python-based (async/await, Pydantic v2, modern type hints).
- DIAL-native: the app must speak the DIAL application protocol so the same deployment model works once real logic is plugged in.
- Must work fully offline (no real LLM calls) so CI and first-time contributors can boot it with zero cloud credentials.
- Packaging: **uv** — user directive.
- Formatter: **black** — user directive.

## Goals / Non-Goals

**Goals:**
- A developer can run `make up` and open the DIAL chat UI at `http://localhost:3000` and talk to an echoing deployment within minutes of cloning.
- All Python dependencies are managed by `uv` with a committed `uv.lock`.
- The Makefile is terse (a handful of targets) while exposing the minimum surface a contributor needs.
- The DIAL Compose topology uses pinned image tags and is stripped down to what the echo app needs.
- The app server layout anticipates future deep-research logic — tools, MCP client, agent loop — without prematurely scaffolding them.

**Non-Goals:**
- Implementing any retrieval, RAG, MCP, or real LLM interaction. Those land in later changes.
- Production deployment artifacts (Helm charts, Terraform, CI/CD pipelines).
- Authentication/authorization beyond what the DIAL stack provides out of the box locally.
- Multi-environment config management. A single `.env.example` is sufficient for now.
- Including adapter-dial, vectordb, elasticsearch, or mcp-inspector services — no downstream feature needs them yet.

## Decisions

### Decision: Use the `aidial-sdk` Python SDK for the app server
**Rationale:** It is the canonical way to expose a DIAL-protocol application and already handles streaming, request/response envelopes, and error shapes. Hand-rolling the protocol would be throwaway work.
**Version pin:** `aidial-sdk[telemetry] >=0.32.0,<0.33.0`.
**Alternatives considered:** Raw FastAPI implementing the DIAL HTTP contract by hand — rejected as redundant effort.

### Decision: uv with `pyproject.toml` + committed `uv.lock`
**Rationale:** User directive. uv is faster, produces a deterministic lockfile, and has first-class Docker integration via the published `ghcr.io/astral-sh/uv` image that can be copied into a slim Python base. Commit `uv.lock` so Docker builds and CI use identical resolutions. uv is the direction for new Python services.
**Python version:** `>=3.13,<3.14`. Ship a `.python-version` file (uv reads it natively).
**Alternatives considered:** Poetry — rejected per user directive. pip-tools — rejected.

### Decision: Host-first app execution (no app Dockerfile)
**Rationale:** The app runs on the host (`uv run python -m dial_deep_research`), not in a container. DIAL core in compose reaches it via `http://host.docker.internal:5000`. This trades prod-parity for three concrete dev wins:
1. **IDE debugging is one-click.** No debugpy, port publishing, path mappings, or attach-mode fiddling. Hit the green button, set breakpoints, step through. This is the daily workflow for iterating on agent/tool logic.
2. **Instant reload.** Edit source → Ctrl+C → `make run`. No `docker build` layer-cache miss on every file change.
3. **Less ceremony in the repo.** No Dockerfile, no `docker-compose.app.yml`, no `--no-deps` flag, no cross-file `depends_on`.

**Alternatives considered:**
- *Docker-first (app as compose service)*: rejected. The parity it buys is real — fewer surprises in CI/prod — but we have no CI/prod for this repo yet, and the debug friction tax is daily. Easy to add back later: ~20 min to write a Dockerfile + overlay + re-template the endpoint.
- *Both paths* (host and Docker): rejected as premature. Not worth the templating cost until one of the two paths actually has users.

**Trade-offs / caveats:**
- **Linux.** `host.docker.internal` is provided automatically by Docker Desktop on macOS/Windows. Linux users need `extra_hosts: ["host.docker.internal:host-gateway"]` on the `core` service. Documented in README; one-line fix when a Linux contributor shows up.
- **Contributor toolchain.** Host-first requires uv and Python 3.13 on the contributor's machine. Already a prerequisite for `make test` / `make lint`, so net-zero.
- **When to reintroduce Docker.** First time CI tests diverge from local runs, or first time we need a real deployment target.

### Decision: Docker Compose topology (infra only)
Four services in `docker-compose.yml`:
- `core` (DIAL core) — `epam/ai-dial-core:0.42.0`, port `8080:8080`, volumes for `dial_conf/core/config.json` and `dial_conf/settings/`.
- `chat` (DIAL chat UI) — `epam/ai-dial-chat:0.36.0`, port `3000:3000`, depends on `themes` + `core`.
- `themes` — `epam/ai-dial-chat-themes:0.10.0`, port `3001:8080`.
- `redis` — `redis:7.2.4-alpine3.19`, required by `core`.

No app service in compose (see host-first decision above).
**Tags pinned** to concrete versions (not `:latest`), for reproducibility from day one.

### Decision: Static DIAL core config (no template substitution)
**Rationale:** We do not need template substitution yet — there are no secrets or per-env endpoints to inject. Ship a plain `dial_conf/core/config.json` with the `echo` application hard-coded to `http://host.docker.internal:5000/...`. Revisit when we add real LLM routes in a later change.
**Alternatives considered:** An entrypoint shell script that substitutes env vars into a config template — rejected as premature.

### Decision: Echo behavior
The app SHALL return, as a single assistant message, the verbatim content of the last user message, prefixed with a short, stable marker (`echo: `). It SHALL stream the response via the SDK's streaming API so we exercise the streaming code path end-to-end — that path will matter once real generation is added. Non-text attachments are ignored in this iteration.

### Decision: Application server code layout
**Rationale:** Use a conventional DIAL app layout (entrypoint / factory / completion / settings) now so future changes drop into a familiar skeleton.

Layout (greatly simplified; we only implement what the echo flow touches):
- `src/dial_deep_research/__main__.py` — loads `.env` (best-effort), configures logging, imports the factory, calls `uvicorn.run(app, host=..., port=..., log_config=None)`. Runs on port 5000 by default.
- `src/dial_deep_research/app/factory.py` — a `create_app()` function that instantiates `DIALApp`, registers the echo `ChatCompletion` under the `echo` deployment via `app.add_chat_completion(...)`, enables the SDK's built-in healthcheck (`add_healthcheck=True`), and wires `TelemetryConfig` so tracing/metrics hooks exist from day one even if no collector is configured.
- `src/dial_deep_research/app/completion.py` — an `EchoCompletion(ChatCompletion)` subclass implementing `chat_completion(request, response)`: extracts the last user message, opens a choice via `with response.create_choice() as choice`, and streams the `"echo: "` prefix + text via `choice.append_content()`.
- `src/dial_deep_research/settings.py` — a `DialAppSettings(BaseSettings)` pydantic-settings model exposing `APP_HOST`, `APP_PORT`, `DIAL_URL`, `DIAL_APP_NAME`. A single `dial_app_settings` singleton is imported where needed.
- `src/dial_deep_research/__init__.py` — empty package marker.

We deliberately do **not** add a multi-deployment dispatch helper, token-usage bookkeeping, auth context plumbing, middleware, or a service-endpoints router. Introducing them before we have the underlying features is cargo-culting. When a real feature needs one of these, we add it in that change.

### Decision: Single-deployment registration via `add_chat_completion`
**Rationale:** A custom registration helper that dispatches on the `{deployment_id}` path param is only needed when one process serves many deployments. We serve a single `echo` deployment, so the SDK's built-in `app.add_chat_completion("echo", EchoCompletion())` suffices. If deep-research later needs multiple deployments, we migrate to a dispatching pattern then.

### Decision: Terse Makefile
**Rationale:** Short list of targets, `up` / `run` / `stop` / `cleanup` verbs. Add `format`, `test`, `logs`, and a `help` default goal. All tools invoked via `uv run` / `uv sync`.
**Targets:** `help`, `init_venv`, `install`, `format`, `lint`, `test`, `run`, `up`, `stop`, `logs`, `cleanup`.

### Decision: Code-quality stack — black + isort + ruff + mypy
**Rationale:**
- **black** for formatting — user directive.
- **isort** (black-compatible profile) for import ordering.
- **ruff check** for lint — replaces flake8 + autoflake (ruff covers both rule sets). Configure ruff to not format (its formatter is off), so black remains the sole formatter.
- **mypy** for type safety — included because this repo will grow in complexity.
- **pytest** for tests.

All tools invoked via `uv run <tool>` from the Makefile. `pyproject.toml` config: `black` with `line-length = 100`; `isort` with `profile = "black"` and `line_length = 100`; `ruff` lint-only with `E501` ignored so it doesn't fight black; `mypy` basic + `aidial_sdk.*` override.

## Risks / Trade-offs

- **DIAL image version drift** → Tags pinned to concrete versions in `docker-compose.yml`. Upgrading is a conscious PR.
- **uv not installed on contributor machines** → README points at the `curl -LsSf https://astral.sh/uv/install.sh | sh` one-liner. Makefile `install` fails fast if `uv` is not on `PATH`.
- **Docker Compose schema differences** → Target Compose V2 syntax (no top-level `version:` key).
- **Ruff rule set may disagree with black** → Constrain ruff's `select` to exclude format-adjacent rules; `E501` stays ignored. Rerun `make format && make lint` on every file we author to catch conflicts early.
- **Local code mount on macOS can be slow** → Use Docker's cached/delegated mount flags for the `app` service; acceptable because the echo app is tiny.
- **Echo endpoint may be mistaken for a real app** → README states clearly this is scaffolding; the deployment name `echo` makes intent obvious in the UI.

## Migration Plan

Not applicable — this is greenfield. Rollback = `git revert` the change; no state to unwind.

## Open Questions

None. Port 3000 for chat UI confirmed by the user. Toolchain confirmed as uv.
