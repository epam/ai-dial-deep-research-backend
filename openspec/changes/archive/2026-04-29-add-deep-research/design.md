## Context

The repo today is a DIAL-protocol scaffold: an `EchoCompletion` registered under deployment id `echo`, wired through `aidial_sdk.DIALApp` in `factory.py` with telemetry + heartbeat. No agent, no LLM call, no external integrations. The first real feature (per the proposal) is a tool-calling agent backed by a generic-RAG MCP server, exposed as `deep-research`.

Constraints baked in by the proposal: HTTP MCP only, fixed `api-key: <key>` header, GPT-5 family only, no planning/subagents/skills/memory, no cross-turn tool-state persistence, single user-facing error message (errors logged server-side, never re-raised).

## Goals / Non-Goals

**Goals:**
- Establish the per-request resource-scoping pattern, the LLM-config shape, the stage-streaming convention, and the error funnel that subsequent deep-research changes will inherit.
- Keep the scope small enough that the design fits on one page and the implementation is reviewable in a single PR.
- Prefer the simplest shape the small scope justifies.

**Non-Goals:**
- Cross-turn persistence of tool messages via DIAL `state`.
- Multiple MCP servers, MCP resources/prompts, or MCP transports other than HTTP.
- Models outside the GPT-5 family.
- Per-feature LLM configs (we have one agent → one config).
- A configurable system prompt or an MCP-tool-allowlist filter.
- Replacing `app-config`, `dev-environment`, or `local-stack` capabilities; they stay as-is.

## Decisions

### LLM configuration

`LLMModelConfig` is a plain pydantic `BaseModel` (not `BaseSettings`) with field-level defaults: `deployment: LLMModelsEnum`, `reasoning_effort: ReasoningEffortEnum | None`, `verbosity: VerbosityEnum | None`. No `temperature`/`seed`/`top_p` — GPT-5 reasoning models reject them, so omitting them prevents footguns. `api_version` is **not** a config field — it's a module-level `_API_VERSION = "2025-04-01-preview"` constant in `llm.py`, since we have no use case for varying it per call site and exposing it on the config makes it look more configurable than it actually is.

`api_version="2025-04-01-preview"` is the latest dated Azure OpenAI preview as of this change (per Microsoft Foundry docs, April 2026) — uses OpenAPI 3.1 and supports GPT-5 reasoning controls. Note: starting August 2025, Microsoft introduced a next-generation v1 GA API that removes `api-version` entirely (use `ChatOpenAI` pointed at the Azure endpoint instead of `AzureChatOpenAI`); we deliberately stay on the dated-preview / `AzureChatOpenAI` path for now. Migrating to the v1 paradigm is a separate, larger change and out of scope here.

`LLMModelsEnum` enumerates supported GPT-5 variants. Each member's `deployment_id` property reads `LLM_MODELS_{NAME}` env to map model → DIAL deployment id. `base_url` is implicit (always `DIAL_URL`).

A single factory `get_chat_model(model_config: LLMModelConfig) -> AzureChatOpenAI` constructs the chat model. The DIAL Core URL and API key come from settings (`dial_settings.dial_url`, `dial_settings.dial_api_key`); the factory has no key parameter (see "Service-key model"). The `SecretStr` wrapping happens at the settings layer rather than inside the factory.

**Alternative considered:** a two-layer split (a settings class for env-loaded defaults + `LLMModelConfig` for per-feature overrides). Rejected — we have one agent, one config; field-level defaults are simpler.

### Service-key model (no per-request user key)

Both downstream credentials are **static, env-driven service keys** held by the app — neither comes from `request.api_key`:

| Downstream | Key | Setting | Env var |
|---|---|---|---|
| LLM via DIAL Core | DIAL Core service key | `dial_settings.dial_api_key` (`SecretStr`) | `DIAL_API_KEY` |
| Generic-RAG MCP | MCP service key | `dial_settings.mcp_api_key` (`SecretStr`) | `MCP_API_KEY` |

