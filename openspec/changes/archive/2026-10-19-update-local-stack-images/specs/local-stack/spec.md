## MODIFIED Requirements

### Requirement: Docker Compose stack brings up the DIAL infrastructure
The repository SHALL provide a `docker-compose.yml` defining the four DIAL infrastructure services — DIAL core, DIAL chat UI, a themes server, and a redis for DIAL core — started and stopped by `make infra-up` / `make infra-down`. The app itself SHALL run on the host via `make app` (not in a container); DIAL core reaches the host-running app at `http://host.docker.internal:5000`. The `core` service SHALL mount `dial_conf/core/` as a directory and load its config as a file list via `aidial.config.files`: the generated `generated/models.json`, the rendered `generated/application-schemas.json`, the local `applications.json`, and the committed `annotations-demo-applications.json` — the legacy single hand-written `dial_conf/core/config.json` SHALL NOT be read. This trade favours iteration speed and trivial IDE debugging over prod-parity; a future change can add an app Dockerfile + compose overlay when deployment becomes real.

#### Scenario: Infrastructure cold start
- **WHEN** a contributor runs `make infra-config` (with remote DIAL credentials and the identity-provider values in `.env`) followed by `make infra-up` on a freshly cloned repo with Docker running
- **THEN** the four infrastructure services (core, chat, themes, redis) SHALL reach a running state and the chat UI SHALL be reachable at `http://localhost:4207`

#### Scenario: App start on the host
- **WHEN** a contributor runs `make app` after `make infra-up`
- **THEN** the app SHALL start on the host via `uv run python -m dial_deep_research`, bound to port 5000, reachable by DIAL core via `host.docker.internal:5000`

#### Scenario: Offline operation
- **WHEN** the stack is started with previously generated config files and without any cloud LLM provider keys configured (DIAL Core itself runs locally, `MCP_API_KEY` is configured for the local generic-RAG MCP, and `DIAL_API_KEY` resolves to a local DIAL Core service key)
- **THEN** it SHALL still start successfully and the `deep-research` deployment SHALL be reachable through the chat UI; if the configured MCP server itself is unreachable, agent requests SHALL surface the friendly error string but the stack SHALL still come up

### Requirement: DIAL adapter routes LLM calls to the upstream provider
The compose stack SHALL run an `ai-dial-adapter-dial` service (image `epam/ai-dial-adapter-dial:0.20.0`) that exposes the OpenAI-compatible chat-completion endpoint at `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions` on the docker network and forwards each call to the configured upstream LLM provider declared in `dial_conf/core/config.json`'s `models.<model>.upstreams` block. The adapter SHALL connect back to DIAL core via `DIAL_URL=http://core:8080` so it can resolve per-request configuration.

#### Scenario: Model endpoint resolves on the docker network
- **WHEN** DIAL core proxies a chat-completion request whose target model declares an `endpoint` of `http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions`
- **THEN** the request SHALL reach the `ai-dial-adapter-dial` service via docker DNS, the adapter SHALL forward it to the configured upstream, and the response SHALL stream back through the same path

#### Scenario: Adapter not exposed on host
- **WHEN** the stack is up
- **THEN** the adapter SHALL be reachable only on the docker network (no host port mapping); host code (the dial-deep-research app) MUST go through DIAL core at `http://localhost:8081` rather than the adapter directly

### Requirement: Pinned infrastructure images
The compose file SHALL pin concrete image tags (not `latest`) for the upstream DIAL core, chat UI, themes, redis, and DIAL adapter services: `epam/ai-dial-core:0.49.2`, `epam/ai-dial-chat:1.2.4`, `epam/ai-dial-chat-themes:0.21.0`, `redis:7.2.4-alpine3.19`, `epam/ai-dial-adapter-dial:0.20.0`. The themes tag SHALL be one built for the pinned chat's line, because a themes configuration built for another chat line loads without an error and applies almost nothing.

#### Scenario: Reproducible stack
- **WHEN** two contributors run `make infra-up` on different machines at different times without pulling new tags
- **THEN** they SHALL run the same upstream DIAL image versions

