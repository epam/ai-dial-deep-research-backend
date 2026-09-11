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

- The template SHALL contain one generic example instance per registered application type —
  the research type and the playground type — with no real client names or other sensitive
  content, each referencing its type by `applicationTypeSchemaId`, plus a
  `roles.default.limits` fragment granting the `default` role access to each instance.
- The template is an **example of the config file's shape**, not a property reference. Each
  instance's `applicationProperties` SHALL set only the properties the properties model
  requires, and SHALL NOT restate a property that has a default. The full reference for what
  a property means and what it defaults to is the model and its generated schema (see
  **application-config-schema**).
- A change to the model's **required** properties — a required property added, removed or
  renamed, or an existing property becoming required or optional — SHALL update the template's
  instances in the same change, and the test suite SHALL fail while the template does not set
  exactly the required set.
- `make infra-config` SHALL copy the template to `dial_conf/core/applications.json` when the
  local file does not exist, and SHALL NOT overwrite an existing local file.
- The README SHALL document that real client instances are added to the local
  `applications.json` (each with its `roles.default.limits` entry) and never committed.

#### Scenario: First-time seeding

- **WHEN** a contributor runs `make infra-config` on a fresh clone
- **THEN** `dial_conf/core/applications.json` SHALL be created as a copy of the committed
  template

#### Scenario: Template sets the required properties only

- **WHEN** the committed template's instances are checked against the properties model
- **THEN** each instance's `applicationProperties` SHALL set exactly the properties the model
  requires, and SHALL set no property that the model gives a default

#### Scenario: A newly required property is added to the template

- **WHEN** a property is added to the properties model as required, or an existing property
  becomes required
- **THEN** the committed template's instances SHALL be updated in the same change to set it,
  and the test suite SHALL fail until they do

#### Scenario: A property that becomes optional leaves the template

- **WHEN** a required property gains a default and so becomes optional
- **THEN** the committed template's instances SHALL drop it in the same change, and the test
  suite SHALL fail until they do

#### Scenario: A changed default reaches an already-seeded channel

- **WHEN** a property's default changes in the properties model and a contributor's
  `applications.json` was seeded from the template before that change
- **THEN** the seeded channel SHALL follow the new default, because the template stated no
  value for that property to pin

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

The opt-in overlay that adds the next-generation chat (see the two-generations requirement) SHALL pin its themes service the same way, to the `epam/ai-dial-chat-themes` tag that chat line expects, and SHALL run its chat service on the moving `development` tag of `epam/ai-dial-chat`. That tag SHALL be the only image in the repository not pinned to a version, and the reason SHALL be recorded where it is set: no released chat renders marker-tag annotations, because that rendering reached the chat's development branch after its newest release was built. The overlay SHALL move to a `1.0.x` tag once one carries the rendering. The reproducibility this requirement otherwise guarantees therefore covers the base stack, which the scenario below exercises, and deliberately not the overlay's chat.

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

### Requirement: Both chat generations run side by side, opt-in

The repository SHALL provide an opt-in Compose overlay that **adds** a next-generation chat UI and a
themes service of its own to the stack, leaving the base `chat` and `themes` services running. Plain
`make infra-up` SHALL be unaffected: it starts the base stack alone, with no next-generation service
and no additional configuration required of a contributor who does not want one.

Adding rather than replacing is the point. The two generations render an assistant message
differently — only the newer one draws inline citation pills — so a report has to be openable in both
to see what each does with it, which a swap-style overlay cannot show without a restart.

The overlay SHALL satisfy the following:

- **Both chats reachable at once**, on distinct host ports. The next-generation chat SHALL be served
  on a host port that its OIDC client accepts as a redirect URI; a port the client does not know
  fails the login with an invalid-redirect error, so this is a constraint rather than a preference.
  With the base chat holding 3000 and the app's default holding 5000, the port that satisfies it is
  **4207** (see the overlay decision in the design for the registered set). If the app is moved off
  its default port, the overlay's note about that clash SHALL be revisited in the same edit rather
  than left describing the old layout.
- **Its own themes service, with its own pinned image.** A themes configuration built for one
  generation loads without error in the other and applies almost nothing, so the two cannot share
  one service.
- **OIDC credentials from `.env` only.** The next-generation chat has no equivalent of the base
  chat's `AUTH_DISABLED`, so it requires a real identity provider. Its credentials SHALL come from
  `.env` and SHALL NOT appear in any committed file, and `.env.example` SHALL document the variables
  it needs. Because a contributor without those values cannot start it, it SHALL remain opt-in —
  this is why the services are not in the base compose file.
- **Its own Makefile targets**, alongside the existing infra ones, to bring the combined stack up,
  take it down, and tail its logs.

The two chats authenticate as different identities — the base one under the development key, the
next-generation one as a real user — so they resolve to different DIAL storage buckets and share no
conversations. That is a property to rely on rather than work around: neither generation can read or
overwrite the other's conversation records, and comparing how the two render one reply needs no
shared conversation, because the demo completion's reply is the same every time.

#### Scenario: The base stack is unchanged

- **WHEN** a contributor runs `make infra-up` with no next-generation values in `.env`
- **THEN** the base services SHALL start as before, no next-generation chat or themes service SHALL
  be created, and nothing SHALL fail for the missing configuration

#### Scenario: Both generations up together

- **WHEN** a contributor runs the overlay's up target with the required `.env` values present
- **THEN** the base chat and the next-generation chat SHALL both be reachable, each on its own host
  port, against the same DIAL core

#### Scenario: A report is compared across generations

- **WHEN** the same reply carrying citation marker tags is requested from each chat
- **THEN** the next-generation chat SHALL render inline citation pills for it, and the base chat
  SHALL show what a client that does not understand those tags shows — which is the point of running
  both, and the only way to observe it

### Requirement: The annotations demo deployment is registered opt-in

The demo completion (see the **report-citations** capability) SHALL be reachable from the local stack
without being present in a default one. Two switches, both off by default and both flipped by
choosing the annotations workflow:

- **In the app**, its registration SHALL be gated by its own environment flag, as the playground
  channel's is.
- **In DIAL core**, its application entry SHALL live in a committed configuration file of its own,
  appended to core's `aidial.config.files` list by the same overlay that adds the next-generation
  chat — never by the base stack. A default stack therefore SHALL NOT show an application whose
  deployment nothing is serving.

The demo SHALL ship no PDFs of its own, so the repository carries no sample binaries and no
environment needs files placed on it. It SHALL cite what the caller attached, and SHALL state
plainly what to attach when the attachments cannot carry the report.

Reaching the demo through core is what the registration is for: the attachments are read with the
per-request key, which only a call routed through core carries. Inspecting the payload without core
is the unit tests' job, over the shared citation code, not a direct call's.

#### Scenario: A default stack shows no demo application

- **WHEN** a contributor generates the core config and runs `make infra-up` without the annotations
  overlay
- **THEN** core SHALL NOT load the demo's application entry, and the chat UI SHALL NOT list it

#### Scenario: The overlay registers it and the app serves it

- **WHEN** a contributor brings up the overlay and runs the app with the demo's flag set
- **THEN** the demo deployment SHALL be callable from the next-generation chat, and its reply SHALL
  carry the citation marker tags and annotations

#### Scenario: Attachments that cannot carry the report are reported, not ignored

- **WHEN** the demo is called with fewer PDF attachments than the report cites, or with one whose
  page count is below the deepest page the report cites
- **THEN** the turn SHALL fail with a message saying how many PDFs to attach and how deep they must
  be, naming the attachment at fault, rather than answering with an incomplete demonstration
