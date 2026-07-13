## ADDED Requirements

### Requirement: DIAL-protocol application server
The repository SHALL implement an application server that conforms to the DIAL application protocol, using the official DIAL Python SDK, exposing a chat completion endpoint consumable by DIAL core under the deployment id `deep-research`.

#### Scenario: Request accepted from DIAL core
- **WHEN** DIAL core forwards a chat completion request to the app with a well-formed DIAL envelope
- **THEN** the app SHALL accept the request and respond with a well-formed DIAL chat completion response

#### Scenario: Rejects malformed requests
- **WHEN** the app receives a request that does not conform to the DIAL application protocol
- **THEN** it SHALL respond with an appropriate HTTP 4xx error surfaced via the SDK, without crashing the server process

### Requirement: Streaming response path
The app SHALL produce its assistant response through the SDK's streaming API so that the streaming code path is exercised end-to-end.

#### Scenario: Streamed delivery
- **WHEN** DIAL core requests a streaming chat completion
- **THEN** the app SHALL emit the assistant content via one or more streaming chunks terminated by an end-of-stream signal, conforming to the SDK's streaming contract

### Requirement: Health endpoint
The app SHALL expose a lightweight health check endpoint that returns success when the process is able to serve requests.

#### Scenario: Health probe
- **WHEN** a client (or Docker healthcheck) issues a GET to the health endpoint
- **THEN** the app SHALL respond with HTTP 200 and a minimal body indicating healthy status

### Requirement: Tool-calling agent over MCP-loaded tools
On each chat completion request the app SHALL construct a fresh LangChain tool-calling agent and run it to completion against the tools loaded from a single HTTP MCP server. The agent SHALL have access only to MCP-loaded tools — no built-in tools, planning middleware, subagents, skills, or persistent memory.

#### Scenario: Agent invokes an MCP tool
- **WHEN** the user message is best answered by calling an MCP-exposed tool
- **THEN** the agent SHALL emit a tool call, the MCP server SHALL execute the tool, and the agent SHALL incorporate the result into its final assistant message

#### Scenario: Agent answers without tool calls
- **WHEN** the user message can be answered from the agent's prior context without an MCP tool call
- **THEN** the agent SHALL produce a final assistant message containing only natural-language text and the response SHALL emit no tool stages

#### Scenario: Per-request agent and MCP scoping
- **WHEN** the MCP server's tool list changes between two chat completion requests (e.g. the generic-RAG MCP server is redeployed)
- **THEN** the second request SHALL discover and use the new tool list without restarting the dial-deep-research process

### Requirement: Tool execution surfaced as timed DIAL stages
For every tool the agent invokes during a request, the app SHALL emit a single DIAL "result" stage carrying both the input arguments and the tool's output. Titles follow the normalized form `[TOOL] "<tool_name>" - <action> <emoji> (<elapsed>s, start: HH:MM:SS, end: HH:MM:SS)`, where action ∈ `{result, error}` and emoji ∈ `{✅, ❌}` respectively. Stage timestamps SHALL bracket the actual execution window (start when the call is dispatched to the MCP server, end when the result is received). When the tool returns an error (caught by `handle_tool_error` instead of bubbling), the stage SHALL use the `error ❌` action variant so the failure stands out in the chat UI. Stage content is rendered as markdown by DIAL, so both the input arguments and the tool output SHALL be wrapped in fenced code blocks (single newlines would otherwise collapse), making multi-line payloads — JSON args, plain-text results, error tracebacks — readable verbatim.

#### Scenario: Tool result stage carries start, end, elapsed, input, and output
- **WHEN** the tool result returns from the MCP server
- **THEN** the app SHALL emit a stage whose title includes the start timestamp, end timestamp, and elapsed seconds, and whose body contains an "Input" section with the JSON-fenced arguments followed by an "Output" section with the fenced tool result content

