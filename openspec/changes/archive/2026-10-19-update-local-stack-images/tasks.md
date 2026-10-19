## 1. Compose and Make

- [x] 1.1 In `docker-compose.yml`, bump `core` to `epam/ai-dial-core:0.49.2` and `ai-dial-adapter-dial` to `epam/ai-dial-adapter-dial:0.20.0`
- [x] 1.2 Replace the `chat` service with the 1.x chat configured as the overlay's `chat-next` (image `epam/ai-dial-chat:1.2.4`, host port 4207, `env_file: .env`, the `environment` block), depending on `themes` and `core`
- [x] 1.3 Set the `themes` service to `epam/ai-dial-chat-themes:0.21.0`
- [x] 1.4 Append `/opt/config/annotations-demo-applications.json` to Core's `aidial.config.files`
- [x] 1.5 Delete `docker-compose.chat-nextgen.yml` and the next-generation chat section of the `Makefile`

## 2. Documentation

- [x] 2.1 README: the chat URL in Setup, a note that the chat needs the identity-provider values, the demo row of the DIAL core configuration table, and the "Inline citations demo" section rewritten for one chat
- [x] 2.2 `.env.example`: describe the identity-provider block as needed by the chat UI

## 3. Verification

- [x] 3.1 `docker compose config` reports no warning, and no file in the repository still names the overlay, its targets or the old ports
- [x] 3.2 `make infra-up`: every service reaches a running state, Core loads the split config list including the demo entry, and the chat answers on `http://localhost:4207`
- [x] 3.3 A Deep Research request sent through Core with `scripts/send_conversation.py` gets an answer
