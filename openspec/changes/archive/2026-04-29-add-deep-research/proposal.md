## Why

The repo currently ships only an echo placeholder; the README calls out "Future changes plug in the generic-rag MCP and implement real deep-research orchestration" as the next step. This change does that on a deliberately small feature surface (one tool-calling agent, one MCP server, no planning/subagents/skills/memory) but **fully** establishes the patterns the larger deep-research orchestration will build on: per-request resource scoping, GPT-5 / DIAL Core wiring, static-service-key auth for both downstream services (DIAL Core + MCP), tool calls and tool results streamed as timed DIAL stages, separation between LangChain message history (full) and DIAL chat content (assistant text only), and a single top-level error funnel. The deep-research app will eventually route to different per-client generic-RAG deployments; for this MVP we hardcode a single deployment.

## What Changes

- Add a new DIAL chat completion deployment named `deep-research`, backed by a LangChain tool-calling agent that connects to a single HTTP MCP server with `api-key` header authentication.
- **BREAKING** Replace the `echo` deployment with `deep-research`. The echo-specific behavior (`echo: <text>` reply for the last user message) is removed. The structural requirements echo-app pioneered (DIAL-protocol conformance, streaming response path, health endpoint) are conserved and exercised by the new completion.
- The agent and the MCP client are constructed **fresh per chat-completion request**, with a hardcoded system prompt. The agent has access to **only** the MCP-loaded tools — no planning, subagents, skills, or checkpointer/store.
- Tool calls and tool results are surfaced as timed DIAL stages (one stage per call, one per result, titles include start/end timestamps + elapsed seconds). Only assistant text streams to the DIAL response; tool messages are stages-only and are not persisted across turns.
- Top-level exception handler funnels every failure (MCP unreachable, MCP tool error, LLM error, malformed input) into: log the exception server-side, append a friendly fixed string to the assistant's message ("Sorry, something went wrong …") via `choice.append_content`. The handler does **not** re-raise — the request completes successfully from DIAL's perspective. No fallback / retry; finer error classification deferred.
- LLM configuration targets GPT-5-family models only, accessed via DIAL Core. The shape is `LLMModelConfig` / `LLMModelsEnum` / `get_chat_model`, with a single config instance.
- **Static service keys for both downstream services**: LLM calls authenticate to DIAL Core using `DIAL_API_KEY`; MCP calls authenticate to the generic-RAG server using `MCP_API_KEY` sent as `api-key: <key>`. The handler does **not** read `request.api_key` — billing and quotas land at the service level. No auth-context / system-user-role machinery is adopted; we have no call site that would benefit from it.
- Add runtime dependencies: `langchain`, `langchain-mcp-adapters`, `langchain-openai`.

Out of scope for this change: stdio MCP transport, multiple MCP servers, MCP resources/prompts, models outside GPT-5, configurable system prompts, MCP-tool-allowlist filtering, cross-turn tool-message state persistence.

## Capabilities

### New Capabilities

- `deep-research`: A DIAL chat completion that, on each request, opens an HTTP MCP client, runs a tool-calling agent over the MCP-exposed tools, streams tool calls/results as timed stages and assistant text as message content, and funnels failures into a logged-and-replaced friendly assistant message (no exception propagation). Includes the structural DIAL-app requirements absorbed from `echo-app` (DIAL-protocol conformance, streaming path, health endpoint).

### Modified Capabilities

- `echo-app`: all requirements are removed. The structural ones (DIAL-protocol conformance, streaming response path, health endpoint) are restated under `deep-research`. "Echo behavior for the last user message" is dropped outright (no replacement). "Local run without Docker" is dropped as redundant with `dev-environment`'s `make run` target.
- `local-stack`: the "Echo app registered as a DIAL application" requirement is removed and replaced with a new "Deep Research app registered as a DIAL application" requirement (deployment id `deep-research`, display label `Deep Research`, endpoint URL updated). The offline-operation scenario in the Compose-stack requirement is modified to reference the new deployment. The "Pinned infrastructure images" requirement is extended to add `epam/ai-dial-adapter-dial:0.6.0`, and a new requirement covers the adapter service's role (DIAL Core → adapter → upstream LLM provider). Compose V2 syntax and `.env`-driven configuration are unchanged.
- `dev-environment`: the "Minimal developer README" requirement updates illustrative text from `Echo` / `echo app` to `Deep Research` / `deep-research`. Tooling (uv, black, isort, ruff, mypy), pinned Python version, Makefile target inventory, and code-quality scenarios are unchanged.
- `app-config`: the "App factory consumes the setting" scenario under the heartbeat-interval requirement updates illustrative text from "the echo chat completion" to "the deep-research chat completion". Field validation and parameter wiring are unchanged.

## Impact

- **Code**: new modules under `src/dial_deep_research/app/` for the MCP client, the LLM config + factory, the timed-stage helpers, and the top-level error handler. `app/completion.py` is reused — `EchoCompletion` is replaced in place by the agent-backed handler. `factory.py` re-registers `deep-research` instead of `echo`. `settings.py` gains `dial_api_key` on `DialAppSettings` plus a new `McpSettings` class (`mcp_url`, `mcp_api_key`); `LLM_MODELS_*` env reads happen inside `LLMModelsEnum.deployment_id` directly.
- **Dependencies**: `langchain`, `langchain-mcp-adapters`, `langchain-openai` added to `pyproject.toml` / `uv.lock`.
- **Configuration**: `.env.example` gains MCP server URL, `MCP_API_KEY` (sent as `api-key: <key>`), and clarifies `DIAL_API_KEY` is also used by the deep-research app for LLM calls via DIAL Core. `LLM_MODELS_<NAME>` env vars are supported as optional overrides (default falls back to the enum member's `.value`) and not required in `.env.example`. No existing env vars change.
- **Local stack**: `docker-compose.yml` gains an `ai-dial-adapter-dial` service (image `epam/ai-dial-adapter-dial:0.6.0`). Required so the GPT-5 model declared in `dial_conf/core/config.json` can route from DIAL Core through the adapter to the upstream LLM provider; without it LLM calls fail. The MCP server itself is still out of scope — the agent points at an externally-running generic-RAG MCP via configuration.
- **DIAL surface**: `Echo` disappears from the chat UI; the new deployment shows as `Deep Research`. The `dial_conf/core/config.json` `applications` block, role limits, and endpoint URL are updated from `echo` → `deep-research`. Anyone with `Echo` selected will need to pick the new deployment.
- **README**: the "send `hello`, get `echo: hello`" first-run example is updated as part of this change.
