# Proposal: per-request-dial-auth

## Why

In normal DIAL operation, Core proxies each request to the application with **per-request
credentials** — the `Api-Key` header, and sometimes an `Authorization: Bearer <JWT>`. The app
must authenticate its downstream calls (LLM, DIAL Core file operations, the RAG MCP server)
with *those* credentials so per-user file access, spend/quota attribution, and per-user RAG
scoping work. Today the app uses one static service key (`DIAL_API_KEY`, `MCP_API_KEY`) for
everything, which breaks all three. Separately, in real deployment the generic-RAG MCP server
is *itself a DIAL application* reached through Core; the current static `MCP_URL` + `MCP_API_KEY`
config only fits a locally-run external MCP and will not work in deployment.

## What Changes

- Enable the DIAL SDK's auth-header propagation (`DIALApp(propagate_auth_headers=True)`) so the
  per-request `api-key` is automatically used on every outgoing call whose URL is under DIAL
  Core — covering LLM calls, DIAL file operations, and the Core-hosted MCP — with no manual key
  threading.
- Stop using the static service key on the request path: construct the LLM client
  (`AzureChatOpenAI`) and the `AsyncDial` client with an obviously-fake placeholder key that the
  propagator overwrites per request.
- **BREAKING** (deployment config): remove the `DIAL_API_KEY` environment variable — no longer
  used.
- Rework the MCP connection into two modes:
  - *Deployment mode*: the RAG MCP is a DIAL application reached through Core at
    `{DIAL_URL}/v1/deployments/{MCP_DEPLOYMENT_NAME}/mcp`, authenticated with the per-request
    api-key (supplied by propagation).
  - *Local-dev mode*: a directly-reachable MCP via static `MCP_URL` + `MCP_API_KEY` (today's
    behavior, kept).
- Forward the per-request JWT (`request.bearer_token`) to the RAG MCP as `Authorization: Bearer`
  when present. The propagator cannot carry the JWT, so this is threaded explicitly; it is
  required for per-user RAG access. LLM calls remain **api-key only** (no JWT).
- **BREAKING** (deployment config): `MCP_URL` and `MCP_API_KEY` become optional (local-dev
  only); add `MCP_DEPLOYMENT_NAME` for deployment mode; exactly one mode must be configured.
- Update the README environment-variables table and `.env.example` to match.

Out of scope: any `AuthContext`/credential abstraction class (the only explicitly-threaded
value is the optional bearer token); forwarding the JWT to the LLM endpoint; changes to the
preparation agent, research nodes, or research graph (they have no downstream auth surface).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dial-agent-with-mcp`: the **MCP-authentication**, **LLM-authentication**, and
  **environment-configuration** requirements change. Downstream DIAL calls now use the
  per-request api-key (via SDK header propagation) instead of the static `DIAL_API_KEY`; the MCP
  connection gains a deployment mode (application-through-Core with per-request api-key + JWT
  forwarding) alongside the existing local-dev static-key mode; `DIAL_API_KEY` is removed and the
  MCP env vars become mode-based (`MCP_URL`/`MCP_API_KEY` optional, new `MCP_DEPLOYMENT_NAME`).

## Impact

- **Code**: `app/factory.py` (enable propagation); `utils/llm.py` (placeholder key);
  `app/completion.py` (placeholder `AsyncDial`, read `request.bearer_token`);
  `app/research/runner.py` + `app/research/tools.py` (bearer threading + two-mode MCP client);
  `settings.py` (remove `dial_api_key`; add `mcp_deployment_name`; make `mcp_url`/`mcp_api_key`
  optional; add mode validator).
- **Config / ops**: `DIAL_API_KEY` removed; `MCP_DEPLOYMENT_NAME` added; `MCP_URL`/`MCP_API_KEY`
  optional. Deployments must set `MCP_DEPLOYMENT_NAME` and drop `DIAL_API_KEY`.
- **Tests & docs**: `tests/test_llm.py`, new MCP-mode and settings-validator tests,
  `tests/conftest.py`; README env-var table and `.env.example`.
- **Dependencies**: none new (uses existing `aidial-sdk` propagation and
  `langchain-mcp-adapters`).
- **Behavior**: a bad/absent per-request key now yields a 401 where the shared static key used
  to "work" — correct behavior that surfaces latent misconfiguration; verify end-to-end on the
  local stack.
