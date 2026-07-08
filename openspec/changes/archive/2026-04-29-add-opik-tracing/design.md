## Context

The deep-research app is a DIAL chat-completion built on a per-request LangChain `create_agent` (LangGraph under the hood) with MCP tools. Today, the only observability comes from `aidial-sdk[telemetry]` (HTTP-level OTel spans) and stdlib logging — neither captures LLM/tool-level structure (system prompt, model inputs, per-tool latency, tool errors). Diagnosing a bad answer or a slow turn means correlating logs by hand. Opik is an open-source LLM observability product (Comet, Apache 2.0) with a first-class LangChain callback that records the agent run, the LLM call, and every tool call as a hierarchical trace, viewable in a local UI.

This change wires Opik in as an **additive** observability layer: the existing OTel telemetry stays, the agent control flow stays, and the new tracer is silently absent when Opik is not configured.

Stakeholders: deep-research developers (debugging), eval/QA (replaying turns), and ops (latency / failure attribution). For a v1, the audience is developer-local debugging — eval/QA integration is out of scope.

## Goals / Non-Goals

**Goals:**

- Capture every deep-research turn end-to-end as one Opik trace: agent run → LLM call → each MCP tool call, with inputs, outputs, errors, and timings.
- Local debugging without a cloud account: `make opik-up` + (opt-in env config) + `make run` produces traces in a local Opik UI.
- Tracing is **opt-in**: when Opik is not configured the agent runs identically to today (no tracer attached, no startup failure, no hidden network calls). Defaults stay off across the board (settings flag, env, Makefile).
- Self-hosted (local) and Comet-hosted Opik MUST both work via the same settings shape.
- The Opik stack lifecycle is **fully independent** of the infra stack: `make up` / `make down` MUST NOT touch Opik containers, and `make opik-up` / `make opik-down` MUST NOT touch infra containers. Either side can restart without disturbing the other.

**Non-Goals:**

