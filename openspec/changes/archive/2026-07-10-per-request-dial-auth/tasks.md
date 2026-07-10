# Tasks: per-request-dial-auth

## 1. Settings — MCP modes and drop DIAL_API_KEY

- [x] 1.1 Remove the `dial_api_key` field from `Settings` (`src/dial_deep_research/settings.py`).
- [x] 1.2 Add `mcp_deployment_name: str | None = None`; make `mcp_url: HttpUrl | None = None` and `mcp_api_key: SecretStr | None = None` optional; keep `mcp_server_name` required.
- [x] 1.3 Add a model validator enforcing exactly one MCP mode: `mcp_url` set ⇒ local-dev mode (requires `mcp_api_key`); otherwise deployment mode (requires `mcp_deployment_name`); neither set ⇒ error. The error message SHALL name the missing/conflicting variable.

## 2. Per-request api-key via SDK header propagation

- [x] 2.1 In `app/factory.py`, construct `DIALApp` with `propagate_auth_headers=True` (`dial_url` is already passed).
- [x] 2.2 In `utils/llm.py`, replace `api_key=settings.dial_api_key` with an obviously-fake placeholder constant (`SecretStr("propagated-per-request")`); add a short comment that the propagator overwrites the `api-key` header per request.
- [x] 2.3 In `app/completion.py`, build `AsyncDial` with the same placeholder api-key (drop `settings.dial_api_key`).

## 3. MCP rework and bearer threading

- [x] 3.1 In `app/research/tools.py`, change `build_mcp_client` to take `bearer_token: str | None` and select a mode from settings: deployment mode → URL `{dial_url}/v1/deployments/{mcp_deployment_name}/mcp`, headers add `Authorization: Bearer <bearer_token>` only when present (api-key comes from propagation); local-dev mode → `mcp_url` with `headers={"api-key": mcp_api_key}` and no `Authorization`.
- [x] 3.2 In `app/research/tools.py`, thread `bearer_token` through `load_research_tools` into `build_mcp_client`.
- [x] 3.3 In `app/research/runner.py`, add `bearer_token: str | None` to `ResearchRunner.run(...)` and pass it to `load_research_tools`.
- [x] 3.4 In `app/completion.py`, read `request.bearer_token` in `_run_turn` and pass it to `ResearchRunner.run(...)`. (Preparation path is untouched — no MCP tools there.)

## 4. Tests

- [x] 4.1 `tests/conftest.py` already sets the local-dev-mode MCP env (`MCP_SERVER_NAME` + `MCP_URL` + `MCP_API_KEY`), which satisfies the new validator; `create_app()` still loads. No change needed.
- [x] 4.2 Added settings-validator tests: deployment mode loads; local-dev mode loads; `MCP_URL` without `MCP_API_KEY` raises; neither `MCP_URL` nor `MCP_DEPLOYMENT_NAME` raises.
- [x] 4.3 Added `tests/test_mcp_client.py`: deployment mode builds the Core URL and sets `Authorization: Bearer` when a bearer is passed and omits it otherwise; local-dev mode uses the static url + `api-key` header and no `Authorization`.
- [x] 4.4 Updated `tests/test_llm.py` to assert the placeholder api-key is used; existing deployment/reasoning/verbosity assertions still pass.
- [x] 4.5 Added `tests/test_auth_propagation.py`: `create_app()` enables auth-header propagation.
- [x] 4.6 `make test` is green (102 passed).

## 5. Docs

- [x] 5.1 README env-var section: removed `DIAL_API_KEY`; added `MCP_DEPLOYMENT_NAME`; documented the two MCP modes and the per-request-auth note.
- [x] 5.2 Updated `.env.example` to show the two MCP modes (both commented; pick one).
- [x] 5.3 Updated the `dial-agent-with-mcp` capability **Purpose** prose (static `DIAL_API_KEY` / no per-request forwarding) by hand during archive, since the delta covers requirements only.

## 6. Verify and finalize

- [x] 6.1 `make format` and `make lint` are clean (ruff, black, isort, mypy).
- [ ] 6.2 End-to-end on the live stack: a chat turn's LLM and MCP calls carry the per-request api-key; the bearer is forwarded to the MCP when present; confirm the RAG MCP accepts the Core-issued key. **Manual — requires the running DIAL stack + a real RAG-MCP; not runnable in this environment. See design Open Questions.**
- [x] 6.3 `openspec validate per-request-dial-auth --strict` passes.
