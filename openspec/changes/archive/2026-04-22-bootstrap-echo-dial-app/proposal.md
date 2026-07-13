## Why

The `dial-deep-research` repo is currently empty scaffolding. Before we can implement the real deep-research application (which will plug in the generic-rag MCP server), we need a working local development environment: a minimal DIAL-compatible chat application that echoes user input, wired into a Dockerized DIAL stack with a chat UI, and driven by a consistent toolchain (uv + Makefile). Starting from a thin vertical slice lets us validate the dev loop (edit → reload → chat in browser) before layering on retrieval, tools, and agent logic.

## What Changes

- Add Python project scaffolding managed by **uv** (`pyproject.toml`, `uv.lock`, pinned Python version).
- Add a minimal **app server** that implements the DIAL application protocol and echoes the last user message back (plus a trivial health endpoint).
- Add a **Docker Compose** stack that runs the DIAL core, the DIAL chat UI, and the echo app, so a developer can open the chat UI in a browser and converse with the echo app end-to-end.
- Add a **Makefile** with targets for common developer workflows: install, format, lint, test, run (local), up/down (docker compose), and logs.
- Add baseline code-quality config (formatter, linter, type checker).
- Add a short `README.md` describing how to boot the stack and chat with the echo app.

This change deliberately does **not** implement deep research, retrieval, MCP wiring, or any real LLM calls — those land in follow-up changes once the environment is proven.

## Capabilities

### New Capabilities
- `dev-environment`: Developer tooling, Python project layout (uv), Makefile targets, and code-quality configuration for the repo.
- `local-stack`: Docker Compose topology that brings up DIAL core, chat UI, and the app server for local end-to-end testing.
- `echo-app`: A minimal DIAL-protocol application server whose only behavior is to echo the user's latest message. Serves as the integration scaffold that later changes will replace with real deep-research logic.

### Modified Capabilities
<!-- none — repo is empty -->

## Impact

- **New files**: `pyproject.toml`, `uv.lock`, `Makefile`, `docker-compose.yml`, `.env.example`, app source under `src/` (or equivalent), `README.md`, lint/format config.
- **Dependencies**: `uv` (toolchain), `aidial-sdk` (or equivalent DIAL app framework), `fastapi`/`uvicorn` as required by the SDK, plus dev tooling (ruff/black, mypy, pytest).
- **External services pulled via compose**: DIAL core image, DIAL chat UI image.
- **Self-contained** — this change does not affect anything outside `dial-deep-research/`.
- **Future work unblocked**: plugging in the generic-rag MCP server and implementing deep-research orchestration.
