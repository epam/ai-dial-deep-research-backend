# Tasks

## 1. Dependencies and packaging

- [x] 1.1 Add `langchain`, `langchain-mcp-adapters`, `langchain-openai` to `pyproject.toml` runtime dependencies; regenerate `uv.lock` via `uv sync`.
- [x] 1.2 Run `make lint` to confirm dependency additions don't break existing checks.

## 2. Settings layer

- [x] 2.1 Extend `DialAppSettings` in `src/dial_deep_research/settings.py` with `dial_api_key: SecretStr = SecretStr("dial_api_key")` — default matches the dev key registered in `dial_conf/core/config.json`; no `alias=` (pydantic-settings's default case-insensitive field-name → env-var matching reads `DIAL_API_KEY`). Existing aliased fields stay aliased.
- [x] 2.2 Flip `dial_app_name` default in `DialAppSettings` from `"Echo"` to `"deep-research"` so OTel service name defaults match the deployment id.
- [x] 2.3 Add a new `McpSettings(BaseSettings)` class in `src/dial_deep_research/settings.py` with `mcp_url: str` and `mcp_api_key: SecretStr`. No aliases — pydantic-settings reads `MCP_URL` and `MCP_API_KEY` from the field names directly.
- [x] 2.4 Update `.env.example` to clarify the dual use of `DIAL_API_KEY` and add `MCP_URL=` / `MCP_API_KEY=`; remove or rename any echo-app comments. `LLM_MODELS_<NAME>` is optional (default falls back to the enum's `.value`), so it stays out of `.env.example`.

## 3. LLM module

- [x] 3.1 Create `src/dial_deep_research/app/llm.py` with `LLMModelsEnum` whose `deployment_id` property reads `os.getenv(f"LLM_MODELS_{member.name}", self.value)` — env var as optional override, fallback to the enum's `.value`.
- [x] 3.2 In the same module, add `LLMModelConfig(BaseModel)` with field-level defaults: `deployment: LLMModelsEnum`, `reasoning_effort: ReasoningEffortEnum | None = None`, `verbosity: VerbosityEnum | None = None`. Define the two enums in the same file. Pin the Azure OpenAI API version as a module-level `_API_VERSION` constant rather than a config field — we have no use case for varying it per call site, and surfacing it on the config makes it look more configurable than it actually is (see design.md).
- [x] 3.3 Add `get_chat_model(model_config: LLMModelConfig) -> AzureChatOpenAI` reading `dial_settings.dial_url` + `dial_settings.dial_api_key` internally; the factory takes no key parameter.

## 4. MCP client module

- [x] 4.1 Create `src/dial_deep_research/app/mcp_client.py` exposing a factory that constructs a `MultiServerMCPClient` configured with the single MCP server at `mcp_settings.mcp_url`, transport `"streamable_http"`, and `headers={"api-key": mcp_settings.mcp_api_key.get_secret_value()}`.

## 5. Stage helpers module

- [x] 5.1 Create `src/dial_deep_research/app/dial_stages.py` exposing **pure title-formatter helpers only** (`timed_stage_title`, `result_stage_title(tool_name, start, end, is_error=...)`). No stage context managers — the completion handler opens stages directly via `with self._choice.create_stage(title): ...` and feeds it a pre-formatted title. Rationale: for this MVP we open the stage at the moment the result arrives (driven by `agent.astream(stream_mode="updates")`), so we don't need a context-manager that wraps "open at start → close at end". A future change that opens the stage when tool execution begins (likely via `astream_events`) will revisit this and introduce a context-manager helper shape.
- [x] 5.2 Title format: `[TOOL] "<tool_name>" - <action> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)` where action/emoji is `result ✅` for success or `error ❌` for failures. One stage per tool invocation; stage body is markdown with an **Input** section (JSON-fenced args) and an **Output**/**Error** section.

## 6. Completion handler

- [x] 6.1 In `src/dial_deep_research/app/completion.py`, replace `EchoCompletion`, `_ECHO_PREFIX`, and `_extract_last_user_text` with a new agent-backed handler class (e.g. `DeepResearchCompletion`). Keep the file path; `factory.py` import sites change minimally.
- [x] 6.2 In the new handler's `chat_completion(self, request, response)`, construct a fresh `MultiServerMCPClient` and a LangChain tool-calling agent per request; load tools via `await client.get_tools()`; do not cache.
- [x] 6.3 Hardcode a system prompt that (a) tells the agent it has access to MCP-loaded tools and should ground answers in retrieved evidence, (b) steers it toward `search` over `data_retrieval` (whose output is too large to fit context), and (c) encourages multiple `search` calls with varied phrasings/synonyms/sub-questions so coverage compounds across iterations. Author it inline.
- [x] 6.4 Stream the agent: route assistant text chunks (`AIMessage` content deltas) through `choice.append_content(...)`. Do not write tool calls or tool results to choice content.
- [x] 6.5 For each tool call: emit a single result stage when the tool result arrives, carrying the JSON-fenced **Input** args and a fenced **Output** (or **Error**) section. Use the helpers from step 5.
- [x] 6.6 Ensure no DIAL `state` round-tripping for tool messages (no `dump_state` / `load_state`); LangChain history is per-request only.
- [x] 6.7 Wrap the entire handler body in a top-level `try/except` (with bare `Exception`). On any failure: log the exception (class + message + traceback) at `ERROR`; call `choice.append_content(...)` with a fixed friendly string (e.g. `"\n\nSorry, something went wrong while processing your request. The error has been logged."`); return normally — do **not** re-raise.

## 7. Factory and module wiring

- [x] 7.1 Update `src/dial_deep_research/app/factory.py`: replace the `EchoCompletion` import with the new completion class; change `add_chat_completion("echo", EchoCompletion(), ...)` to `add_chat_completion("deep-research", DeepResearchCompletion(...), ...)`.
- [x] 7.2 Pass any required dependencies (e.g. `dial_settings`, `mcp_settings`, `llm_model_config`) to the completion class constructor; keep wiring minimal — no DI framework.
- [x] 7.3 Verify `dial_app_settings.dial_app_name` (now defaulting to `"deep-research"`) is what flows into `TelemetryConfig.service_name`.

## 8. DIAL core config

- [x] 8.1 Update `dial_conf/core/config.json`: rename the `applications.echo` block to `applications.deep-research`. Set `displayName` to `"Deep Research"`. Update `description` and `descriptionKeywords` to reflect the new agent (replace echo wording).
- [x] 8.2 Update the `endpoint` field to `http://host.docker.internal:5000/openai/deployments/deep-research/chat/completions`.
- [x] 8.3 Update `roles.default.limits` to key on `deep-research` instead of `echo` (preserve any existing limit values).
- [x] 8.4 Register a GPT-5 model entry in `dial_conf/core/config.json` `models.<model>.endpoint` pointing at the in-cluster adapter (`http://ai-dial-adapter-dial:5000/openai/deployments/<model>/chat/completions`) with the upstream LLM provider configured in `upstreams`.
- [x] 8.5 Add `ai-dial-adapter-dial` (image `epam/ai-dial-adapter-dial:0.6.0`) to `docker-compose.yml`, env `DIAL_URL=http://core:8080`, no host port published.

## 9. README and docs

- [x] 9.1 Replace the README intro/first-run example: drop the "send `hello`, get `echo: hello`" wording; add a short walk-through that selects `Deep Research` in the chat UI and demonstrates a real tool-calling turn against the configured MCP server.
- [x] 9.2 Update the project tree comment in README that mentions `EchoCompletion(ChatCompletion)` / `registers the echo application` to point at the new completion class and `deep-research` deployment.
- [x] 9.3 Add a short subsection documenting the env vars: required (`DIAL_API_KEY`, `MCP_URL`, `MCP_API_KEY`) and the optional `LLM_MODELS_<NAME>` override.
- [x] 9.4 Document the manual-verification gate (no automated end-to-end): step-by-step instructions to run `make up && make run` and exercise tool-calling in the chat UI.

## 10. Unit tests

- [x] 10.1 Delete `tests/test_echo.py` (echo behavior no longer exists).
- [x] 10.2 Add a unit test for `LLMModelConfig`: defaults instantiate; passing an invalid `reasoning_effort` / `verbosity` enum string raises `ValidationError`. Per project guidance, do **not** add a test that only asserts a default value loads.
- [x] 10.3 Add a unit test for `LLMModelsEnum.deployment_id`: with `LLM_MODELS_<NAME>` set, the property returns the env value; with the env var unset, the property returns the enum member's `.value` (no raise).
- [x] 10.4 Add a unit test for `get_chat_model`: given a known `LLMModelConfig`, the returned `AzureChatOpenAI` instance has `azure_endpoint == dial_settings.dial_url`, the configured `api_version`, and `reasoning_effort` / `verbosity` threaded through. Use a simple settings stub rather than mocking the SDK.
- [x] 10.5 Add unit tests for the timed-stage title formatters (result-success, result-error): given fixed `start`/`end` `datetime` values, each returns the expected string in the normalized `[TOOL] "<tool_name>" - <action> <emoji> (...)` form. Test the formatters as pure functions — no DIAL stage fakes.
- [x] 10.6 Add an integration-style test for the top-level error funnel: boot the real app via `create_app()` + `fastapi.TestClient`, point `MCP_URL` at a port nothing is listening on (set in `conftest.py`), POST a chat completion, and assert (a) the response is HTTP 200, (b) the assistant content contains the friendly error fragment, (c) at least one `ERROR`-level log record was emitted by `dial_deep_research.app.completion` mentioning `deep-research`. This proves the handler does not re-raise without needing a `Choice` fake.

## 11. Spec maintenance

- [x] 11.1 Verify the five spec deltas in this change (`deep-research`, `echo-app`, `local-stack`, `dev-environment`, `app-config`) align with the implementation; adjust any wording drifts caught during code review.
- [x] 11.2 Run `openspec validate add-deep-research --strict` after any spec edits.

## 12. Cleanup and verification

- [x] 12.1 Grep the repo for residual references to `echo`, `EchoCompletion`, `_ECHO_PREFIX`, `_extract_last_user_text` outside `openspec/changes/archive/` (which is intentionally frozen). Remove or rename each occurrence.
- [x] 12.2 Run `make format`, `make lint`, `make test_unit` — expect all green.
- [x] 12.3 Manual end-to-end: with a real generic-RAG MCP server reachable, `make up && make run`, open the chat UI, select `Deep Research`, ask "what tools are available?". Verify the agent enumerates / calls MCP tools and tool stages render with start/end timestamps in the UI.
- [x] 12.4 Manual error-path check: stop the MCP server, send a chat message, verify the response ends with the friendly error string and the server log carries the full traceback.
