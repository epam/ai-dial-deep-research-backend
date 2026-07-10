# local-stack

## Purpose

The local DIAL stack: four infrastructure services (DIAL core, chat UI, themes, redis) managed by `make infra-up` / `make infra-down`, plus a host-running app that DIAL core reaches via `host.docker.internal:<APP_PORT>`. Core's config is split into generated and local files built by `make infra-config` (models pulled from a remote DIAL, the app-type registration rendered with the app port, client instances seeded from a committed template). Pinned image versions, `.env`-driven configuration, and Compose V2 syntax keep the experience reproducible from first clone forward.

## Requirements

### Requirement: Docker Compose stack brings up the DIAL infrastructure
The repository SHALL provide a `docker-compose.yml` defining the four DIAL infrastructure services — DIAL core, DIAL chat UI, a themes server, and a redis for DIAL core — started and stopped by `make infra-up` / `make infra-down`. The app itself SHALL run on the host via `make app` (not in a container); DIAL core reaches the host-running app at `http://host.docker.internal:5000`. The `core` service SHALL mount `dial_conf/core/` as a directory and load its config as a file list via `aidial.config.files`: the generated `generated/models.json`, the rendered `generated/application-schemas.json`, and the local `applications.json` — the legacy single hand-written `dial_conf/core/config.json` SHALL NOT be read. This trade favours iteration speed and trivial IDE debugging over prod-parity; a future change can add an app Dockerfile + compose overlay when deployment becomes real.

#### Scenario: Infrastructure cold start
- **WHEN** a contributor runs `make infra-config` (with remote DIAL credentials in `.env`) followed by `make infra-up` on a freshly cloned repo with Docker running
- **THEN** the four infrastructure services (core, chat, themes, redis) SHALL reach a running state and the chat UI SHALL be reachable at `http://localhost:3000`

#### Scenario: App start on the host
- **WHEN** a contributor runs `make app` after `make infra-up`
- **THEN** the app SHALL start on the host via `uv run python -m dial_deep_research`, bound to port 5000, reachable by DIAL core via `host.docker.internal:5000`

#### Scenario: Offline operation
- **WHEN** the stack is started with previously generated config files and without any cloud LLM provider keys configured (DIAL Core itself runs locally, `MCP_API_KEY` is configured for the local generic-RAG MCP, and `DIAL_API_KEY` resolves to a local DIAL Core service key)
- **THEN** it SHALL still start successfully and the `deep-research` deployment SHALL be reachable through the chat UI; if the configured MCP server itself is unreachable, agent requests SHALL surface the friendly error string but the stack SHALL still come up

### Requirement: DIAL adapter routes LLM calls to the upstream provider
The compose stack SHALL run an `ai-dial-adapter-dial` service (image `epam/ai-dial-adapter-dial:0.16.0`) that exposes the OpenAI-compatible chat-completion endpoint at `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions` on the docker network and forwards each call to the configured upstream LLM provider declared in `dial_conf/core/config.json`'s `models.<model>.upstreams` block. The adapter SHALL connect back to DIAL core via `DIAL_URL=http://core:8080` so it can resolve per-request configuration.

#### Scenario: Model endpoint resolves on the docker network
- **WHEN** DIAL core proxies a chat-completion request whose target model declares an `endpoint` of `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions`
- **THEN** the request SHALL reach the `ai-dial-adapter-dial` service via docker DNS, the adapter SHALL forward it to the configured upstream, and the response SHALL stream back through the same path

#### Scenario: Adapter not exposed on host
- **WHEN** the stack is up
- **THEN** the adapter SHALL be reachable only on the docker network (no host port mapping); host code (the dial-deep-research app) MUST go through DIAL core at `http://localhost:8080` rather than the adapter directly

### Requirement: Deep Research app registered as a DIAL application
The DIAL core configuration SHALL register Deep Research as a schema-rich application **type** plus at least one application **instance**, and SHALL ship a single API key (name: `dial_api_key`, role: `default`) under which the chat UI can invoke it:

