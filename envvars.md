# Environment variables

All env vars are loaded from `.env` at the repo root (see `.env.example` for the contributor template). The app fails fast at startup if any **required** var is missing.

## Required

| Env var | Used for |
| ------- | -------- |
| `CHANNEL_CONFIG_PATH` | Path to the channel config YAML. See `data/configs/example.yaml` and the schema in `src/dial_deep_research/channel_config.py`. |
| `MCP_SERVER_NAME` | Logical name for the generic-RAG MCP server connection. |
| `MCP_URL` | URL of the generic-RAG MCP server. |
| `MCP_API_KEY` | Service key for the MCP server. |

## Optional

| Env var | Used for |
| ------- | -------- |
| `APP_HOST` | Host interface the app binds to. |
| `APP_PORT` | Port the app binds to. |
| `LOG_LEVEL` | Python logging level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `DIAL_URL` | Where the app finds DIAL Core. |
| `DIAL_API_KEY` | Service key the app uses to call DIAL Core |
| `DIAL_APP_NAME` | OTel service name for traces. |
| `HEARTBEAT_INTERVAL` | Seconds between DIAL keep-alive heartbeats during long-running responses. |
| `LLM_MODELS_<ENUM_NAME>` | Override the DIAL Core deployment id for a given `LLMModelsEnum` member. E.g. `LLM_MODELS_GPT_5_2_2025_12_11=gpt-5.2-custom-name`. |
| `OPIK_TRACING_ENABLED` | Enable or disable Opik LLM tracing. |

NOTE: `DOCKER_DEFAULT_PLATFORM` in `.env.example` is consumed by Docker Compose (not the app): uncomment it on Apple Silicon because the DIAL images ship linux/amd64 only.
