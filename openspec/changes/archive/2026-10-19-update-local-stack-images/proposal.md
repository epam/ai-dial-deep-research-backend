## Why

The local compose stack pins DIAL images that are several releases old, and it runs two chat UIs: the
0.x chat by default and the 1.x chat through an opt-in overlay. Only the 1.x line is supported now,
and coming work on resuming an interrupted research has to be checked against current DIAL Core and
Chat behaviour, such as how Chat stores a failed answer and how large a state it accepts. The stack
should run the current versions and a single chat.

## What Changes

- Bump the pinned images: `epam/ai-dial-core` 0.47.1 → 0.49.2, `epam/ai-dial-chat` 0.47.2 → 1.2.4,
  `epam/ai-dial-chat-themes` 0.17.0 → 0.21.0, `epam/ai-dial-adapter-dial` 0.16.0 → 0.20.0.
  `redis` stays at `7.2.4-alpine3.19`.
- **BREAKING** Remove the 0.x chat. The `chat` service of `docker-compose.yml` becomes the 1.x chat,
  configured as the overlay's `chat-next` service is today: host port 4207, identity-provider
  credentials from `.env`, and the 1.x environment variables. Chat 1.x has no `AUTH_DISABLED`, so
  `make infra-up` now needs the identity-provider values in `.env` before the chat can start.
- Remove the second themes service. The single `themes` service runs the themes image built for
  the 1.x chat.
- Delete `docker-compose.chat-nextgen.yml` and the `chat-ng-up`, `chat-ng-down` and `chat-ng-logs`
  Make targets.
- DIAL Core always loads `annotations-demo-applications.json`. The app still serves the demo only
  when `ENABLE_ANNOTATIONS_DEMO` is set, so the default stack lists the demo application, and it
  answers only while the app runs with that flag.
- Update the README and `.env.example` to match.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-stack`: the pinned image versions change; the default bring-up opens the chat on port
  4207 and needs identity-provider values in `.env`; the requirement that both chat generations
  run side by side is removed; and the annotations demo's Core entry is part of the base Core
  configuration instead of an opt-in.

## Impact

- `docker-compose.yml`: the image tags, and the `chat` and `themes` services rewritten for the 1.x
  chat; the demo's file is appended to Core's `aidial.config.files`.
- `docker-compose.chat-nextgen.yml`: deleted.
- `Makefile`: the next-generation chat section and its three targets are deleted; the `infra-up`
  help text is unchanged.
- `README.md`: the setup section (chat URL), the DIAL core configuration table row for the demo
  file, and the "Inline citations demo" section.
- `.env.example`: the identity-provider block is described as required for the chat UI.
- `openspec/specs/local-stack/spec.md`: updated through this change's delta.
- No application code changes. `docker-compose.app.yml` is unaffected, because it adds only the
  app's own container.