`get_chat_model(model_config)` reads `dial_api_key` from settings internally — there's no `api_key` parameter. The chat completion handler does not touch `request.api_key`; it can stay populated by the SDK but we ignore it.

**Rationale:** the deep-research app is a service that runs against the local DIAL Core deployment. Quotas and billing land at the service level rather than per-user; this is what an internal app wants. Both downstream calls behave the same way (static service key, application-owned), which keeps the handler dead simple — no key threading, no auth-context type, no system-vs-user-mode dispatch.

**Implications:**
- No auth-context machinery (user/system auth-context types, bearer-token gating, role checks) is needed or adopted. We have no call site that would choose between user mode and system mode.
- Multi-tenancy / per-user quota enforcement is delegated to whatever fronts the app (DIAL Core's own auth on the chat application). The deep-research app does not enforce caller identity.
- If a future change introduces a use case where a user's key must flow to DIAL (e.g., billing per user), we'd add it as an additive concern — most likely by reading `request.api_key` in the handler and overriding the default. The current design doesn't preclude that.

**Alternatives considered:**
- Per-request user key threading (`request.api_key` → `get_chat_model`). Rejected — adds plumbing (handler reads key, factory takes key parameter) for a benefit (per-user billing) we don't currently need.
- A full auth-context + system-user-role pattern. Rejected — that suits an app with admin endpoints, background jobs, and bearer-token-gated flows. We have one chat completion handler and no background work.

### Per-request MCP client scoping

`MultiServerMCPClient` and the LangChain agent are constructed inside `chat_completion(self, request, response)`, fresh each call. No process-wide caching of either the client or the tool list.

**Lifecycle:** because `MultiServerMCPClient` is **stateless by default**, the per-request "lifecycle" is trivial — construct the client, await `client.get_tools()` once, hand the tools to the agent, and let the client object fall out of scope when the request finishes. There is no explicit teardown to do; each tool invocation during the request opens (and closes) its own short-lived `ClientSession` internally. The only per-request cost on top of normal tool-call traffic is the tool-list round-trip.

**Cost:** an HTTP handshake + a tool-list round-trip on every request before any agent work. For a single MCP server on the same network this is in the low-ms range (assumption, not measured). Future optimization: cache the tool list with a TTL while keeping the client per-request.

**Why per-request and not startup-load:** the generic-RAG MCP server can be redeployed with new (or removed) tools at any time. A startup-loaded tool list goes stale silently and stays stale until the deep-research app is restarted, which is a worse failure mode than a small per-request latency cost. Per-request scoping makes the agent always see the current tool set; if the MCP server is unreachable, the request fails loudly via the error handler instead of succeeding against a stale cache.

**Why `MultiServerMCPClient` for one server:** `langchain-mcp-adapters` does not expose a dedicated single-server client. The lower-level `load_mcp_tools(session)` requires manual `ClientSession` lifecycle management, which we'd just be reinventing.

**Two post-load helpers wrap the tool list before it reaches the agent** (`mcp_client.py`):

- `enable_tool_error_handling(tools)` — sets `tool.handle_tool_error = True` on every tool. Without this, a `ToolException` raised by `langchain-mcp-adapters` (when the MCP server returns an error response, including its own pydantic validation rejections) bubbles past LangChain's `ToolNode` — whose default handler only catches `ToolInvocationError`, not `ToolException` — and the whole chat completion fails. With it set, the tool returns the error text as its result with `status="error"`; the agent receives that as a `ToolMessage` in its next step and can retry with corrected args. This is what backs the spec's "Tool error stage signals failure but does not abort the turn" scenario. `handle_validation_error` is intentionally not set: `BaseTool._parse_input` skips client-side validation when `args_schema` is a dict (which is what `langchain-mcp-adapters` produces for MCP tools), so client-side `ValidationError` never fires here — server-side rejections come back as `ToolException` instead.
- `sanitize_tool_schemas(tools)` — workaround for a `fastmcp`-side bug. Some MCP servers (notably the generic-RAG MCP server's `list_documents` / `data_retrieval` / `search` tools) emit JSON schemas whose `$ref` paths don't resolve in `$defs`, because `fastmcp.compress_schema(prune_defs=True)` over-aggressively prunes a dynamically-generated type and leaves a dangling reference. LangChain's tool binder calls `dereference_refs` on the schema and raises `KeyError` on the unresolved ref, killing the whole turn. The helper walks each tool's `args_schema`, drops any unresolvable `#/$defs/<name>` reference, and leaves the surrounding object as a permissive `{}`. Conservative — we don't drop the tool, we just stop arg-validation on the affected fields. Should be removed once `fastmcp` fixes the upstream bug.

### Auth: `api-key` header (HTTP only)

The MCP API key (one env var) is sent as `api-key: <key>` via `MultiServerMCPClient`'s `headers` config. Header name is fixed.

**Why not `Authorization: Bearer`:** the target generic-RAG MCP server expects `api-key` per its existing convention. Forcing a different header name on the client side would just diverge from server expectations.

**Why HTTP-only:** stdio doesn't carry headers, so authentication would have to flow through env / args — different shape, different threat model. Keeping HTTP-only matches our auth contract and the realistic deployment topology (MCP server runs as a separate service).

### Message history vs DIAL chat content

Inside a single chat-completion call: the agent's LangChain history includes the user/assistant text from `request.messages` plus the `AIMessage(tool_calls=[...])` and `ToolMessage(...)` records LangGraph generates during tool calls. All of it is fed into the LLM on each step.

What hits the DIAL response: only assistant text (string `chunk.content`) goes through `choice.append_content(...)`. Tool calls and tool results are written to dedicated stages (see next decision), not to choice content.

**No state persistence across turns:** tool messages are not round-tripped through DIAL `state`, so later turns cannot replay them. Multi-turn requests will see prior assistant text from `request.messages` as opaque strings; the agent will not know which tools produced earlier answers.

**Alternative considered:** a full history class that persists tool messages through DIAL `state`. Rejected for MVP — `state` round-tripping adds complexity (custom JSON shape, message-class registry) we don't yet need. Easy to add later when multi-turn quality demands it.

### Tool-call streaming as DIAL stages

Each tool invocation produces a single "result" stage that carries both the input arguments (under an **Input** section) and the tool's output (under **Output**, or **Error** when the tool failed). The stage is opened when the `ToolMessage` arrives.

**Timing semantics:** `start` is captured when the agent emits the tool call (i.e. tool execution begins from our perspective), `end` is when the result arrives. Both go into the stage title alongside the elapsed seconds — that's what makes per-tool latency visible.

Title format: a normalized `[TOOL] "<tool_name>" - <action> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where action ∈ `{result, error}` and emoji ∈ `{✅, ❌}` respectively. The `[TOOL]` prefix groups stages visually in the chat UI; the trailing emoji makes success/error distinguishable at a glance even when titles are truncated. Body format: `**Input**\n\n```json\n<args>\n```\n\n**Output**\n\n```\n<result>\n```` (the **Output** label flips to **Error** for the error variant; the fence around the result preserves newlines either way).

**Implementation: pure title formatters, not a context-manager port.** `dial_stages.py` exposes only `timed_stage_title` + `result_stage_title(tool_name, start, end, is_error=...)`; the completion handler opens the DIAL stage inline via `with self._choice.create_stage(title): ...`. We do **not** add context-manager stage helpers that wrap "open at start → close at end". Reason: in this MVP the stage is opened only when the tool result arrives (driven by `agent.astream(stream_mode="updates")`, which yields the AI tool-call message and the `ToolMessage` in adjacent updates), so there's no "open at start → close at end" window for a context-manager helper to wrap. A follow-up change that opens the stage at tool-call time (likely via `astream_events`) will introduce that helper shape; deferring it now keeps the surface minimal and trivially unit-testable as pure functions.

**Output rendering richer than "wrap in a fence."** For each tool's `ToolMessage.content`, the body builder in `completion.py` does more than dump a single fenced code block: when content arrives as LangChain content blocks (`{"type": "text", "text": "...", "id": "..."}`), each block renders as a structured `**id**` / `**type**` / `**text**` layout separated by horizontal rules, and JSON-shaped strings are recursively unwrapped + pretty-printed (`_render_output_section`, `_render_content_block`, `_maybe_prettify_json`, `_deep_parse_json`). This is purely a presentation concern — the spec's contract ("input + output rendered as fenced markdown so multi-line payloads stay readable") is preserved; we just give the chat UI a more navigable layout when the MCP server returns nested JSON or multiple content blocks.

**Alternative considered:** a lighter `[<elapsed>s]` suffix on the stage title. Rejected — the user explicitly asked for a format with start + end timestamps.

**Alternative considered:** a separate "call" stage emitted before the result. Rejected after we consolidated input + output into the single result stage; the call stage's content was redundant and we were emitting both stages at the same instant anyway (we don't open the call stage live — `agent.astream(stream_mode="updates")` yields the AI tool-call message and the ToolMessage in adjacent updates with no streaming hook in between). Live "tool is running" feedback would require restructuring around `astream_events` and is deferred.

### Top-level error handling

`chat_completion(self, request, response)` wraps its body in `try/except`. On any exception:
1. Log the exception (class + message + traceback) via the module logger at `ERROR` level.
2. Write a short, user-facing error message into the assistant choice via `choice.append_content(...)` — e.g. `"Sorry, something went wrong while processing your request. The error has been logged."`. The exception details are **not** included in the user-facing string.
3. Return normally — do **not** re-raise. The DIAL response completes successfully from the SDK's perspective.

**Why log-and-respond instead of raise:** raising `InternalServerError` shows a generic UI error indicator with no context; the user has to retry or open a ticket. Returning a friendly assistant message keeps the conversation flowing, and the operator gets the full traceback in logs. We only lose the chat UI's "this turn errored" treatment, which we don't need.

**Single error type by design.** We do not distinguish `RateLimitError` / `BadRequestError` / `ContentFilterFinishReasonError`. Every failure becomes the same friendly assistant string for MVP; finer classification when there's evidence we need it.

**Alternatives considered:**
- Re-raise as `InternalServerError`. Rejected per above.
- Append the full exception text to assistant content. Rejected — leaks stack traces into user chats.

### Replacing echo-app

`app/completion.py` is **reused**: the `EchoCompletion` class and its `_extract_last_user_text` helper are replaced by the new agent-backed handler class in the same file (no file deletion, no rename). `factory.py` re-registers the deployment as `deep-research` instead of `echo`.

The structural requirements echo-app pioneered (DIAL-protocol conformance, streaming response path, health endpoint) survive — they reappear under `deep-research`'s spec rather than as a separate `dial-app-server` capability.

**Alternative considered:** extract the structural pieces into a new `dial-app-server` capability that both `deep-research` and any future deployments share. Rejected for now — premature abstraction with one consumer.

### Names: UI display, deployment id, telemetry

Three distinct strings, each lives in exactly one place:

| Name | Value | Where |
|---|---|---|
| Deployment id | `deep-research` | code (`factory.add_chat_completion(...)`), `dial_conf/core/config.json` `applications` key, endpoint URL |
| UI display name | `Deep Research` | `dial_conf/core/config.json` → `applications.deep-research.displayName` |
| Telemetry service name (`DIAL_APP_NAME` env) | `deep-research` (default) | `DialAppSettings.dial_app_name`, passed to `TelemetryConfig.service_name` so OTel traces label this service by its technical id |

The deployment id is the only identifier code references; OTel traces use the same value so service identifiers in observability tools match the deployment id one-to-one. The UI display name is decoupled so DIAL admins can rename it without touching code or telemetry. `DIAL_APP_NAME` default flips from `Echo` to `deep-research`.

### DIAL UI display string and config update

The chat UI's display label comes from `dial_conf/core/config.json` → `applications.<deployment_id>.displayName`. As part of this change, that file flips from:

```json
"echo": { "displayName": "Echo", "endpoint": ".../echo/...", ... }
```

to:

```json
"deep-research": { "displayName": "Deep Research", "endpoint": ".../deep-research/...", ... }
```

`description`, `descriptionKeywords`, and `roles.default.limits` are updated to match the new deployment id.

### Settings layout

Settings are split by domain:

- **`DialAppSettings`** (existing class, extended): `app_host`, `app_port`, `dial_url`, `dial_app_name`, `log_level`, `heartbeat_interval` (existing) + `dial_api_key: SecretStr` (new). Default for `dial_app_name` flips from `Echo` to `deep-research` (used as the OTel service name).
- **`McpSettings`** (new class): `mcp_url: str`, `mcp_api_key: SecretStr`. Lives in its own pydantic-settings class because MCP is a separate downstream service with its own URL + credential.
- **`LLMModelsEnum.deployment_id` reads env vars directly** (no dedicated settings class). Each enum member resolves to a DIAL deployment id at access time via `os.getenv(f"LLM_MODELS_{member.name}", self.value)` — the env var is an optional override; if unset the enum's `.value` (the canonical model id) is used. Example: `LLM_MODELS_GPT_5_2_2025_12_11=gpt-5.2-custom-deployment` lets DIAL admins point the code-side constant at a non-default deployment name without code changes.

### LLM_MODELS env var convention

Env var name = `LLM_MODELS_{ENUM_MEMBER_NAME}` — the uppercase Python enum member name with no transformation. Examples:
- Enum member `GPT_5` → env var `LLM_MODELS_GPT_5` → value is the DIAL deployment id (e.g. `gpt-5` or `gpt-5-2025-04-01`).
- Enum member `GPT_5_MINI` → env var `LLM_MODELS_GPT_5_MINI` → value is the DIAL deployment id for the mini variant.

If the env var is unset for a member, `deployment_id` falls back to the enum's `.value` (the canonical model id). No error is raised — operators only set `LLM_MODELS_<NAME>` when they need to override the default.

### Code layout

`app/completion.py` is **kept**: `EchoCompletion` (and `_extract_last_user_text`) is replaced in place by the agent-backed handler class. Same file path so `factory.py` import sites change minimally.

Other new modules under `src/dial_deep_research/app/`:
- `mcp_client.py` — factory for `MultiServerMCPClient` configured with the MCP URL + `api-key` header.
- `llm.py` — `LLMModelConfig`, `LLMModelsEnum`, `get_chat_model`.
- `dial_stages.py` — timed-stage title helpers.
- `factory.py` — re-registers `deep-research` instead of `echo`.

`settings.py` gains: `dial_api_key` on the existing `DialAppSettings` class, plus a new `McpSettings` class (`mcp_url`, `mcp_api_key`). The `LLM_MODELS_*` env reads happen inside `LLMModelsEnum.deployment_id` directly — no settings class for them.

### Testing strategy

Automated coverage is intentionally narrow for MVP; the primary verification gate is manual end-to-end. No integration tests — the request-level wiring (MCP client + agent + DIAL stages + handler) is covered by manual testing only.

**Unit tests** (in `tests/`):
- `LLMModelConfig` — instantiates with defaults; rejects invalid `reasoning_effort`/`verbosity` enum values.
- `LLMModelsEnum.deployment_id` — reads the right `LLM_MODELS_{NAME}` env var; raises clearly when unset.
- `get_chat_model` — points at `dial_settings.dial_url`, uses `dial_settings.dial_api_key` (already a `SecretStr`), threads `reasoning_effort`/`verbosity` through to `AzureChatOpenAI`.
- Timed-stage title formatter — given fixed `(start, end)` `datetime` values, produces the expected title string. Test the formatter as a pure function so we don't have to fake DIAL stages.
- Top-level error funnel — integration-style test boots the real app via `create_app()` + `fastapi.TestClient`, points `MCP_URL` at a port nothing is listening on (set in `conftest.py`), POSTs a chat completion, and asserts the response is HTTP 200, the assistant content carries the friendly fragment, and an `ERROR`-level log was emitted from `dial_deep_research.app.completion` mentioning `deep-research`. Proves no re-raise without needing a `Choice` fake.

**Manual end-to-end** (the verification gate, document in README):
- `make up && make run`, point a real generic-RAG MCP at the app via `.env`, open the DIAL chat UI, ask "what tools are available?". Expected: agent enumerates the MCP server's tools (either by listing them in the response or by demonstrating tool-calling capability). Tool calls and results show up as timed stages in the UI.
- Variant: ask a question that should exercise tool-calling (e.g., search for a document). Verify the result is grounded in tool output.

**What we don't automate:**
- The chat completion handler end-to-end (manual only).
- Anything against a real MCP server.
- LLM behavior quality (no eval harness in this repo).
- DIAL streaming chunk-by-chunk validation (covered by manual UI inspection).

## Risks / Trade-offs

- **Per-request MCP latency** → first-request UX is dominated by handshake + tool-list. Mitigation deferred (tool-list TTL cache).
- **Tool overload at LLM context** → if the MCP server exposes many tools (>30) and each has a verbose JSON schema, the LLM context fills with tool definitions. Mitigation: filter tools at MCP-client load time (deferred).
- **Single error message loses precision** → 401 from MCP, malformed user input, and an actual bug all surface as the same friendly "something went wrong" string. The user can't tell what failed; only logs distinguish. Mitigation: differentiate when error patterns emerge (post-MVP).
- **No cross-turn tool memory** → in a multi-turn conversation, the agent can't reference what it queried last turn. Mitigation: persist tool messages through DIAL `state` when multi-turn quality demands it.
- **GPT-5-only is rigid** → if a deployment lacks GPT-5, the app can't serve. Mitigation: extending `LLMModelsEnum` later is additive.
- **Service-key model means no per-user accounting** → all LLM and MCP traffic spends the deep-research service's quota; we cannot rate-limit or attribute usage by end-user inside this app. Mitigation: rely on DIAL Core's auth + quotas on the chat application as the gate. Adopt per-request user-key flow when per-user accounting becomes a requirement.

## Open Questions

- _(none open — see "System prompt" under Decisions for the resolution of the prior open question on default prompt wording.)_

## Decisions (resolved during implementation)

### System prompt

The agent's hardcoded system prompt (in `completion.py`) ended up longer than the original "2–3 sentences" sketch. Final shape:

1. Identity + tool-use stance: "deep-research assistant for the client, has access to MCP-loaded tools, use them whenever possible to ground answers in retrieved evidence rather than parametric memory."
2. Steer away from `data_retrieval`: its output is typically too large to fit in the context window — prefer `search` for searching documents.
3. Encourage iteration: issue multiple `search` calls with varied queries — different phrasings, synonyms, sub-questions — rather than relying on a single query; iterating on queries based on what earlier results reveal yields the best coverage.
4. Honest-failure clause: if a tool fails or returns nothing relevant, say so plainly.

Why we expanded past the sketch: with only one tool-calling agent and no planning/reflection layer, the prompt is the only knob we have to influence retrieval strategy. The two concrete steers (`search` over `data_retrieval`, and "iterate with varied queries") came directly from observed failure modes against the generic-RAG MCP server during manual verification (12.3 / 12.4). They're load-bearing for answer quality, not stylistic. Future change: revisit if/when we add a planning middleware or replace the prompt with an evaluator-driven loop.