- The type registration SHALL be authored in the committed `dial_conf/core/application-schemas-template.json` — an `applicationTypeSchemas` entry with display name `Deep Research`, `dial:applicationTypeCompletionEndpoint` pointing at `http://host.docker.internal:$env:{APP_PORT}/openai/deployments/deep-research/chat/completions`, `dial:applicationTypeSchemaEndpoint` pointing at `http://host.docker.internal:$env:{APP_PORT}/v1/configuration-support/application-schema`, and `dial:appendApplicationPropertiesHeader: false` — and rendered by `make infra-config` into the gitignored `dial_conf/core/generated/application-schemas.json`, substituting `$env:{APP_PORT}` with the `APP_PORT` environment value (default `5000`, the same variable that drives the app's bind port). Rendering SHALL fail on placeholder tokens it cannot resolve. Core's settings (`dial_conf/settings/settings.json`) SHALL keep `applications.includeCustomApps` enabled.
- Application instances SHALL live in the gitignored local `dial_conf/core/applications.json` (seeded from the committed template), each referencing the type via `applicationTypeSchemaId` and carrying an `applicationProperties` object valid against the schema.
- The API key SHALL ship in the committed `dial_conf/core/models-template.json` and flow into the generated models config.

The README SHALL document this file layout and the instance-adding workflow; the committed template files themselves serve as the generic examples.

#### Scenario: Application visible in chat UI
- **WHEN** a contributor opens the chat UI after the stack is up
- **THEN** the application instance of type `Deep Research` SHALL appear as a selectable application/agent in the UI

#### Scenario: Routing to the host-running app with instance properties
- **WHEN** a user sends a message to a Deep Research instance from the chat UI
- **THEN** DIAL core SHALL proxy the request to the host-running app over `host.docker.internal:5000` at the `deep-research` deployment path with the application identity attached, and the turn SHALL run with that instance's `applicationProperties`

#### Scenario: Core loads the schema from the app
- **WHEN** DIAL core (>= 0.41.0) starts with the rendered `generated/application-schemas.json` loaded and the host app running
- **THEN** core SHALL fetch the property schema from the app's schema endpoint and accept instances whose `applicationProperties` validate against it

#### Scenario: Custom app port flows into the registration
- **WHEN** a contributor sets `APP_PORT=5001` in `.env` (e.g. because macOS AirPlay Receiver occupies port 5000) and runs `make infra-config` followed by `make infra-up` and `make app`
- **THEN** the rendered registration endpoints SHALL point at `host.docker.internal:5001`, the app SHALL bind port 5001, and a chat message to a Deep Research instance SHALL reach the app

### Requirement: Generated models config pulled from a remote DIAL

The repository SHALL provide a generator script (`scripts/generate_dial_config.py`) that
builds the local DIAL Core models config from a remote DIAL instance:

- It SHALL read `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` from the environment (loading
  `.env` like the app settings) and fail with a clear error when either is missing.
- It SHALL fetch model definitions from the remote DIAL through the `aidial-client` library
  (deployments listing plus per-model info), authenticated with the remote key.
- Each fetched model with a `chat_completion` or `embeddings` capability SHALL become a Core
  model entry whose `endpoint` routes through the local adapter
  (`http://ai-dial-adapter-dial:5000/openai/deployments/<id>/...`) with a single upstream at
  the remote DIAL deployment carrying the remote key; models with neither capability SHALL
  be skipped. Metadata present on the remote model (display fields, token limits, pricing,
  features) SHALL be emitted under the camelCase keys DIAL Core's config schema defines
  (e.g. `maxPromptTokens`, never the listing API's `max_prompt_tokens`) — Core parses its
  config strictly and fails to start on unknown keys.
- Fetched models SHALL be merged over the committed template
  `dial_conf/core/models-template.json` (which carries the `dial_api_key` key → `default`
  role skeleton), and `roles.default.limits` SHALL be rebuilt with an entry per model id so
  the `default` role can access every generated model.
- The output SHALL be written to `dial_conf/core/generated/models.json`, and that path SHALL
  be gitignored (it embeds the remote key in every upstream).

A `make infra-config` target SHALL run the generator (after seeding the local applications
file, see the template requirement). The generator SHALL also render the application-type
registration from its committed template (see the registration requirement) so one command
produces every local config file.

#### Scenario: Models generated from the remote

- **WHEN** a contributor with `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` set in `.env` runs
  `make infra-config`
- **THEN** `dial_conf/core/generated/models.json` SHALL exist, containing every remote
  chat/embedding model routed via `ai-dial-adapter-dial` with the remote as upstream, plus
  the template's `keys` and a `roles.default.limits` entry per model

#### Scenario: Token limits emitted in camelCase

- **WHEN** a remote model reports token limits (the listing API uses snake_case keys such as
  `max_prompt_tokens`)
- **THEN** the generated entry's `limits` SHALL use `maxPromptTokens` /
  `maxCompletionTokens` / `maxTotalTokens`, and DIAL Core SHALL start successfully on the
  generated config

#### Scenario: Missing remote credentials

- **WHEN** the generator runs without `REMOTE_DIAL_URL` or `REMOTE_DIAL_API_KEY` set
- **THEN** it SHALL exit with an error naming the missing variable and SHALL NOT write any
  output file

#### Scenario: Refresh overwrites the generated file

- **WHEN** `make infra-config` is re-run after models changed on the remote
- **THEN** `dial_conf/core/generated/models.json` SHALL be overwritten with the fresh model
  set

### Requirement: Local application instance config seeded from a committed template

The repository SHALL keep application instances (client configs) in a gitignored local file
`dial_conf/core/applications.json`, seeded from a committed generic template
`dial_conf/core/applications-template.json`:

- The template SHALL contain exactly one generic example instance (no real client names or
  other sensitive content), referencing the Deep Research type by `applicationTypeSchemaId`
  and carrying `applicationProperties` consistent with
  `data/configs/example-application-properties.json`, plus a `roles.default.limits` fragment
  granting the `default` role access to the example instance.
- `make infra-config` SHALL copy the template to `dial_conf/core/applications.json` when the
  local file does not exist, and SHALL NOT overwrite an existing local file.
- The README SHALL document that real client instances are added to the local
  `applications.json` (each with its `roles.default.limits` entry) and never committed.

#### Scenario: First-time seeding

- **WHEN** a contributor runs `make infra-config` on a fresh clone
- **THEN** `dial_conf/core/applications.json` SHALL be created as a copy of the committed
  template

#### Scenario: Existing local file preserved

- **WHEN** a contributor who already added client instances to `applications.json` re-runs
  `make infra-config`
- **THEN** the local file SHALL be left untouched while the generated models config is
  refreshed

#### Scenario: Local file stays out of git

- **WHEN** a contributor adds a real client instance to `dial_conf/core/applications.json`
  and runs `git status`
- **THEN** the file SHALL NOT appear as trackable (it is gitignored), while
  `applications-template.json` and `application-schemas-template.json` remain tracked

### Requirement: Pinned infrastructure images
The compose file SHALL pin concrete image tags (not `latest`) for the upstream DIAL core, chat UI, themes, redis, and DIAL adapter services: `epam/ai-dial-core:0.45.1`, `epam/ai-dial-chat:0.47.2`, `epam/ai-dial-chat-themes:0.17.0`, `redis:7.2.4-alpine3.19`, `epam/ai-dial-adapter-dial:0.16.0`.

#### Scenario: Reproducible stack
- **WHEN** two contributors run `make infra-up` on different machines at different times without pulling new tags
- **THEN** they SHALL run the same upstream DIAL image versions

### Requirement: Environment configuration via .env
The stack SHALL read environment configuration from a `.env` file at the repo root, and the repository SHALL ship an `.env.example` documenting the supported variables. At minimum the `.env` file SHALL expose the DIAL API key used by the chat UI to call DIAL core. `.env.example` SHALL additionally document the optional `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` variables consumed only by the config generator (`make infra-config`); the app itself SHALL NOT require them.

#### Scenario: Default bring-up
- **WHEN** a contributor copies `.env.example` to `.env` without modifications, generates the core config, and runs `make infra-up` followed by `make app`
- **THEN** the stack SHALL start on the default ports (chat UI at 3000, DIAL core at 8080, themes at 3001, app at 5000 on the host)

#### Scenario: App runs without remote DIAL credentials
- **WHEN** the app starts with `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` unset
- **THEN** the app SHALL start normally — the variables are consumed only by the generator script

### Requirement: Compose V2 syntax
The compose file SHALL target Compose V2 and SHALL NOT include a top-level `version:` key.

#### Scenario: Modern Docker Desktop
- **WHEN** the stack is launched with Docker Desktop ≥ 4.x / Compose V2
- **THEN** no deprecation warnings SHALL be emitted by `docker compose config`

### Requirement: Local Opik tracing stack runs independently of the infra stack

The repository SHALL provide a separate Compose lifecycle for a local self-hosted **Opik** instance (LLM trace ingestion + UI), plus two new Makefile targets:

- `opik-up` SHALL start the Opik services.
- `opik-down` SHALL stop the Opik services.

The implementation MAY ship its own self-contained `docker-compose.opik.yml`, OR delegate to Opik's upstream compose file by checking the upstream Opik repository out into a gitignored local path (e.g. `.opik-local/`) on first `make opik-up`. Either approach is acceptable provided the lifecycle-independence guarantees below hold. The Opik Compose project SHALL run under a different Compose project name from the infra stack (so `docker compose down` from the repo root never affects Opik containers) and a pinned Opik release version SHALL be used (no floating `latest` tag), consistent with the existing `Pinned infrastructure images` requirement.

The existing `docker-compose.yml`, `make infra-up`, and `make infra-down` SHALL NOT be modified to include Opik services — they continue to operate solely on the DIAL infrastructure (core, chat, themes, redis, ai-dial-adapter-dial). Conversely, `make opik-up` / `make opik-down` SHALL NOT touch the infra services. The two stacks have fully independent lifecycles: either side can be started, stopped, or restarted without disturbing the other.

When running, the local Opik instance SHALL expose:

- a UI reachable from the host at a stable, documented port,
- an ingestion endpoint reachable from the host-running deep-research app at `http://localhost:<port>` so the existing host-on-`5000` / Compose-on-Docker pattern (already established for DIAL core) continues to apply.

The repository SHALL NOT ship a `.env.example` (or equivalent) that pre-enables Opik tracing: `OPIK_TRACING_ENABLED` defaults to `False` in `Settings`, and contributors opt in by setting it (and the relevant connection vars) in their own local environment.

#### Scenario: `make infra-up` does not start Opik
- **WHEN** a contributor runs `make infra-up` on a freshly cloned repo
- **THEN** only the existing DIAL infrastructure services SHALL reach a running state; no Opik services SHALL be started, and `make infra-up` cold-start time and disk footprint SHALL be unchanged from before this change

#### Scenario: `make infra-down` does not stop Opik
- **WHEN** a contributor has previously run `make opik-up` (Opik services running) and then runs `make infra-down`
- **THEN** the DIAL infrastructure services SHALL stop, the Opik services SHALL remain running, and the Opik UI SHALL still be reachable from the host

#### Scenario: `make opik-up` does not start infra
- **WHEN** a contributor runs `make opik-up` on a freshly cloned repo without having run `make infra-up`
- **THEN** only the Opik services SHALL reach a running state; no DIAL infrastructure services SHALL be started

#### Scenario: `make opik-down` does not stop infra
- **WHEN** a contributor has previously run `make infra-up` (infra services running) and then runs `make opik-down`
- **THEN** the Opik services SHALL stop and the DIAL infrastructure services SHALL remain running

#### Scenario: End-to-end trace flow with both stacks up
- **WHEN** a contributor runs `make infra-up`, `make opik-up`, sets `OPIK_TRACING_ENABLED=true` in their local environment, and runs `make app` followed by a chat completion through the chat UI
- **THEN** the Opik UI SHALL show a trace for that turn containing the agent run, the LLM call, and a span per MCP tool invocation

#### Scenario: App start-up tolerates Opik being absent
- **WHEN** a contributor runs `make infra-up` followed by `make app` without ever running `make opik-up` and with `OPIK_TRACING_ENABLED` unset (or `false`)
- **THEN** the deep-research app SHALL start successfully, chat completions SHALL succeed end-to-end, and no Opik network calls SHALL be attempted

#### Scenario: Opik unreachable while tracing enabled
- **WHEN** the deep-research app is started with `OPIK_TRACING_ENABLED=true` but the Opik stack has not been started (`make opik-up` was not run, or it was torn down via `make opik-down`)
- **THEN** the app SHALL still start and accept chat completion requests, and request handling SHALL still produce successful DIAL responses (consistent with the deep-research app's tracing-failure-does-not-break-the-turn requirement); only the trace will be missing from Opik