### Requirement: Environment configuration via .env
The stack SHALL read environment configuration from a `.env` file at the repo root, and the repository SHALL ship an `.env.example` documenting the supported variables. At minimum the `.env` file SHALL expose the DIAL API key used by the chat UI to call DIAL core. `.env.example` SHALL additionally document the optional `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` variables consumed only by the config generator (`make infra-config`); the app itself SHALL NOT require them.

The chat UI has no mode without authentication, so it logs users in through an identity provider. Its identity-provider credentials SHALL come from `.env` and SHALL NOT appear in any committed file, and `.env.example` SHALL document the variables they need. The chat SHALL be served on a host port that the identity provider's OIDC client accepts as a redirect URI, because a port the client does not know fails the login with an invalid-redirect error; that port is **4207**. The app SHALL NOT need the identity-provider values: they are read only by the chat service.

#### Scenario: Default bring-up
- **WHEN** a contributor copies `.env.example` to `.env`, fills in the identity-provider values, generates the core config, and runs `make infra-up` followed by `make app`
- **THEN** the stack SHALL start on the default ports (chat UI at 4207, DIAL core at 8081, themes at 3011, app at 5000 on the host), and the contributor SHALL be able to log into the chat UI

#### Scenario: Identity-provider values missing
- **WHEN** a contributor runs `make infra-up` with no identity-provider values in `.env`
- **THEN** DIAL core, redis, themes and the DIAL adapter SHALL still start, so the app can be driven through DIAL core without the chat UI, for example with `scripts/send_conversation.py`; only the chat UI SHALL be unusable

#### Scenario: App runs without remote DIAL credentials
- **WHEN** the app starts with `REMOTE_DIAL_URL` and `REMOTE_DIAL_API_KEY` unset
- **THEN** the app SHALL start normally — the variables are consumed only by the generator script

## REMOVED Requirements

### Requirement: Both chat generations run side by side, opt-in
**Reason**: The stack runs one chat, the 1.x line, which is the only line still supported and the one that renders inline citation pills. There is nothing left to compare it with.
**Migration**: Use the single chat at `http://localhost:4207`. The `chat-ng-up`, `chat-ng-down` and `chat-ng-logs` targets are gone; use `make infra-up`, `make infra-down` and `make infra-logs`. The identity-provider values the overlay read from `.env` are now read by the base `chat` service.

### Requirement: The annotations demo deployment is registered opt-in
**Reason**: The overlay that registered the demo in DIAL core is removed with the second chat. The demo's Core entry is now part of the base Core configuration, as the next requirement states.
**Migration**: Nothing to do in Core. Set `ENABLE_ANNOTATIONS_DEMO=true` when running the app to serve the demo, as before.

## ADDED Requirements

### Requirement: The annotations demo deployment is registered in the base stack

The demo completion (see the **report-citations** capability) SHALL be reachable from the local stack
through DIAL core. Its application entry SHALL live in a committed configuration file of its own,
which the base `core` service always loads through `aidial.config.files`.

The app SHALL serve the demo only when its own environment flag is set, as the playground channel's
registration is gated. A default stack therefore lists the demo application, and the demo answers
only while the app runs with that flag.

The demo SHALL ship no PDFs of its own, so the repository carries no sample binaries and no
environment needs files placed on it. It SHALL cite what the caller attached, and SHALL state
plainly what to attach when the attachments cannot carry the report.

Reaching the demo through core is what the registration is for: the attachments are read with the
per-request key, which only a call routed through core carries. Inspecting the payload without core
is the unit tests' job, over the shared citation code, not a direct call's.

#### Scenario: The base stack registers the demo

- **WHEN** a contributor generates the core config and runs `make infra-up`
- **THEN** core SHALL load the demo's application entry, and the chat UI SHALL list it

#### Scenario: The app serves the demo only behind its flag

- **WHEN** a contributor runs the app with the demo's flag set and calls the demo from the chat UI
- **THEN** the demo deployment SHALL answer, and its reply SHALL carry the citation marker tags and
  annotations; without the flag the app SHALL NOT serve that deployment

#### Scenario: Attachments that cannot carry the report are reported, not ignored

- **WHEN** the demo is called with fewer PDF attachments than the report cites, or with one whose
  page count is below the deepest page the report cites
- **THEN** the turn SHALL fail with a message saying how many PDFs to attach and how deep they must
  be, naming the attachment at fault, rather than answering with an incomplete demonstration
