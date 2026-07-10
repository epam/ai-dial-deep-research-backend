<h1 align="center">
    DIAL Deep Research
</h1>
<p align="center">
    <a href="https://dialx.ai/">
        <img src="https://dialx.ai/logo/dialx_logo.svg" alt="About DIALX">
    </a>
</p>
<h4 align="center">
    <a href="https://discord.gg/ukzj9U9tEe">
        <img src="https://img.shields.io/static/v1?label=DIALX%20Community%20on&message=Discord&color=blue&logo=Discord&style=flat-square" alt="Discord">
    </a>
</h4>

A DIAL-native **deep research** application: a LangChain/LangGraph agent that connects to a
generic-RAG MCP server, clarifies the user's query, aligns on a research plan, runs a
research loop grounded in the MCP tools, and streams progress to DIAL as timed stages.

- [Prerequisites](#prerequisites)
- [Local run](#local-run)
- [Configuration](#configuration)
- [DIAL core configuration](#dial-core-configuration)
- [Running the app in Docker (opt-in)](#running-the-app-in-docker-opt-in)
- [Driving the app from the CLI](#driving-the-app-from-the-cli)
- [LLM tracing with Opik (optional)](#llm-tracing-with-opik-optional)
- [Environment variables](#environment-variables)
  - [Required](#required)
  - [Optional](#optional)

## Prerequisites

- Docker Desktop 4.x (Compose V2)
- Python 3.13
- `uv` (Python package manager)
- A reachable generic-RAG MCP server (URL + api-key).
- A `dial_conf/core/config.json` (see [DIAL core configuration](#dial-core-configuration)).
- DIAL Core >= 0.41.0 — the app registers as a schema-rich application type and Core fetches
  its schema from the app's schema endpoint. The compose stack already pins a compatible Core.

## Local run

Infra runs in Docker; the **app runs on your host** via uvicorn. DIAL core reaches the app through `host.docker.internal:5000`.

```sh
cp .env.example .env
# fill .env with secrets
make install
make infra-up
make app
```

Then open DIAL Chat UI in the browser, select the **Deep Research** application, and send your query.

Tear down:

```sh
make infra-down       # stop infra
make infra-cleanup    # down + remove volumes (destroys DIAL core data)
```

> **Host-first trade-off.** Host-run is the default dev loop (fast restarts, IDE debugging). `host.docker.internal` is provided automatically by Docker Desktop on macOS and Windows; on Linux you'd need to add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `core` service in `docker-compose.yml`. An opt-in containerized run is available too — see [Running the app in Docker](#running-the-app-in-docker-opt-in).

## Configuration

Configuration comes from two sources:

- **Env vars** (loaded from `.env` at the repo root; template in `.env.example`) carry
  deployment concerns: endpoints, keys, ports, knobs.
  See [Environment variables](#environment-variables) for
  the full spec. Startup fails fast if required vars are missing.
- **Application properties** carry everything specific to one application instance
  ("channel") of the app: the client wording injected into prompts, the knowledge-base
  topics map, the research iteration cap. They live in DIAL Core on each application
  instance and are fetched and validated per request against the JSON schema generated
  from `src/dial_deep_research/app_properties.py` (committed at
  [`docs/generated-app-schema.json`](./docs/generated-app-schema.json)). An example ships
  at
  [`data/configs/example-application-properties.json`](./data/configs/example-application-properties.json).
  A request without valid properties gets a friendly "not configured" reply.

## DIAL core configuration

`dial_conf/core/config.json` is **not committed**.
Create your own before `make infra-up` — docker-compose mounts it into the `core`
service.

The app is a **schema-rich application type**: DIAL Core must know the type, and every
channel is an application **instance** of it. (Core-side custom apps are already enabled in
this repo's `dial_conf/settings/settings.json` via `"applications": {"includeCustomApps": true}`.)

Register the type with an `applicationTypeSchemas` entry — Core fetches the property schema
live from the app's schema endpoint:

```json
"applicationTypeSchemas": [
  {
    "$id": "https://mydial.epam.com/custom_application_schemas/deep-research",
    "$schema": "https://dial.epam.com/application_type_schemas/schema#",
    "dial:applicationTypeDisplayName": "Deep Research",
    "dial:applicationTypeCompletionEndpoint": "http://host.docker.internal:5000/openai/deployments/deep-research/chat/completions",
    "dial:applicationTypeSchemaEndpoint": "http://host.docker.internal:5000/v1/configuration-support/application-schema",
    "dial:appendApplicationPropertiesHeader": false
  }
]
```

Then add one application instance per channel, referencing the type by its `$id` and
carrying that channel's `applicationProperties` (shape:
[`data/configs/example-application-properties.json`](./data/configs/example-application-properties.json)):

```json
"applications": {
  "deep-research-acme": {
    "displayName": "ACME Deep Research",
    "applicationTypeSchemaId": "https://mydial.epam.com/custom_application_schemas/deep-research",
    "applicationProperties": {
      "max_research_iterations": 10,
      "prompts": {
        "client_name": "ACME",
        "agent_name": "ACME Deep Research",
        "data_sources_descriptions": "## financial report\n\n..."
      }
    }
  }
}
```

## Running the app in Docker (opt-in)

`docker-compose.app.yml` is a compose overlay that runs the app as a container next to the
infra, e.g. to test the image itself or container networking:

```sh
make app-build        # build the app image
make all-up           # start infra + the app container
make app-logs         # tail app logs
make all-down         # stop infra + the app container
```

Notes:

- For DIAL core to route to the containerized app, the app endpoint in
  `dial_conf/core/config.json` must be `http://deep-research:5000/...`
  (not `host.docker.internal`, which is for the host-run app).
- Inside the container `localhost` means the container itself. Any `.env` URL that points at
  a service on your host (e.g. `MCP_URL`, Opik) must use `host.docker.internal` instead.

## Driving the app from the CLI

`scripts/send_conversation.py` drives a multi-turn conversation against a running stack —
useful for testing without the chat UI:

```sh
# fresh conversation
uv run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite -d deep-research-acme
# follow-up turn, threading prior state
uv run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue -d deep-research-acme
```

`-d`/`--deployment` targets an application instance registered in DIAL Core (falls back to
the `DEPLOYMENT_ID` env var). Calling the bare `deep-research` type deployment returns the
"not configured" reply — instances carry the configuration.

## LLM tracing with Opik (optional)

The agent's per-turn LangChain run can be traced into [Opik](https://github.com/comet-ml/opik) — every turn becomes one hierarchical trace covering the agent graph, the LLM calls, and every MCP tool call. **Off by default**; opt in per-developer.

Only local Opik is supported for now. Non-local Opik is not yet supported.

Enable with the following envvar

```sh
OPIK_TRACING_ENABLED=true
```

Start a local Opik stack:

```sh
make opik-up          # first run clones github.com/comet-ml/opik into .opik-local/ (gitignored), then `docker compose up`
```

The Opik stack runs as a separate Compose project (`name: opik` upstream),
so `make infra-up` / `make infra-down` for our infra never touches it — and vice versa.

Tear down:

```sh
make opik-down        # stops Opik containers; .opik-local/ stays for the next `opik-up`
```

## Environment variables

All env vars are loaded from `.env` at the repo root (see `.env.example` for the contributor template). The app fails fast at startup if any **required** var is missing.

### Required

| Env var | Used for |
| ------- | -------- |
| `MCP_SERVER_NAME` | Logical name for the generic-RAG MCP server connection. |
| `MCP_URL` | URL of the generic-RAG MCP server. |
| `MCP_API_KEY` | Service key for the MCP server. |

### Optional

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
| `OPIK_PROJECT_NAME` | Opik project traces are grouped under (default: `deep-research`). |

NOTE: `DOCKER_DEFAULT_PLATFORM` in `.env.example` is consumed by Docker Compose (not the app): uncomment it on Apple Silicon because the DIAL images ship linux/amd64 only.
