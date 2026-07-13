## ADDED Requirements

### Requirement: Local Opik tracing stack runs independently of the infra stack

The repository SHALL provide a separate Compose lifecycle for a local self-hosted **Opik** instance (LLM trace ingestion + UI), plus two new Makefile targets:

- `opik-up` SHALL start the Opik services.
- `opik-down` SHALL stop the Opik services.

The implementation MAY ship its own self-contained `docker-compose.opik.yml`, OR delegate to Opik's upstream compose file by checking the upstream Opik repository out into a gitignored local path (e.g. `.opik-local/`) on first `make opik-up`. Either approach is acceptable provided the lifecycle-independence guarantees below hold. The Opik Compose project SHALL run under a different Compose project name from the infra stack (so `docker compose down` from the repo root never affects Opik containers) and a pinned Opik release version SHALL be used (no floating `latest` tag), consistent with the existing `Pinned infrastructure images` requirement.

The existing `docker-compose.yml`, `make up`, and `make down` SHALL NOT be modified to include Opik services — they continue to operate solely on the DIAL infrastructure (core, chat, themes, redis, ai-dial-adapter-dial). Conversely, `make opik-up` / `make opik-down` SHALL NOT touch the infra services. The two stacks have fully independent lifecycles: either side can be started, stopped, or restarted without disturbing the other.

When running, the local Opik instance SHALL expose:

- a UI reachable from the host at a stable, documented port,
- an ingestion endpoint reachable from the host-running deep-research app at `http://localhost:<port>` so the existing host-on-`5000` / Compose-on-Docker pattern (already established for DIAL core) continues to apply.

The repository SHALL NOT ship a `.env.example` (or equivalent) that pre-enables Opik tracing: `OPIK_TRACING_ENABLED` defaults to `False` in `OpikSettings`, and contributors opt in by setting it (and the relevant connection vars) in their own local environment.

#### Scenario: `make up` does not start Opik
- **WHEN** a contributor runs `make up` on a freshly cloned repo
- **THEN** only the existing DIAL infrastructure services SHALL reach a running state; no Opik services SHALL be started, and `make up` cold-start time and disk footprint SHALL be unchanged from before this change

#### Scenario: `make down` does not stop Opik
- **WHEN** a contributor has previously run `make opik-up` (Opik services running) and then runs `make down`
- **THEN** the DIAL infrastructure services SHALL stop, the Opik services SHALL remain running, and the Opik UI SHALL still be reachable from the host

#### Scenario: `make opik-up` does not start infra
- **WHEN** a contributor runs `make opik-up` on a freshly cloned repo without having run `make up`
- **THEN** only the Opik services SHALL reach a running state; no DIAL infrastructure services SHALL be started

#### Scenario: `make opik-down` does not stop infra
- **WHEN** a contributor has previously run `make up` (infra services running) and then runs `make opik-down`
- **THEN** the Opik services SHALL stop and the DIAL infrastructure services SHALL remain running

#### Scenario: End-to-end trace flow with both stacks up
- **WHEN** a contributor runs `make up`, `make opik-up`, sets `OPIK_TRACING_ENABLED=true` in their local environment, and runs `make run` followed by a chat completion through the chat UI
- **THEN** the Opik UI SHALL show a trace for that turn containing the agent run, the LLM call, and a span per MCP tool invocation

#### Scenario: App start-up tolerates Opik being absent
- **WHEN** a contributor runs `make up` followed by `make run` without ever running `make opik-up` and with `OPIK_TRACING_ENABLED` unset (or `false`)
- **THEN** the deep-research app SHALL start successfully, chat completions SHALL succeed end-to-end, and no Opik network calls SHALL be attempted

#### Scenario: Opik unreachable while tracing enabled
- **WHEN** the deep-research app is started with `OPIK_TRACING_ENABLED=true` but the Opik stack has not been started (`make opik-up` was not run, or it was torn down via `make opik-down`)
- **THEN** the app SHALL still start and accept chat completion requests, and request handling SHALL still produce successful DIAL responses (consistent with the deep-research app's tracing-failure-does-not-break-the-turn requirement); only the trace will be missing from Opik
