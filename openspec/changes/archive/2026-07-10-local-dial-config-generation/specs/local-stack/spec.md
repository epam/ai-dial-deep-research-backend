# local-stack (delta)

## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: Environment configuration via .env

The stack SHALL read environment configuration from a `.env` file at the repo root, and the repository SHALL ship an `.env.example` documenting the supported variables. At minimum the `.env` file SHALL expose the DIAL API key used by the chat UI to call DIAL core. `.env.example` SHALL additionally document the optional `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` variables consumed only by the config generator (`make infra-config`); the app itself SHALL NOT require them.

#### Scenario: Default bring-up

- **WHEN** a contributor copies `.env.example` to `.env` without modifications, generates the core config, and runs `make infra-up` followed by `make app`
- **THEN** the stack SHALL start on the default ports (chat UI at 3000, DIAL core at 8080, themes at 3001, app at 5000 on the host)

#### Scenario: App runs without remote DIAL credentials

- **WHEN** the app starts with `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` unset
- **THEN** the app SHALL start normally — the variables are consumed only by the generator script
