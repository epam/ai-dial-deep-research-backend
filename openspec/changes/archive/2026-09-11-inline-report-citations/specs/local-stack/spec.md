## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Pinned infrastructure images
The compose file SHALL pin concrete image tags (not `latest`) for the upstream DIAL core, chat UI, themes, redis, and DIAL adapter services: `epam/ai-dial-core:0.45.1`, `epam/ai-dial-chat:0.47.2`, `epam/ai-dial-chat-themes:0.17.0`, `redis:7.2.4-alpine3.19`, `epam/ai-dial-adapter-dial:0.16.0`.

The opt-in overlay that adds the next-generation chat (see the two-generations requirement) SHALL pin its themes service the same way, to the `epam/ai-dial-chat-themes` tag that chat line expects, and SHALL run its chat service on the moving `development` tag of `epam/ai-dial-chat`. That tag SHALL be the only image in the repository not pinned to a version, and the reason SHALL be recorded where it is set: no released chat renders marker-tag annotations, because that rendering reached the chat's development branch after its newest release was built. The overlay SHALL move to a `1.0.x` tag once one carries the rendering. The reproducibility this requirement otherwise guarantees therefore covers the base stack, which the scenario below exercises, and deliberately not the overlay's chat.

#### Scenario: Reproducible stack
- **WHEN** two contributors run `make infra-up` on different machines at different times without pulling new tags
- **THEN** they SHALL run the same upstream DIAL image versions