- No Opik Datasets, Evaluation, or Experiments integration in this change (eval repo's job).
- No replacement of `aidial-sdk[telemetry]` OTel — Opik is additive.
- No tracing of non-agent code paths (health endpoint, request parsing, DIAL stage emission). The agent run is the unit of value; everything else is uninteresting plumbing.
- No per-user-key handling: traces are tagged with the deployment, not the end user (the app already deliberately uses a single service `DIAL_API_KEY`).
- No tracing-on-by-default: shipping a `.env.example` that flips `OPIK_TRACING_ENABLED=true` is explicitly rejected — contributors who haven't started `make opik-up` would get noisy unreachable-Opik attempts. Opt-in is set at the contributor's local config, not at the repo level.

## Decisions

### 1. Integration surface: `OpikTracer` callback on `agent.astream(...)`

`opik.integrations.langchain.OpikTracer` is a LangChain `BaseCallbackHandler`. We attach it via `config={"callbacks": [tracer]}` in `_AgentRunner.run` at the single `astream` call site (`completion.py:83`). Because LangChain's `create_agent` is built on LangGraph and the MCP tools are wrapped as LangChain `BaseTool`s by `langchain-mcp-adapters`, the callback captures: graph node transitions, the LLM call (with prompt + response), and each tool invocation (with args + result + error). No per-function decorators, no per-tool wrappers.

**Alternatives considered:**
- `@opik.track` decorator on `chat_completion`: produces one span per turn but loses the agent/LLM/tool structure. Rejected — the structure is the point.
- `track_openai` on the underlying `AzureChatOpenAI` HTTP client: would trace the LLM call but miss the agent graph and tool calls. Rejected — same reason.
- OTel auto-instrumentation via OpenLLMetry / Opik's OTel ingestion: more pieces to configure, no clear win for our LangChain-only stack. Rejected for now; could revisit if/when we instrument non-agent code.

### 2. Activation gate: explicit boolean, defaulted off

Add an `OpikSettings.tracing_enabled: bool` field (default `False`, env `OPIK_TRACING_ENABLED`). The tracer is attached **iff** this flag is true. The single companion field is `project_name` (see Decision 4 for the full settings shape).

**Why an explicit boolean rather than "enabled iff project name set"**: removes ambiguity, lets us A/B-toggle without unsetting other vars, and matches the existing settings style (`heartbeat_interval`, `log_level` are explicit values, not derived).

**Where activation happens**: a small helper `app/tracing.py` exposes `build_opik_tracer(settings) -> OpikTracer | None`. `_AgentRunner.__init__` calls it once, stores the result, and includes `[tracer]` in the `astream` callbacks list only when non-None. `opik.configure(use_local=True, project_name=...)` is called once at app startup in `factory.py` (gated on the same flag) so the SDK is configured before any tracer is built.

### 3. Local Opik via a Makefile wrapper around upstream Opik's compose

Opik's local deployment is large (~400-line `docker-compose.yaml`, 9+ services, plus auxiliary config files mounted as host volumes — ClickHouse server XML, NGINX templates, OTel collector config). Vendoring those files into this repo would be brittle (drift from upstream) and noisy (hundreds of lines of third-party infra config in a small DIAL chat repo). Cloning the upstream Opik repo at `make opik-up` time is the pragmatic alternative.

The Makefile gains two targets that:

1. Ensure `.opik-local/` exists (a gitignored shallow clone of `github.com/comet-ml/opik` pinned to a specific release tag — `OPIK_VERSION` Make variable, e.g. `1.x.y`).
2. Run `docker compose -f .opik-local/deployment/docker-compose/docker-compose.yaml --profile opik up -d` (or the matching `down`).

The upstream compose declares `name: opik`, so it runs as a separate Compose **project** from ours. `docker compose up` / `docker compose down` from our repo root operates only on our own project (`docker-compose.yml`) and never touches Opik containers — and vice versa. This is what gives us the lifecycle-independence guarantee, "for free" from Compose's project-scoping rules.

**Why this rather than vendoring a `docker-compose.opik.yml`**: see section context above — the upstream compose references multiple host-mounted config files we'd have to vendor and maintain in lockstep. The wrapper is ~10 lines; a vendored compose is hundreds of lines plus drift maintenance. The cost of the wrapper is one extra `git clone` on first `opik-up` (cached afterwards).

**Why this rather than a Compose profile in our existing `docker-compose.yml`**: profiles filter `up`, not `down`. With profiles, `docker compose down` from the repo root would tear down both infra and Opik, breaking the lifecycle-independence goal.

**Pinning**: the Makefile sets `OPIK_VERSION` to a specific Opik release tag (not `main`/`latest`), and `--depth 1 --branch <tag>` keeps the checkout small and reproducible. Bumping Opik is a one-line `OPIK_VERSION` change. The pin satisfies the `local-stack` "Pinned infrastructure images" requirement at the source-revision level.

**Host ports**: upstream defaults — Opik UI at `http://localhost:5173`, with the SDK ingestion endpoint at `http://localhost:5173/api` (the frontend NGINX proxies `/api` to the internal backend). 5173 doesn't collide with our existing host bindings (`3000`, `3001`, `5000`, `8080`, redis).

**Alternatives considered:**

- **Vendor a self-contained `docker-compose.opik.yml`**: rejected — would also require vendoring the auxiliary config files (ClickHouse XML, NGINX templates, OTel config) and tracking upstream changes manually. High maintenance cost, brittle, low payoff.
- **Compose profiles in our existing `docker-compose.yml`**: rejected — `down` filtering doesn't work, so the independent-lifecycle goal isn't achievable.
- **Reference upstream via Compose `include:`**: still requires the upstream files on disk, so it doesn't avoid the clone; adds Compose V2.20+ dependency. No benefit over the explicit `-f` flag.
- **Document "run Opik separately"**: pushes setup burden onto contributors. The Makefile target is the zero-config replacement.
- **Hosted-only (Comet)**: fine for prod but doesn't satisfy the local-dev goal.

### 4. Dedicated `OpikSettings` class, not new fields on `DialAppSettings`

Opik configuration lives in its own pydantic-settings class, sibling to `DialAppSettings` and `McpSettings`:

```python
class OpikSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPIK_")

    tracing_enabled: bool = False         # → OPIK_TRACING_ENABLED
    project_name: str | None = None       # → OPIK_PROJECT_NAME

opik_settings = OpikSettings()
```

`tracing.py` calls `opik.configure(use_local=True, project_name=settings.project_name)` when tracing is enabled. `use_local=True` is the SDK's native switch for "self-hosted at localhost"; it picks the right ingestion URL, port, and auth defaults so we don't need to surface any of those as settings.

**Why a dedicated class rather than extending `DialAppSettings`**: this codebase already separates concerns by infra surface — `DialAppSettings` is for the DIAL chat-completion app (host/port, DIAL key, log level, heartbeat), `McpSettings` is for the MCP client (URL + key). Opik is a third infra surface (the trace sink); giving it its own class keeps each settings object cohesive, lets the tracing module depend only on `OpikSettings` (no spurious coupling to DIAL-app fields), and matches the existing precedent.

**`env_prefix="OPIK_"`** on the class lets the field names be terse (`tracing_enabled`, `project_name`) while still mapping to the `OPIK_*` env-var convention. Per project memory the rule against new aliases is about per-field `alias=...`; an `env_prefix` on the class is structural, not per-field, and is the idiomatic pydantic-settings way to share a prefix across related fields.

**Why local-only (no api key / url override / workspace / port surfaced)**: this repo's primary observability story is `make opik-up` + a local trace UI. Manual smoke-testing confirmed that `opik.configure(use_local=True, project_name=...)` is the only thing the app needs — the SDK's local-deployment defaults handle URL, port, and auth correctly. Adding api-key / URL / workspace / port fields would be speculative surface area for a Comet-cloud path we don't ship. Anyone needing a non-local Opik instance can configure the SDK directly via its native `OPIK_*` env vars / `~/.opik.config` and our class doesn't get in the way.

**No automated test coverage for `OpikSettings`.** The integration is exercised manually against the local Opik stack (see Migration Plan); the four fields are plain pydantic-settings primitives and don't need pinned tests. `DialAppSettings` is untouched, so its existing tests still pass unchanged.

The flag stays `False` at the repo level — there is no `.env.example` shipping `OPIK_TRACING_ENABLED=true`. Contributors opt in by setting it in their own local environment.

### 5. Trace scoping per turn

Each `_AgentRunner` instance corresponds to one DIAL chat-completion turn. Building a fresh `OpikTracer()` per runner gives one trace per turn — clean boundaries, easy correlation with DIAL's per-request structure, no shared mutable state across requests. The cost is negligible (the tracer is a thin object).

We do **not** propagate trace context from DIAL's incoming request envelope into Opik (no `parent_id` plumbing). DIAL doesn't carry an Opik-shaped trace id today; the existing OTel path covers HTTP-level correlation. Could be revisited if eval/QA wants to link external trace ids.

## Risks / Trade-offs

- **Local stack heaviness** → mitigation: gate via Compose profile so default `make up` is unchanged; document `make opik-up` as the opt-in.
- **Opik self-host docs/images shift between versions** → mitigation: pin a specific Opik version in `docker-compose.yml`, refresh deliberately like other infra images.
- **Sensitive data in traces** (system prompt, retrieved documents, DIAL keys) → mitigation: local-only by default; document that Comet cloud usage requires reviewing what gets shipped (system prompt is fine; tool outputs may contain customer-derived RAG content). For v1 we don't redact.
- **Tracer failure shouldn't break turns** → `OpikTracer` exceptions inside callback handlers should be swallowed by LangChain's callback machinery; we additionally rely on the existing top-level error funnel (`completion.py:46`) so any escaped exception still produces the friendly error string. We do **not** add a second try/except layer around the callback — the existing funnel is sufficient.
- **Two observability systems (OTel + Opik) running in parallel** → small CPU overhead per turn; acceptable given they answer different questions (HTTP/infra vs. LLM/agent).

## Migration Plan

This is additive. No existing behaviour changes when the flag is off; existing tests and local `.env` files keep working unchanged.

Rollout order at implementation time:

1. Add settings fields and `tracing.py` helper (off by default — no functional change).
2. Wire the callback in `_AgentRunner.run` (still a no-op until the flag is on).
3. Add `make opik-up` / `make opik-down` wrapping a gitignored `.opik-local/` clone of upstream Opik at a pinned tag; verify the two lifecycles are independent (start infra, start Opik, stop one without affecting the other).
4. Document in `envvars.md` and the README dev-loop section — including the explicit set of env vars a contributor needs to set in their own local config to opt in.

Rollback: unset `OPIK_TRACING_ENABLED` (or set to `false`) — tracer detaches, no other change. The `opik` dependency stays in `pyproject.toml`; removing it requires a separate revert.

## Open Questions

- Exact Opik self-host image set and version to pin (Opik's docs are the source of truth at implementation time; default to the version Opik themselves recommend for `docker compose up`).
- Do we want a `make logs-opik` shortcut? Defer — `docker compose -f .opik-local/deployment/docker-compose/docker-compose.yaml --profile opik logs <service>` is fine for v1.
