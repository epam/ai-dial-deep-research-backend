# Design: per-request-dial-auth

## Context

The app makes three kinds of authenticated downstream calls, all currently using static
settings keys built inside a request but never using the request's own credentials:

1. `AsyncDial` (`app/completion.py`) → DIAL Core file/attachment operations — `settings.dial_api_key`.
2. `AzureChatOpenAI` (`utils/llm.py`, used by the prep agent and all three research nodes) → the
   DIAL Core LLM endpoint — `settings.dial_api_key`.
3. The MCP client (`app/research/tools.py`) → the generic-RAG MCP server — static
   `settings.mcp_url` + `settings.mcp_api_key`.

DIAL Core forwards each request to the app with a per-request `Api-Key` header (required by the
SDK; exposed as `request.api_key`) and sometimes an `Authorization: Bearer <JWT>` (exposed as
`request.bearer_token`; `request.jwt` is deprecated). The app must use those. Two references
informed this design: statgpt-backend (an explicit auth-context threaded to every client) and
the QuickApps backend (connecting to an application-hosted MCP through Core at
`{DIAL_URL}/v1/deployments/{id}/mcp` with per-request `Api-Key` + `Bearer`).

The DIAL SDK (`aidial-sdk` 0.32.0) ships `DIALApp(propagate_auth_headers=True)`: a FastAPI
middleware captures the incoming `api-key` into a request-scoped `ContextVar`, and it patches
httpx/aiohttp/requests so any outgoing call whose URL starts with `dial_url` has its `api-key`
header rewritten to the per-request value. It does **not** capture or forward the bearer/JWT.

## Goals / Non-Goals

**Goals:**
- Authenticate LLM calls, DIAL file operations, and the RAG MCP with the per-request api-key.
- Forward the per-request JWT to the RAG MCP when present (per-user RAG access).
- Make the RAG MCP reachable as a DIAL application through Core in deployment, while keeping a
  local-dev path to a directly-reachable MCP.
- Remove the static `DIAL_API_KEY` from the request path.

**Non-Goals:**
- No `AuthContext`/credentials abstraction class — the only explicitly-threaded value is the
  optional bearer token.
- No JWT forwarding to the LLM endpoint (LLM auth is api-key only).
- No changes to the preparation agent, research nodes, or research graph (no downstream auth
  surface there — the prep agent has no MCP tools).
- No switch away from `langchain-mcp-adapters` / streamable HTTP.

## Decisions

### D1 — Rely on SDK header propagation for the api-key (not explicit threading)
Enable `DIALApp(propagate_auth_headers=True)`. Once the MCP is reached through Core, all three
call sites live under `dial_url`, so the propagator supplies the per-request api-key to every one
of them with zero key-threading through the agent/graph/runner layers.
- *Alternative — statgpt-style explicit `AuthContext` threaded to every client.* More faithful to
  one reference, fully testable, and forwards JWT explicitly — but it threads a parameter through
  `PrepAgentRunner`, `build_prep_agent`, `get_chat_model`, `ResearchRunner`, `build_research_graph`,
  and three node factories. Rejected: propagation achieves the api-key goal (the hard requirement)
  with a fraction of the churn. We keep only the one thread propagation can't do (the bearer).

### D2 — Placeholder api-key at client construction
`AzureChatOpenAI` and `AsyncDial` both require a credential at construction. Build both with an
obviously-fake placeholder (e.g. `"propagated-per-request"`); the propagator overwrites the
`api-key` header per request. `DIAL_API_KEY` is dropped entirely.
- *Alternative — thread the real per-request key into these constructors.* Rejected: contradicts
  D1 and reintroduces the threading D1 avoids.

### D3 — Two-mode MCP configuration
`build_mcp_client(bearer_token)` selects a mode from settings:
- **Deployment mode** (`MCP_DEPLOYMENT_NAME` set): URL `{dial_url}/v1/deployments/{name}/mcp`
  (route confirmed for our DIAL Core), api-key via propagation, `Authorization: Bearer` added when
  a bearer is present.
- **Local-dev mode** (`MCP_URL` set): static `MCP_URL` + `api-key: MCP_API_KEY`, no bearer.
A settings validator enforces exactly one mode. `MCP_SERVER_NAME` stays the logical connection
key; transport stays streamable HTTP; the client stays per-request.
- *Alternative — always go through Core.* Rejected: breaks local dev where the MCP runs as a
  separate host process (`host.docker.internal`), which isn't a Core deployment.

### D4 — JWT forwarded only to the RAG MCP
The propagator can't carry the JWT, so `request.bearer_token` is threaded explicitly and sent as
`Authorization: Bearer` to the RAG MCP in deployment mode when present. This is the only threading
in the change: `completion._run_turn` → `ResearchRunner.run(bearer_token=…)` →
`load_research_tools(bearer_token=…)` → `build_mcp_client(bearer_token=…)`.
- *Alternatives:* forward the JWT everywhere (rejected — LLM is api-key only per requirement; Core
  file ops work off the per-request api-key) or nowhere (rejected — the RAG server enforces
  per-user access and QuickApps forwards the bearer to DIAL-internal MCPs).

## Risks / Trade-offs

- **Propagation is `ContextVar`-based** → LangGraph `astream`/`ainvoke` run in the same async
  task, so it propagates; but any hop to a worker *thread* would lose it. → Verify end-to-end on
  the local stack that LLM and MCP calls carry the per-request key.
- **Placeholder key hides misconfiguration if propagation is inactive** (e.g. a test without the
  middleware) → DIAL calls would go out with the placeholder and 401. → Keep the placeholder
  obviously-fake; cover the propagation wiring in tests; rely on E2E.
- **Bad/absent per-request key → 401 where the static key used to "work"** → this is correct and
  surfaces latent misconfig; the existing top-level error funnel still returns the friendly
  message. → Confirm on the local stack that the dev key (`dial_api_key`, `default` role) is
  authorized for the LLM model deployments.
- **RAG MCP auth model unverified** — whether it needs the bearer or authorizes off the
  Core-issued api-key. → Forward the bearer when present (harmless if ignored); verify E2E.
- **MCP route differs across DIAL Core versions** → confirmed `/v1/deployments/{name}/mcp` for our
  Core; documented so a future Core change is a one-line URL edit.

## Migration Plan

- **Deployment**: register the generic-RAG MCP server as a DIAL application; set
  `MCP_DEPLOYMENT_NAME`; remove `DIAL_API_KEY`; leave `MCP_URL`/`MCP_API_KEY` unset.
- **Local dev**: unchanged — keep `MCP_URL` + `MCP_API_KEY` (local-dev mode); the app no longer
  reads `DIAL_API_KEY` (the stack's own `DIAL_API_KEY`, used by the chat UI → Core, is a separate
  variable and is untouched).
- **Rollback**: revert the code change and restore `DIAL_API_KEY` + the static MCP config. The
  change is code + config only (no data migration).

## Open Questions

- Does the generic-RAG MCP server accept the Core-issued per-request api-key, and does it actually
  require the forwarded bearer? (Resolve during E2E.)
- The `dial-agent-with-mcp` capability **Purpose** paragraph (and any README prose) still states
  "static service `DIAL_API_KEY` / does not forward per-request user keys." The delta operates on
  requirements only, so this prose must be updated by hand when syncing/archiving the spec.
