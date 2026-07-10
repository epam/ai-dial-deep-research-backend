## MODIFIED Requirements

### Requirement: Docker Compose stack brings up the DIAL infrastructure
The repository SHALL provide a `docker-compose.yml` defining the four DIAL infrastructure services — DIAL core, DIAL chat UI, a themes server, and a redis for DIAL core — started and stopped by `make infra-up` / `make infra-down`. The app itself SHALL run on the host via `make app` (not in a container); DIAL core reaches the host-running app at `http://host.docker.internal:5000`. The `core` service SHALL mount `dial_conf/core/` as a directory and load its config as a file list via `aidial.config.files`: the generated `generated/models.json`, the rendered `generated/application-schemas.json`, and the local `applications.json` — the legacy single hand-written `dial_conf/core/config.json` SHALL NOT be read. This trade favours iteration speed and trivial IDE debugging over prod-parity; a future change can add an app Dockerfile + compose overlay when deployment becomes real.

#### Scenario: Infrastructure cold start
- **WHEN** a contributor runs `make infra-config` (with remote DIAL credentials in `.env`) followed by `make infra-up` on a freshly cloned repo with Docker running
- **THEN** the four infrastructure services (core, chat, themes, redis) SHALL reach a running state and the chat UI SHALL be reachable at `http://localhost:3000`

#### Scenario: App start on the host
- **WHEN** a contributor runs `make app` after `make infra-up`
- **THEN** the app SHALL start on the host via `poetry run python -m dial_deep_research`, bound to port 5000, reachable by DIAL core via `host.docker.internal:5000`

#### Scenario: Offline operation
- **WHEN** the stack is started with previously generated config files and without any cloud LLM provider keys configured (DIAL Core itself runs locally, `MCP_API_KEY` is configured for the local generic-RAG MCP, and `DIAL_API_KEY` resolves to a local DIAL Core service key)
- **THEN** it SHALL still start successfully and the `deep-research` deployment SHALL be reachable through the chat UI; if the configured MCP server itself is unreachable, agent requests SHALL surface the friendly error string but the stack SHALL still come up