#### Scenario: Tool error stage signals failure but does not abort the turn
- **WHEN** an MCP tool raises (e.g. argument validation rejects the LLM's call) and the error is caught by the per-tool error handler
- **THEN** the app SHALL emit a stage whose title uses the `error ❌` variant (e.g. `[TOOL] "<tool_name>" - error ❌ (...)`), whose body carries the JSON-fenced "Input" section followed by a fenced "Error" section with the error text; the agent SHALL receive the same error text as a `ToolMessage` in its next step and MAY retry with corrected arguments without the chat completion failing

### Requirement: Assistant message content contains only model text
The DIAL response message content SHALL contain only the agent's natural-language assistant text. Tool calls, tool results, and intermediate agent messages SHALL be conveyed only via stages and SHALL NOT appear in the assistant message content.

#### Scenario: Tool-using turn
- **WHEN** the agent makes one or more tool calls before producing its final answer
- **THEN** the DIAL response content SHALL contain only the final assistant text and SHALL NOT contain serialized tool calls, tool results, or intermediate agent reasoning

#### Scenario: Cross-turn isolation of tool messages
- **WHEN** a follow-up chat completion request arrives after an earlier tool-using turn
- **THEN** the second turn's agent SHALL receive only the assistant text from prior turns as conversation history (no prior tool calls or tool results), since DIAL only stores assistant text and the agent is reconstructed per request

### Requirement: Top-level error funnel with friendly assistant message
The app SHALL wrap each chat completion in a top-level exception handler. On any failure (MCP unreachable, MCP tool error, LLM error, malformed model output, etc.), the handler SHALL log the exception server-side and append a fixed friendly error string to the assistant message via `choice.append_content`. The handler SHALL NOT re-raise the exception; the chat completion SHALL complete successfully from DIAL's perspective.

#### Scenario: MCP server unreachable
- **WHEN** the MCP server cannot be reached at the configured URL during a chat completion
- **THEN** the app SHALL log the failure server-side and the DIAL response SHALL contain a friendly error string as the assistant message, completing successfully (HTTP 200) from DIAL's perspective

#### Scenario: LLM error mid-turn
- **WHEN** the LLM call fails after one or more tool stages have already been streamed
- **THEN** the app SHALL log the failure server-side and append the friendly error string to the existing partial assistant content, completing successfully from DIAL's perspective

#### Scenario: MCP tool execution error
- **WHEN** an MCP tool raises an error during execution
- **THEN** the app SHALL log the failure server-side and the DIAL response SHALL end with the friendly error string as part of the assistant message, completing successfully from DIAL's perspective

### Requirement: MCP authentication via api-key header
The app SHALL authenticate to the MCP server by sending the configured MCP API key in the `api-key` HTTP header on every request to the MCP server.

#### Scenario: Configured key sent on connect
- **WHEN** the app opens an HTTP MCP connection to load tools or invoke a tool
- **THEN** the request SHALL include the header `api-key: <MCP_API_KEY value>`

### Requirement: LLM access via DIAL Core with static service key
The app SHALL invoke its LLM through DIAL Core, authenticating with a static `DIAL_API_KEY` value loaded from environment configuration. The app SHALL NOT forward per-request user API keys (e.g. `request.api_key`) to the LLM call.

#### Scenario: LLM call uses service key
- **WHEN** the agent invokes the LLM
- **THEN** the underlying HTTP request to DIAL Core SHALL carry the configured `DIAL_API_KEY` value as authentication, regardless of any API key value present on the incoming DIAL chat completion request

### Requirement: Configuration via environment variables
The app SHALL be configurable through environment variables documented in `.env.example` and `envvars.md`. The MCP server URL and the MCP API key SHALL be required at process startup. The DIAL API key SHALL be optional with a default of `dial_api_key` (matching the dev key registered in `dial_conf/core/config.json`); deployments shipping a real key SHALL override it via `DIAL_API_KEY`. `LLM_MODELS_<NAME>` env mappings SHALL be supported as overrides for the per-enum-member DIAL Core deployment id; if unset, the app SHALL fall back to the enum member's value (the model id).

#### Scenario: Missing startup-required variable
- **WHEN** the process starts without one of `MCP_URL` or `MCP_API_KEY`
- **THEN** the app SHALL exit non-zero before serving any request, with a log/error message that names the missing variable

#### Scenario: DIAL_API_KEY default
- **WHEN** the process starts without `DIAL_API_KEY` set in the environment
- **THEN** `dial_app_settings.dial_api_key` SHALL resolve to the `dial_api_key` default and the app SHALL start successfully

#### Scenario: LLM_MODELS override resolves at request time
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is set in the environment for the configured model
- **THEN** the agent SHALL use that value as the DIAL Core `azure_deployment` id

#### Scenario: LLM_MODELS unset falls back to enum value
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is **not** set
- **THEN** the agent SHALL use the enum member's `.value` (the model id, e.g. `gpt-5.2-2025-12-11`) as the DIAL Core deployment id without raising
