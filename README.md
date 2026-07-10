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
- **Channel config** (a YAML file selected by `CHANNEL_CONFIG_PATH`) carries everything
  specific to one deployment ("channel") of the app: the deployment id, the client wording
  injected into prompts, the knowledge-base topics map. Schema:
  `src/dial_deep_research/channel_config.py`. A ready-to-run example ships at
  [`data/configs/example.yaml`](./data/configs/example.yaml) — `.env.example` points at it.

## DIAL core configuration

`dial_conf/core/config.json` is **not committed**.
Create your own before `make infra-up` — docker-compose mounts it into the `core`
service.

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
uv run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite
# follow-up turn, threading prior state
uv run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue
```

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
| `CHANNEL_CONFIG_PATH` | Path to the channel config YAML. See `data/configs/example.yaml` and the schema in `src/dial_deep_research/channel_config.py`. |
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

NOTE: `DOCKER_DEFAULT_PLATFORM` in `.env.example` is consumed by Docker Compose (not the app): uncomment it on Apple Silicon because the DIAL images ship linux/amd64 only.
