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

See [docs/architecture.md](docs/architecture.md) for diagrams of the runtime flow.

- [Configuration](#configuration)
- [Environment variables](#environment-variables)
  - [Notes on the environment variables](#notes-on-the-environment-variables)
- [DIAL core configuration](#dial-core-configuration)
  - [Playground (optional)](#playground-optional)
- [Local run](#local-run)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [Running the app in Docker (opt-in)](#running-the-app-in-docker-opt-in)
- [Inline citations demo](#inline-citations-demo)
- [Driving the app from the CLI](#driving-the-app-from-the-cli)
- [LLM tracing with Opik (optional)](#llm-tracing-with-opik-optional)
- [Spec-driven development](#spec-driven-development)
- [License](#license)

## Configuration

Configuration comes from two sources:

- **Env vars** (loaded from `.env` at the repo root; template in `.env.example`) carry
  deployment concerns: endpoints, keys, ports, knobs.
  See [Environment variables](#environment-variables) for
  the full spec. Startup fails fast if required vars are missing.
- **Application properties** carry everything specific to one application instance
  ("channel") of the app: the client wording injected into prompts, the knowledge-base
  topics map, the research iteration cap, and the MCP servers it connects to. They live in
  DIAL Core on each application instance and are fetched and validated per request against
  the JSON schema generated
  from `src/dial_deep_research/app_properties.py` (committed at
  [`docs/generated-app-schema.json`](./docs/generated-app-schema.json)) — that schema and the
  model behind it are the full reference for every property, its meaning and its default.
  [`dial_conf/core/applications-template.json`](./dial_conf/core/applications-template.json)
  is an example of the config file's shape and sets only the required properties, so it is not
  a property reference.
  A request whose properties fail validation is delivered as a DIAL protocol error (a "not
  configured — contact your administrator" message), not a normal reply.

## Environment variables

All env vars are loaded from `.env` at the repo root (see `.env.example` for the contributor template). The app fails fast at startup if any **required** var is missing.

The app authenticates to DIAL Core (LLM calls, file operations, and the deployment-mode MCP) with the **per-request api-key** that DIAL Core forwards with each request — there is no static DIAL service key.

| Variable | Default | Required | Description | Available Values |
| -------- | ------- |--------| ----------- | ---------------- |
| **App server** | | | | |
| `APP_HOST` | `0.0.0.0` | No | Host interface the app binds to. | |
| `APP_PORT` | `5000` | No | Port the app binds to. | |
| `LOG_LEVEL` | `INFO` | No | Level of the root logger and every managed logger except the app's own. | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DEEP_RESEARCH_LOG_LEVEL` | `INFO` | No | Level of the app's own `dial_deep_research` logger, independent of `LOG_LEVEL`. | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | pipe-separated layout with an OTEL trace block | No | Log line format (`logging` %-style; `%(levelprefix)s` and `%(otel_context)s` available). | |
| `LOG_DATE_FORMAT` | `%Y-%m-%d %H:%M:%S` | No | Timestamp format for log lines. | |
| `LOG_PAYLOADS` | `false` | No | Opt-in payload debugging — **local development only, never enable in a shared environment**. When `false`, logs carry no prompt/message content at any level, and the payload-capable `openai`/`httpx`/`httpcore` loggers are capped at `INFO` regardless of `LOG_LEVEL`. When `true`, the app logs assembled LLM requests at `DEBUG` (truncated) and the cap is lifted. | `true`, `false` |
| `LOG_PAYLOADS_MAX_LENGTH` | `2000` | No | Per-string character cap for payload records when `LOG_PAYLOADS=true`; longer values are truncated with a marker. Inert otherwise. | positive integer |
| `ENABLE_PLAYGROUND_CHANNEL` | `false` | No | Also register the `deep-research-playground` deployment: a tool-calling agent over the configured MCP servers, with no clarification or research flow, for testing MCP tools. | `true`, `false` |
| `ENABLE_ANNOTATIONS_DEMO` | `false` | No | Also register the `deep-research-annotations-demo` deployment: a fixed report citing the PDFs the caller attaches, its citations converted into inline citation annotations by the shared citation code, for checking how a client renders them. See [Inline citations demo](#inline-citations-demo). | `true`, `false` |
| **DIAL Core** | | | | |
| `DIAL_URL` | | ⚠️ Yes | Where the app finds DIAL Core. No built-in default. | |
| `DIAL_APP_NAME` | `deep-research` | No | OTel service name for traces. | |
| `HEARTBEAT_INTERVAL` | `5` | No | Seconds between DIAL keep-alive heartbeats during long-running responses. | |
| **MCP servers** | | | | |
| _(none)_ | | | MCP servers are per-client config, delivered as application properties, not env vars. | |
| **LLM models** | | | | |
| `LLM_MODELS_<ENUM_NAME>` | | No | Override the DIAL Core deployment id for a given `LLMModelsEnum` member. E.g. `LLM_MODELS_GPT_5_2_2025_12_11=gpt-5.2-custom-name`. | |
| `LLM_CACHE_POLICY` | | No | When set, every LLM call sends the `X-DIAL-CACHE-POLICY` header so DIAL Core's [prompt-cache](https://docs.dialx.ai/tutorials/developers/prompt-caching) routing follows the chosen retry policy. `cache-priority` keeps retries on the cache-warm upstream; `availability-priority` fails over to another upstream. Unset sends no header (Core defaults to `availability-priority`). | `availability-priority`, `cache-priority` |
| `MAX_CONTEXT_IMAGES` | `50` | No | Cap on image content blocks in any LLM request; overflowing image tool results are dropped and replaced with an explanatory tool error. The default is the per-request image limit of the models in use. Raise or lower it to match your provider. | positive integer |
| **Opik tracing** | | | | |
| `OPIK_TRACING_ENABLED` | `false` | No | Enable or disable Opik LLM tracing. | `true`, `false` |
| `OPIK_PROJECT_NAME` | `deep-research` | No | Opik project traces are grouped under. | |
| **Scripts & config generator** | | | | |
| `REMOTE_DIAL_URL` | | No | Remote DIAL that `make infra-config` pulls model configs from. Never read by the app. | |
| `REMOTE_DIAL_API_KEY` | | No | Api-Key for that remote DIAL. Never read by the app. | |
| `DIAL_API_KEY` | `dial_api_key` | No | Client-side Api-Key `scripts/send_conversation.py` and the compose `chat` service use to authenticate to DIAL Core. Never read by the app (it uses the per-request key). | |

### Notes on the environment variables

- A direct-mode MCP server's `connection` (in the application properties) must be a `$env:{VAR}` placeholder referencing an env var defined in `.env`.
- `DOCKER_DEFAULT_PLATFORM` in `.env.example` is consumed by Docker Compose (not the app): uncomment it on Apple Silicon because the DIAL images ship linux/amd64 only.

## DIAL core configuration

The `core` service reads its config as a **list of files** from `dial_conf/core/`
(merged by Core in the `aidial.config.files` order set in `docker-compose.yml`):

| File | Git | Content |
| ---- | --- | ------- |
| `generated/models.json` | ignored | model deployments pulled from a remote DIAL by `make infra-config`, plus the local `dial_api_key` and default-role limits from the committed `models-template.json`. Embeds the remote key — keep it local. |
| `generated/application-schemas.json` | ignored | the Deep Research application-type registration, rendered by `make infra-config` from the committed `application-schemas-template.json` with your `APP_PORT` baked into the endpoints. Core fetches the property schema live from the app's schema endpoint. |
| `applications.json` | ignored | your application instances ("channels"), seeded from the committed `applications-template.json`. |
| `annotations-demo-applications.json` | committed | the inline-citations demo's application entry, added to the list only by the annotations overlay (see [Inline citations demo](#inline-citations-demo)). Its endpoint names port 5010, so it works only while the app binds that port; edit that line to match your `APP_PORT` otherwise. |

Build all three local files with:

```sh
# needs REMOTE_DIAL_URL and REMOTE_DIAL_API_KEY in .env
make infra-config
```

- `generated/models.json` is (re)written on every run: each chat/embedding model of the
  remote DIAL becomes a local deployment routed through the `ai-dial-adapter-dial` container
  with the remote as upstream. Re-run the target to refresh models.
- **Prompt caching** is enabled on the model deployment in Core, not by this app.
  The app's only job is to keep request prefixes byte-stable — deterministic tool ordering
  and append-only message growth — so the cache can match across calls. Cached
  input tokens show up in the `tokens=` log field as `cache_read`. See the
  [prompt-caching tutorial](https://docs.dialx.ai/tutorials/developers/prompt-caching).
  - Core caching must be enabled on the deployment's `features` in one of two modes:
    **automatic** (`autoCachingSupported`) — Core chooses the cache breakpoints, no client
    changes needed; or **manual** (`cacheSupported`) — the client must mark breakpoints with
    `custom_fields.cache_breakpoint` on messages and tool definitions. This app does not set
    breakpoints, so its deployments must use automatic mode.
  - `X-DIAL-CACHE-POLICY` header (set via `LLM_CACHE_POLICY`) only affects
    which upstream Core routes to on a *retry*;
    it does not turn caching on or off. `cache-priority` value keeps a retry on the
    cache-warm upstream; `availability-priority` value sends the retry to a different upstream
    instead. The tutorial calls it
    `X-CACHE-POLICY`, which is not the name Core reads — use `X-DIAL-CACHE-POLICY`.
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
type via `applicationTypeSchemaId`, carry that channel's `applicationProperties`, and grant
the chat key's role access to the instance under `roles.default.limits`. The committed
[`applications-template.json`](./dial_conf/core/applications-template.json) shows both parts
for a fictional example instance:

```json
{
  "applications": {
    "deep-research-acme": {
      "displayName": "ACME Deep Research",
      "applicationTypeSchemaId": "https://mydial.epam.com/custom_application_schemas/deep-research",
      "applicationProperties": { }
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

> ℹ️ `applicationProperties` is elided above. `applications-template.json` shows it filled in
> with the required properties only; `docs/generated-app-schema.json` is the authoritative list
> of every property, required or optional, with its description and default. A property the
> config omits takes the default from that schema, so a channel only needs to state what it
> wants to differ.

`mcp_servers` lists the MCP servers the research agent connects to (at least one is
required; `server_name` must be unique across the list). Each server states which supported
retrieval server it is in `server_type` — `generic_rag` for one serving documents, `statgpt`
for one serving datasets — and at most one server of each type may be configured, because a
report's citation carries an id and never the server that issued it. A `generic_rag` server must
also name its `file_sharing_tool` (`get_citation_url`, for a Generic RAG deployment): the reader
opens a cited page through the copy that tool makes, so a document server without it would deliver
every citation as plain text. Each server is one of two modes:

- **deployment** — set `deployment_id`: the MCP is a DIAL application reached through Core
  by that deployment id, authenticated with the per-request api-key (the request bearer
  token is forwarded for per-user access).
- **direct** — set `connection`: a directly-reachable MCP server, authenticated with a
  static api-key in the `api-key` header.

In direct mode, `connection` must be a `$env:{VAR}` placeholder resolving to a JSON object
`{"url": "...", "api_key": "..."}`, expanded from the app's environment at load time.
Set `tools_to_include` to restrict a server to named
tools (empty = include all).

Real client instances stay in the gitignored local file — never commit them.

### Playground (optional)

The templates also register a second application type, `deep-research-playground`, with an
example instance (`deep-research-playground-acme`). It reuses the **same** application-properties
schema (so its instances still carry `prompts`) but routes to a
separate app-server deployment: a single tool-calling agent over the configured MCP servers, with
no clarification or research flow, for testing MCP tools. The app serves that deployment only when
run with `ENABLE_PLAYGROUND_CHANNEL=true`; otherwise Core's forward to it returns an error.

## Local run

### Prerequisites

- Docker Desktop 4.x (Compose V2)
- Python 3.13
- [Poetry](https://python-poetry.org/docs/#installation) (Python package manager)
- At least one MCP server (e.g. generic-RAG) for the research agent — either registered as a DIAL application (deployment mode) or directly reachable via URL + api-key (direct mode). Configured per channel in the instance's application properties, not in `.env`.
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
make install          # runtime + dev deps; use `make install-all` if you want Opik tracing
make infra-config     # build the local DIAL core config (see "DIAL core configuration")
make infra-up
make app
```

Then open DIAL Chat UI at [http://localhost:3010](http://localhost:3010), select the **Deep Research** application, and send your query.

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
- Inside the container `localhost` means the container itself. Any URL that points at a
  service on your host — a `.env` URL (e.g. Opik) or a direct-mode MCP server `url` in the
  application properties — must use `host.docker.internal` instead.

## Inline citations demo

A second chat completion that answers with a **fixed report** demonstrating how the delivered
report's citations become DIAL inline citation annotations: each paragraph of the reply shows one
behaviour and says in its own text what should appear at that spot. It runs no research and calls
no model, so it is the cheap way to check how a client renders a citation.

The report cites the PDFs you attach. Two of them become documents 1 and 2, in the order they
arrive, and which file becomes which does not matter. A third document is cited with nothing
attached behind it, which is the case where no URL resolves and the marker text stays as written.
An attachment already lives in your own storage, so the annotations point straight at it and the
demo copies nothing anywhere.

**Only the next-generation chat UI draws inline citation pills**, and no released version carries
the marker-tag rendering this feature emits yet. The overlay below adds such a chat beside the
base one so the same reply can be opened in both.

Bring it up:

```sh
# 1. Add the identity-provider values the next-generation chat needs to .env (see .env.example),
#    then start infra with both chat generations and the demo registered in core.
make annotations-up

# 2. Run the app with the demo deployment enabled.
ENABLE_ANNOTATIONS_DEMO=true make app
```

Then open the next-generation chat at <http://localhost:4207>, log in as a real user, and start a
conversation with **Deep Research - Inline Citations Demo** (deployment id
`deep-research-annotations-demo`). Attach two PDFs of at least three pages each and send any
message. Attach anything else — one file, a shallower PDF, nothing at all — and the demo says
what to attach rather than answering with half its cases working.

What to look for in that reply:

- a pill at every citation the text says should have one, including the one in the table cell and
  the one in the heading, and none where the text says the marker stays as it was written (the
  document you attached nothing for);
- one pill for the run of three adjacent citations, its popup carrying two sources — the source
  cited twice inside the run is listed once;
- separate pills for the same document cited in two places, each opening its own page;
- clicking a pill opens the attached PDF at the cited page;
- no raw `<cit …>` tag and no placeholder text anywhere in the text.

Opening the same reply in the base chat at <http://localhost:3010> shows what a client that does
not understand the marker tags does with it.

## Driving the app from the CLI

`scripts/send_conversation.py` drives a multi-turn conversation against a running stack —
useful for testing without the chat UI:

```sh
# fresh conversation
poetry run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite -d deep-research-acme
# follow-up turn, threading prior state
poetry run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue -d deep-research-acme
```

`-d`/`--deployment` targets an application instance registered in DIAL Core.
Calling the bare `deep-research` type deployment returns the
"not configured" reply — instances carry the configuration.

## LLM tracing with Opik (optional)

The agent's per-turn LangChain run can be traced into [Opik](https://github.com/comet-ml/opik) — every turn becomes one hierarchical trace covering the agent graph, the LLM calls, and every MCP tool call. **Off by default**; opt in per-developer.

Only local Opik is supported for now. Non-local Opik is not yet supported.

The `opik` Python package is an **optional dependency** (the `tracing` extra): it pulls a
large dependency tree and is only used for local tracing, so the production Docker image
omits it. `make install-all` installs it (via `poetry install --all-extras`). Tracing is off
by default, so the opik-less image runs normally; if you set `OPIK_TRACING_ENABLED=true` in
an environment where the `tracing` extra is not installed, the app **fails fast at startup**
with a clear error rather than silently running untraced.

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

## Spec-driven development

Changes are planned as specs before they are coded, using the `openspec` CLI. Two
directories hold everything:

- **`openspec/specs/<capability>/spec.md`** — the living contract: what the app does
  today, written as requirements with WHEN/THEN scenarios.
- **`openspec/changes/<name>/`** — one proposed change: `proposal.md` (why and what),
  `specs/` (the delta against the living specs), `design.md` (how), `tasks.md` (the
  implementation checklist). On archive the delta folds into `openspec/specs/` and the
  change moves under `openspec/changes/archive/`.

Two Claude Code skills wrap the planning half, so the approach is settled — and
challenged — before any code exists:

```
/plan-change <description>   clarify scope with the user, then write
                             proposal → specs → design
/review-plan <name>          adversarial loop: a critic subagent asks whether the
                             change makes sense at all, then hunts gaps, then checks
                             the artifacts against each other; every finding is
                             verified against the real code and logged to the
                             change's review-log.md
       ↓                     you read the artifacts + review log, and approve;
                             the review log is scratch and is deleted on approval
/opsx:continue               tasks
/opsx:apply                  implement
/opsx:verify                 implementation vs artifacts
/opsx:archive                fold the delta into openspec/specs/
```

`/plan-change` deliberately stops before `tasks`: it depends on both specs and design,
so every accepted review finding would churn it. In the review loop, gaps and
inconsistencies are fixed automatically, but findings that question the **approach**
are always escalated to a human instead of applied.

For a change too small to be worth reviewing, `/opsx:propose` writes all four artifacts
in one pass.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
