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
make up
make app
```

Then open DIAL Chat UI in the browser, select the **Deep Research** application, and send your query.

Tear down:

```sh
make down             # stop infra
make cleanup          # down + remove volumes (destroys DIAL core data)
```

> **Host-first trade-off.** We don't ship a Dockerfile for the app yet. `host.docker.internal` is provided automatically by Docker Desktop on macOS and Windows; on Linux you'd need to add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `core` service in `docker-compose.yml`. We'll revisit when prod deployment becomes real.

## Configuration

Configuration comes from two sources:

- **Env vars** (loaded from `.env` at the repo root; template in `.env.example`) carry
  deployment concerns: endpoints, keys, ports, knobs. See [`envvars.md`](./envvars.md) for
  the full spec. Startup fails fast if required vars are missing.
- **Channel config** (a YAML file selected by `CHANNEL_CONFIG_PATH`) carries everything
  specific to one deployment ("channel") of the app: the deployment id, the client wording
  injected into prompts, the knowledge-base topics map. Schema:
  `src/dial_deep_research/channel_config.py`. A ready-to-run example ships at
  [`data/configs/example.yaml`](./data/configs/example.yaml) — `.env.example` points at it.

## DIAL core configuration

`dial_conf/core/config.json` is **not committed**.
Create your own before `make up` — docker-compose mounts it into the `core`
service.

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
so `make up` / `make down` for our infra never touches it — and vice versa.

Tear down:

```sh
make opik-down        # stops Opik containers; .opik-local/ stays for the next `opik-up`
```
