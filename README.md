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

- [Configuration](#configuration)
- [Environment variables](#environment-variables)
  - [Notes on the environment variables](#notes-on-the-environment-variables)
- [DIAL core configuration](#dial-core-configuration)
- [Local run](#local-run)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [Running the app in Docker (opt-in)](#running-the-app-in-docker-opt-in)
- [Driving the app from the CLI](#driving-the-app-from-the-cli)
- [LLM tracing with Opik (optional)](#llm-tracing-with-opik-optional)

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
  A request whose properties fail validation is delivered as a DIAL protocol error (a "not
  configured — contact your administrator" message), not a normal reply.

## Environment variables

All env vars are loaded from `.env` at the repo root (see `.env.example` for the contributor template). The app fails fast at startup if any **required** var is missing.

The app authenticates to DIAL Core (LLM calls, file operations, and the deployment-mode MCP) with the **per-request api-key** that DIAL Core forwards with each request — there is no static DIAL service key.

| Variable | Default | Required | Description | Available Values |
| -------- | ------- |:--------:| ----------- | ---------------- |
| **App server** | | | | |
| `APP_HOST` | `0.0.0.0` | No | Host interface the app binds to. | |
| `APP_PORT` | `5000` | No | Port the app binds to. | |
| `LOG_LEVEL` | `INFO` | No | Python logging level. | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| **DIAL Core** | | | | |
| `DIAL_URL` | | ⚠️ Yes | Where the app finds DIAL Core. No built-in default. | |
| `DIAL_APP_NAME` | `deep-research` | No | OTel service name for traces. | |
| `HEARTBEAT_INTERVAL` | `5` | No | Seconds between DIAL keep-alive heartbeats during long-running responses. | |
| **MCP server** | | | | |
| `MCP_SERVER_NAME` | | ⚠️ Yes | Logical name for the generic-RAG MCP server connection. | |
| `MCP_DEPLOYMENT_NAME` | | ⚠️ Yes, if `MCP_URL` unset | Deployment mode: DIAL application/deployment id of the generic-RAG MCP server, reached through DIAL Core at `{DIAL_URL}/v1/deployments/{name}/mcp`. Authenticated with the per-request api-key. | |
| `MCP_URL` | | ⚠️ Yes, if `MCP_DEPLOYMENT_NAME` unset | Local-dev mode: URL of a directly-reachable MCP server. Setting it selects local-dev mode. | |
| `MCP_API_KEY` | | ⚠️ Yes, if `MCP_DEPLOYMENT_NAME` unset | Local-dev mode: static key sent as the `api-key` header to `MCP_URL`. | |
| **LLM models** | | | | |
| `LLM_MODELS_<ENUM_NAME>` | | No | Override the DIAL Core deployment id for a given `LLMModelsEnum` member. E.g. `LLM_MODELS_GPT_5_2_2025_12_11=gpt-5.2-custom-name`. | |
| **Opik tracing** | | | | |
| `OPIK_TRACING_ENABLED` | `false` | No | Enable or disable Opik LLM tracing. | `true`, `false` |
| `OPIK_PROJECT_NAME` | `deep-research` | No | Opik project traces are grouped under. | |
| **Scripts & config generator** | | | | |
| `REMOTE_DIAL_URL` | | No | Remote DIAL that `make infra-config` pulls model configs from. Never read by the app. | |
| `REMOTE_DIAL_API_KEY` | | No | Api-Key for that remote DIAL. Never read by the app. | |

### Notes on the environment variables

- Exactly one **MCP connection mode** must be configured (the app fails fast at startup otherwise): (1) deployment mode via `MCP_DEPLOYMENT_NAME`, or (2) local-dev mode via `MCP_URL` + `MCP_API_KEY`.
- `DOCKER_DEFAULT_PLATFORM` in `.env.example` is consumed by Docker Compose (not the app): uncomment it on Apple Silicon because the DIAL images ship linux/amd64 only.

## DIAL core configuration

The `core` service reads its config as a **list of files** from `dial_conf/core/`
(merged by Core in the `aidial.config.files` order set in `docker-compose.yml`):

| File | Git | Content |
| ---- | --- | ------- |
| `generated/models.json` | ignored | model deployments pulled from a remote DIAL by `make infra-config`, plus the local `dial_api_key` and default-role limits from the committed `models-template.json`. Embeds the remote key — keep it local. |
| `generated/application-schemas.json` | ignored | the Deep Research application-type registration, rendered by `make infra-config` from the committed `application-schemas-template.json` with your `APP_PORT` baked into the endpoints. Core fetches the property schema live from the app's schema endpoint. |
| `applications.json` | ignored | your application instances ("channels"), seeded from the committed `applications-template.json`. |

Build all three local files with:

```sh
# needs REMOTE_DIAL_URL and REMOTE_DIAL_API_KEY in .env
make infra-config
```

- `generated/models.json` is (re)written on every run: each chat/embedding model of the
  remote DIAL becomes a local deployment routed through the `ai-dial-adapter-dial` container
  with the remote as upstream. Re-run the target to refresh models.
- `generated/application-schemas.json` is (re)rendered on every run from `APP_PORT`
  (default `5000`) — the same variable the app binds to, so one `.env` entry moves both
  ends. **macOS:** AirPlay Receiver occupies port 5000; set e.g. `APP_PORT=5001` in `.env`
  and re-run `make infra-config`.
- `applications.json` is seeded from the template only when missing — local edits survive
  re-runs.

The app is a **schema-rich application type**: the rendered registration
([template](./dial_conf/core/application-schemas-template.json)) declares the type, and
every channel is an application **instance** of it. (Core-side custom apps are already
enabled in this repo's `dial_conf/settings/settings.json` via
`"applications": {"includeCustomApps": true}`.)

Add one instance per channel to your local `dial_conf/core/applications.json`: reference the
type via `applicationTypeSchemaId`, carry that channel's `applicationProperties` (shape:
[`data/configs/example-application-properties.json`](./data/configs/example-application-properties.json)),
and grant the chat key's role access to the instance under `roles.default.limits`. The
committed [`applications-template.json`](./dial_conf/core/applications-template.json) shows
both parts for a fictional example instance:

```json
{
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
  },
  "roles": {
    "default": {
      "limits": {
        "deep-research-acme": {}
      }
    }
  }
}
```

Real client instances stay in the gitignored local file — never commit them.

## Local run

### Prerequisites

- Docker Desktop 4.x (Compose V2)
- Python 3.13
- `uv` (Python package manager)
- A generic-RAG MCP server — either registered as a DIAL application (deployment mode) or directly reachable via URL + api-key (local-dev mode).
- A remote DIAL instance to pull model configs from (`REMOTE_DIAL_URL` + `REMOTE_DIAL_API_KEY`
  in `.env`, consumed by `make infra-config` — see
  [DIAL core configuration](#dial-core-configuration)).
- DIAL Core >= 0.41.0 — the app registers as a schema-rich application type and Core fetches
  its schema from the app's schema endpoint. The compose stack already pins a compatible Core.

### Setup

Infra runs in Docker; the **app runs on your host** via uvicorn. DIAL core reaches the app through `host.docker.internal:5000`.

```sh
cp .env.example .env
# fill .env with secrets
make install
make infra-config     # build the local DIAL core config (see "DIAL core configuration")
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

> **macOS and port 5000.** AirPlay Receiver binds port 5000, so the app can't. Set e.g. `APP_PORT=5001` in `.env` **before** `make infra-config` — the target bakes the port into the DIAL core routing config (see [DIAL core configuration](#dial-core-configuration)).

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

- For DIAL core to route to the containerized app, the type endpoints in
  `dial_conf/core/generated/application-schemas.json` must point at
  `http://deep-research:5000/...` (not `host.docker.internal`, which is for the host-run
  app). Re-apply that edit after re-running `make infra-config`.
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
