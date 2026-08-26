## ADDED Requirements

### Requirement: An opt-in Compose overlay runs the next-generation DIAL Chat

The repository SHALL provide `docker-compose.spike.yml`, an opt-in overlay layered on
`docker-compose.yml`, that replaces the chat UI with the next-generation DIAL Chat
(`epam/ai-dial-chat:1.0.0-rc.6`, the `1.0.0-rc.x` release line) and bumps the themes service to
`epam/ai-dial-chat-themes:0.19.1`. The overlay exists so inline citation annotations, which only
the next-generation chat renders, can be exercised locally.

The next-generation chat has no equivalent of the legacy `AUTH_DISABLED`, so at least one OIDC
provider SHALL be configured. The overlay SHALL take the Keycloak values
(`AUTH_KEYCLOAK_CLIENT_ID`, `AUTH_KEYCLOAK_SECRET`, `AUTH_KEYCLOAK_HOST`,
`AUTH_KEYCLOAK_DIAL_ROLES_FIELD`) from `.env` via `env_file`, never inlining them in a committed
file, and SHALL set `AUTH_COOKIE_SECURE=false`, which upstream sanctions for local HTTP.

The overlay SHALL NOT alter the default developer experience: plain `docker compose up` and
`make infra-up` SHALL continue to start the legacy stack unchanged.

DIAL Core SHALL NOT be changed for this overlay. Annotation attachment auto-sharing entered Core in
0.44.0, and the pinned `epam/ai-dial-core:0.45.1` already contains it.

#### Scenario: Spike stack cold start

- **WHEN** a contributor runs the spike overlay on a repository whose `.env` carries the four
  Keycloak values
- **THEN** the next-generation chat UI SHALL reach a running state and prompt for a Keycloak login,
  and the DIAL Core, themes, and redis services SHALL start as they do for the default stack

#### Scenario: The default stack is unaffected

- **WHEN** a contributor runs `make infra-up` without the overlay
- **THEN** the legacy chat image SHALL start as before, with no Keycloak requirement

#### Scenario: The app port does not collide with the chat backend

- **GIVEN** the next-generation chat's backend-for-frontend listens on port 5000, as does the Deep
  Research app by default
- **WHEN** the spike stack is started
- **THEN** the app SHALL be reachable on a port other than 5000, and DIAL Core's rendered
  application-schema endpoint SHALL point at that same port

### Requirement: A flag-gated spike deployment emits inline citation annotations

The app SHALL register an `annotations-spike` chat-completion deployment only when
`ENABLE_ANNOTATIONS_SPIKE` is true, defaulting to false, mirroring how the playground deployment is
gated on `enable_playground_channel`. The deployment is a local-only investigation aid: it SHALL
ignore the user's message and reply with a fixed report referencing two PDFs.

The deployment SHALL emit `custom_content.annotations` through
`Choice.send_chunk(ArbitraryChunk(...))`, because the DIAL SDK exposes no annotations API. Every
annotation SHALL carry a sequential integer `index`, which the SDK's non-streaming merge requires
and which DIAL Chat uses to merge streaming deltas, and SHALL carry
`body.source.attachment.url` pointing at a DIAL file, which is both what DIAL Chat filters on and
what DIAL Core auto-shares.

Citation offsets SHALL be derived from markers embedded in the report source rather than hardcoded
separately, so that editing the report wording cannot silently desynchronise the offsets from the
text.

#### Scenario: The deployment is absent by default

- **WHEN** the app starts without `ENABLE_ANNOTATIONS_SPIKE` set
- **THEN** no `annotations-spike` deployment SHALL be registered, and every existing deployment
  SHALL behave exactly as before

#### Scenario: The deployment returns a well-formed annotation payload

- **WHEN** the spike deployment is called through DIAL Core with the flag enabled
- **THEN** the response SHALL carry a `custom_content.annotations` array whose entries each have a
  sequential integer `index`, a `body.source.attachment.url` naming a DIAL file, and a
  `target.selector` of type `text_character_range` whose `end` offset falls inside the returned
  report text

#### Scenario: Cited files are readable by the caller

- **WHEN** the spike response's cited attachment URLs are fetched with the calling key
- **THEN** each SHALL be readable, demonstrating that DIAL Core auto-shared the annotation's source
  attachment

#### Scenario: The non-streaming path preserves the annotations

- **WHEN** the spike deployment is called with `stream: false`
- **THEN** the assembled response SHALL carry the same annotations, demonstrating that the
  sequential `index` satisfies the SDK's indexed-list merge
