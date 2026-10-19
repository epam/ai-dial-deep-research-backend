## Context

`docker-compose.yml` runs the 0.x chat with `AUTH_DISABLED=true` on host port 3010.
`docker-compose.chat-nextgen.yml` adds a 1.x chat (`chat-next`, host port 4207), a second themes
service (`themes-next`), and the demo's Core entry. The overlay was opt-in because the 1.x chat
needs a real identity provider, whose credentials only some contributors have. See proposal.md for
why the stack moves to one chat.

## Goals / Non-Goals

**Goals:**
- One chat service, of the 1.x line, in the base compose file, configured as `chat-next` is today.
- Every pinned image on the version named in the proposal.

**Non-Goals:**
- A StatGPT backend service in the stack. It comes as a change of its own.
- Running the chat without an identity provider. Chat 1.x has no such mode.

## Decisions

### The 1.x chat replaces the base `chat` service, keeping the service names `chat` and `themes`

The overlay's `chat-next` and `themes-next` settings move into the base `chat` and `themes`
services. The overlay's service names are dropped, because with one chat a "next" name no longer
says anything.

- *Alternative: keep the overlay and make the base stack chat-less.* Rejected. `make infra-up`
  would then start no UI at all, and two compose files would stay for one chat.

### The chat keeps host port 4207

The identity provider's OIDC client accepts `http://localhost:4207` as a redirect URI, and a port
it does not know fails the login.

- *Alternative: move the chat back to 3010, the port the old chat used.* Rejected. The login would
  fail until someone registers a new redirect URI with the identity provider.

### The chat reads `.env` through `env_file`, and `environment` overrides the variables it validates differently

This carries over the overlay's setup unchanged. `env_file` brings in the four `AUTH_KEYCLOAK_*`
values without naming them in a committed file. `environment` wins over `env_file`, which keeps the
app's `LOG_LEVEL=INFO` away from the chat: the chat accepts only `debug`, `log`, `warn` or `error`
there, and exits at startup on anything else.

- *Alternative: list each `AUTH_KEYCLOAK_*` variable under `environment` with `${…}`
  interpolation.* Rejected. It ties the compose file to one provider's variable names, while
  `env_file` passes whichever provider the contributor configures.

### The demo's Core entry is always loaded

`annotations-demo-applications.json` is appended to the base `aidial.config.files` list. The app's
`ENABLE_ANNOTATIONS_DEMO` flag remains the one switch for serving it.

- *Alternative: a small overlay that only appends the demo entry.* Rejected. It keeps a second
  compose file and Make targets for one config line, and the demo is cheap to list.
- *Alternative: drop the demo's Core registration.* Rejected. Then nothing local routes to the
  demo, and its attachments are readable only with the per-request key that a call through Core
  carries.

## Risks / Trade-offs

- [`make infra-up` now needs identity-provider values to give a usable chat] → Core, redis, themes
  and the adapter still start without them, and `scripts/send_conversation.py` drives the app
  through Core with no chat. The README says so next to the setup steps.
- [A Core release between 0.47.1 and 0.49.2 changes a setting the stack relies on] → Smoke-test
  after the bump: Core starts with the split config list, the chat logs in, the Deep Research
  deployment answers a request sent through Core, and the demo deployment is listed.
- [Conversations stored by the 0.x chat are not visible in the 1.x chat] → Accepted. The two chats
  logged in as different identities and so wrote to different buckets; local conversations are
  disposable.

## Migration Plan

A contributor pulls, copies the identity-provider block of `.env.example` into `.env` if they have
not already, and runs `make infra-down` followed by `make infra-up`. Stopping a stack started with
the removed overlay needs `docker compose -f docker-compose.yml -f docker-compose.chat-nextgen.yml
down` from an older checkout, or `docker compose down --remove-orphans` from this one.
