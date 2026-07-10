# Tasks: reformat-env-docs-and-require-dial-url

## 1. Settings — make DIAL_URL required

- [x] 1.1 In `src/dial_deep_research/settings.py`, change `dial_url: HttpUrl = HttpUrl("http://localhost:8080")` to `dial_url: HttpUrl` (no default) so it is required and fails fast at startup. Update the field comment to note there is no built-in default.
- [x] 1.2 In `.env.example`, add `DIAL_URL=http://localhost:8080` as the documented local-dev value (grouped with the other DIAL Core vars).

## 2. README — reformat the Environment variables section

- [x] 2.1 Replace the two-table Required/Optional layout (and the separate MCP-mode table) with a single quickapps-style table `Variable | Default | Required | Description`, grouped by bold category header rows: App server, DIAL Core, MCP server, LLM models, Opik tracing, Scripts & config generator.
- [x] 2.2 Fill each row's Default and Required from the settings: `DIAL_URL` (—, Yes), `MCP_SERVER_NAME` (—, Yes), `APP_HOST` (`0.0.0.0`, No), `APP_PORT` (`5000`, No), `LOG_LEVEL` (`INFO`, No), `DIAL_APP_NAME` (`deep-research`, No), `HEARTBEAT_INTERVAL` (`5`, No), `OPIK_TRACING_ENABLED` (`false`, No), `OPIK_PROJECT_NAME` (`deep-research`, No), `LLM_MODELS_<ENUM_NAME>` (—, No), `REMOTE_DIAL_URL` (—, No), `REMOTE_DIAL_API_KEY` (—, No).
- [x] 2.3 Express the MCP modes in the Required column: `MCP_DEPLOYMENT_NAME` (—, `mode¹`), `MCP_URL` (—, `mode¹`), `MCP_API_KEY` (—, `if MCP_URL`); add a footnote stating exactly one MCP mode is required (deployment via `MCP_DEPLOYMENT_NAME`, or local-dev via `MCP_URL` + `MCP_API_KEY`).
- [x] 2.4 Keep the `DOCKER_DEFAULT_PLATFORM` note below the table. Do not add a Deprecated subsection (no deprecated vars).
- [x] 2.5 Update the table-of-contents: remove the `Required` / `Optional` sub-anchors under Environment variables (the single-table layout has no subheadings).

## 3. Tests

- [x] 3.1 Update `tests/conftest.py` (and any other fixture that constructs `Settings`/`create_app`) so `DIAL_URL` is set in the env — the removed default no longer supplies it.
- [x] 3.2 In `tests/test_settings.py`, add a test that a missing `DIAL_URL` raises at `Settings()` construction (fail-fast); confirm existing settings tests still pass.
- [x] 3.3 `make test` is green.

## 4. Verify and finalize

- [x] 4.1 `make format` and `make lint` are clean (README env table stays in sync with the settings per CLAUDE.md).
- [x] 4.2 Verified fail-fast/boot behavior directly (settings singleton loads at import): with `DIAL_URL` unset the process exits non-zero with a pydantic error naming `dial_url`; with `DIAL_URL` set, `create_app()` succeeds. Full docker-stack boot not run — the change's runtime surface is the settings requirement, exercised here.
- [x] 4.3 `openspec validate --change reformat-env-docs-and-require-dial-url` passes.
