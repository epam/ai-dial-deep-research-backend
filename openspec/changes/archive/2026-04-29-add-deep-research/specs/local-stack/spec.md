## MODIFIED Requirements

### Requirement: Docker Compose stack brings up the DIAL infrastructure
The repository SHALL provide a `docker-compose.yml` defining the four DIAL infrastructure services — DIAL core, DIAL chat UI, a themes server, and a redis for DIAL core — started and stopped by `make up` / `make down`. The app itself SHALL run on the host via `make run` (not in a container): DIAL core reaches the host-running app at `http://host.docker.internal:5000`. This trade favours iteration speed and trivial IDE debugging over prod-parity; a future change can add an app Dockerfile + compose overlay when deployment becomes real.

#### Scenario: Infrastructure cold start
- **WHEN** a contributor runs `make up` on a freshly cloned repo with Docker running
- **THEN** the four infrastructure services (core, chat, themes, redis) SHALL reach a running state and the chat UI SHALL be reachable at `http://localhost:3000`

#### Scenario: App start on the host
- **WHEN** a contributor runs `make run` after `make up`
- **THEN** the app SHALL start on the host via `uv run python -m dial_deep_research`, bound to port 5000, reachable by DIAL core via `host.docker.internal:5000`

#### Scenario: Offline operation
- **WHEN** the stack is started without any cloud LLM provider keys configured (DIAL Core itself runs locally, `MCP_API_KEY` is configured for the local generic-RAG MCP, and `DIAL_API_KEY` resolves to a local DIAL Core service key)
- **THEN** it SHALL still start successfully and the `deep-research` deployment SHALL be reachable through the chat UI; if the configured MCP server itself is unreachable, agent requests SHALL surface the friendly error string but the stack SHALL still come up

### Requirement: Pinned infrastructure images
The compose file SHALL pin concrete image tags (not `latest`) for the upstream DIAL core, chat UI, themes, redis, and DIAL adapter services: `epam/ai-dial-core:0.42.0`, `epam/ai-dial-chat:0.36.0`, `epam/ai-dial-chat-themes:0.10.0`, `redis:7.2.4-alpine3.19`, `epam/ai-dial-adapter-dial:0.6.0`.

#### Scenario: Reproducible stack
- **WHEN** two contributors run `make up` on different machines at different times without pulling new tags
- **THEN** they SHALL run the same upstream DIAL image versions

## REMOVED Requirements

### Requirement: Echo app registered as a DIAL application
**Reason**: Renamed and rewritten — the application registered in DIAL core is no longer the echo placeholder.
**Migration**: See the new "Deep Research app registered as a DIAL application" requirement under ADDED Requirements in this delta.

## ADDED Requirements

### Requirement: DIAL adapter routes LLM calls to the upstream provider
The compose stack SHALL run an `ai-dial-adapter-dial` service (image `epam/ai-dial-adapter-dial:0.6.0`) that exposes the OpenAI-compatible chat-completion endpoint at `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions` on the docker network and forwards each call to the configured upstream LLM provider declared in `dial_conf/core/config.json`'s `models.<model>.upstreams` block. The adapter SHALL connect back to DIAL core via `DIAL_URL=http://core:8080` so it can resolve per-request configuration.

#### Scenario: Model endpoint resolves on the docker network
- **WHEN** DIAL core proxies a chat-completion request whose target model declares an `endpoint` of `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions`
- **THEN** the request SHALL reach the `ai-dial-adapter-dial` service via docker DNS, the adapter SHALL forward it to the configured upstream, and the response SHALL stream back through the same path

#### Scenario: Adapter not exposed on host
- **WHEN** the stack is up
- **THEN** the adapter SHALL be reachable only on the docker network (no host port mapping); host code (the dial-deep-research app) MUST go through DIAL core at `http://localhost:8080` rather than the adapter directly

### Requirement: Deep Research app registered as a DIAL application
The DIAL core configuration SHALL register the host-running app as an application (deployment id: `deep-research`, display name: `Deep Research`) whose endpoint points at `http://host.docker.internal:5000/openai/deployments/deep-research/chat/completions`, and SHALL ship a single API key (name: `dial_api_key`, role: `default`) under which the chat UI can invoke that application.

#### Scenario: Application visible in chat UI
- **WHEN** a contributor opens the chat UI after the stack is up
- **THEN** the application labelled `Deep Research` (deployment id `deep-research`) SHALL appear as a selectable application/agent in the UI

#### Scenario: Routing to the host-running app
- **WHEN** a user sends a message to the `Deep Research` application from the chat UI
- **THEN** the request SHALL be proxied by DIAL core to the host-running app over `host.docker.internal:5000` at the `deep-research` deployment path, and the app SHALL receive it
