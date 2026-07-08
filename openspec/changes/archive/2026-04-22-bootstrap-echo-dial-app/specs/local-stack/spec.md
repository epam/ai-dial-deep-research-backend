## ADDED Requirements

### Requirement: Docker Compose stack brings up the DIAL infrastructure
The repository SHALL provide a `docker-compose.yml` defining the four DIAL infrastructure services — DIAL core, DIAL chat UI, a themes server, and a redis for DIAL core — started and stopped by `make up` / `make down`. The app itself SHALL run on the host via `make run` (not in a container): DIAL core reaches the host-running app at `http://host.docker.internal:5000`. This trade favours iteration speed and trivial IDE debugging over prod-parity; a future change can add an app Dockerfile + compose overlay when deployment becomes real.

#### Scenario: Infrastructure cold start
- **WHEN** a contributor runs `make up` on a freshly cloned repo with Docker running
- **THEN** the four infrastructure services (core, chat, themes, redis) SHALL reach a running state and the chat UI SHALL be reachable at `http://localhost:3000`

#### Scenario: App start on the host
- **WHEN** a contributor runs `make run` after `make up`
- **THEN** the app SHALL start on the host via `uv run python -m dial_deep_research`, bound to port 5000, reachable by DIAL core via `host.docker.internal:5000`

#### Scenario: Offline operation
- **WHEN** the stack is started without any cloud API keys configured
- **THEN** it SHALL still start successfully and the `echo` deployment SHALL be usable through the chat UI, since no external LLM provider is required

### Requirement: Echo app registered as a DIAL application
The DIAL core configuration SHALL register the host-running app as an application (name: `echo`) whose endpoint points at `http://host.docker.internal:5000/openai/deployments/echo/chat/completions`, and SHALL ship a single API key (name: `dial_api_key`, role: `default`) under which the chat UI can invoke that application.

#### Scenario: Application visible in chat UI
- **WHEN** a contributor opens the chat UI after the stack is up
- **THEN** the application named `echo` SHALL appear as a selectable application/agent in the UI

#### Scenario: Routing to the host-running app
- **WHEN** a user sends a message to the `echo` application from the chat UI
- **THEN** the request SHALL be proxied by DIAL core to the host-running app over `host.docker.internal:5000`, and the app SHALL receive it

### Requirement: Pinned infrastructure images
The compose file SHALL pin concrete image tags (not `latest`) for the upstream DIAL core, chat UI, themes, and redis services: `epam/ai-dial-core:0.42.0`, `epam/ai-dial-chat:0.36.0`, `epam/ai-dial-chat-themes:0.10.0`, `redis:7.2.4-alpine3.19`.

#### Scenario: Reproducible stack
- **WHEN** two contributors run `make up` on different machines at different times without pulling new tags
- **THEN** they SHALL run the same upstream DIAL image versions

### Requirement: Environment configuration via .env
The stack SHALL read environment configuration from a `.env` file at the repo root, and the repository SHALL ship an `.env.example` documenting the supported variables. At minimum the `.env` file SHALL expose the DIAL API key used by the chat UI to call DIAL core.

#### Scenario: Default bring-up
- **WHEN** a contributor copies `.env.example` to `.env` without modifications and runs `make up` followed by `make run`
- **THEN** the stack SHALL start on the default ports (chat UI at 3000, DIAL core at 8080, themes at 3001, app at 5000 on the host)

### Requirement: Compose V2 syntax
The compose file SHALL target Compose V2 and SHALL NOT include a top-level `version:` key.

#### Scenario: Modern Docker Desktop
- **WHEN** the stack is launched with Docker Desktop ≥ 4.x / Compose V2
- **THEN** no deprecation warnings SHALL be emitted by `docker compose config`
