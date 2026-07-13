# dial-agent-with-mcp (delta)

## ADDED Requirements

### Requirement: Per-request authentication to DIAL Core via header propagation

The app SHALL authenticate all outgoing calls to DIAL Core with the **per-request** `api-key`
that DIAL Core sends on the incoming chat completion request, not a static service key. It
SHALL achieve this by enabling the DIAL SDK's auth-header propagation
(`DIALApp(propagate_auth_headers=True)`, with `dial_url` set), which rewrites the `api-key`
header to the per-request value on every outgoing HTTP request whose URL is under `DIAL_URL` —
covering the LLM calls (`AzureChatOpenAI`), DIAL file operations (`AsyncDial`), and the
Core-hosted MCP endpoint in deployment mode. Clients that require a credential at construction
(`AzureChatOpenAI`, `AsyncDial`) SHALL be built with an obviously-fake placeholder api-key that
the propagator overwrites per request; the app SHALL NOT load or require a static `DIAL_API_KEY`.
The app SHALL NOT forward the request bearer token to the LLM endpoint — LLM authentication is
api-key only.

#### Scenario: Propagation enabled at app construction
- **WHEN** the app is constructed via `create_app()`
- **THEN** the `DIALApp` SHALL be created with auth-header propagation enabled and `dial_url` set

#### Scenario: LLM call carries the per-request key
- **WHEN** the agent invokes the LLM during a chat completion request
- **THEN** the outgoing HTTP request to DIAL Core SHALL carry the incoming request's per-request
  `api-key` as the `api-key` header, not a static service key

#### Scenario: DIAL file operations carry the per-request key
- **WHEN** the app reads user attachments or uploads files to DIAL Core during a request
- **THEN** those requests SHALL carry the incoming request's per-request `api-key`

#### Scenario: No static DIAL key required at startup
- **WHEN** the process starts without any `DIAL_API_KEY` set in the environment
- **THEN** the app SHALL start successfully and SHALL make no use of a static DIAL service key on
  the request path

#### Scenario: Bearer token is not sent to the LLM
- **WHEN** the incoming request carries a bearer token and the agent invokes the LLM
- **THEN** the LLM request SHALL NOT include an `Authorization: Bearer` header (the bearer is
  forwarded only to the RAG MCP, per the **MCP authentication** requirement)

## MODIFIED Requirements

### Requirement: MCP authentication via api-key header

The app SHALL authenticate to the generic-RAG MCP server using per-request credentials, in one
of two mutually exclusive modes (selected by configuration, see **Configuration via environment
variables**):

- **Deployment mode** — the MCP server is a DIAL application reached through DIAL Core. The MCP
  endpoint URL SHALL be `{DIAL_URL}/v1/deployments/{MCP_DEPLOYMENT_NAME}/mcp`. The per-request
  `api-key` SHALL be supplied by DIAL SDK header propagation (the URL is under DIAL Core; see
  **Per-request authentication to DIAL Core via header propagation**), so the app SHALL NOT set a
  static `api-key` header itself. When the incoming request carries a bearer token, the app SHALL
  additionally send `Authorization: Bearer <request bearer token>` on the MCP requests; when the
  request has no bearer token, no `Authorization` header SHALL be added.
- **Local-dev mode** — a directly-reachable external MCP. The app SHALL send the static
  `MCP_API_KEY` value in the `api-key` header on every MCP request (the previous behavior) and
  SHALL NOT add an `Authorization` header.

Transport SHALL remain streamable HTTP and the MCP client SHALL remain per-request (no
cross-request caching), consistent with the **Tool-calling agent over MCP-loaded tools**
requirement.

#### Scenario: Deployment mode sends per-request api-key and forwards the bearer
- **WHEN** the app is in deployment mode and opens an MCP connection for a request that carries a
  bearer token
- **THEN** the MCP endpoint URL SHALL be `{DIAL_URL}/v1/deployments/{MCP_DEPLOYMENT_NAME}/mcp`, the
  outgoing `api-key` header SHALL equal the request's per-request key (via propagation), and an
  `Authorization: Bearer <request bearer token>` header SHALL be present

#### Scenario: Deployment mode without a bearer token
- **WHEN** the app is in deployment mode and the incoming request carries no bearer token
- **THEN** the MCP requests SHALL carry the per-request `api-key` (via propagation) and SHALL NOT
  include an `Authorization` header

#### Scenario: Local-dev mode sends the configured static key
- **WHEN** the app is in local-dev mode and opens an MCP connection to load tools or invoke a tool
- **THEN** the request SHALL target `MCP_URL`, include the header `api-key: <MCP_API_KEY value>`,
  and SHALL NOT include an `Authorization` header

### Requirement: Configuration via environment variables

The app SHALL be configurable through environment variables documented in `.env.example` and the
README environment-variables table. The app SHALL NOT require a channel-config file path
(`CHANNEL_CONFIG_PATH` is removed); per-channel behavior comes from DIAL application properties
(see the **application-config-schema** capability).

The MCP connection SHALL be configured in exactly one of two mutually exclusive modes, enforced
at process startup by a settings validator:

- **Deployment mode**: `MCP_DEPLOYMENT_NAME` names the DIAL application/deployment id of the
  generic-RAG MCP server, reached through DIAL Core (see **MCP authentication via api-key
  header**). `MCP_URL` and `MCP_API_KEY` are not used.
- **Local-dev mode**: `MCP_URL` gives a directly-reachable MCP endpoint and `MCP_API_KEY` its
  static key. When `MCP_URL` is set the app SHALL use local-dev mode and SHALL require
  `MCP_API_KEY`.

`MCP_SERVER_NAME` SHALL remain required as the logical connection name in both modes. A
configuration that resolves to neither mode (no `MCP_URL` and no `MCP_DEPLOYMENT_NAME`), or that
sets `MCP_URL` without `MCP_API_KEY`, SHALL cause the app to exit non-zero at startup with a
message naming the problem.

The app SHALL NOT read a `DIAL_API_KEY` environment variable; downstream DIAL Core calls
authenticate with the per-request api-key (see **Per-request authentication to DIAL Core via
header propagation**).

`LLM_MODELS_<NAME>` env mappings SHALL be supported as overrides for the per-enum-member DIAL
Core deployment id; if unset, the app SHALL fall back to the enum member's value (the model id).

#### Scenario: Deployment-mode startup
- **WHEN** the process starts with `MCP_SERVER_NAME` and `MCP_DEPLOYMENT_NAME` set and no `MCP_URL`
- **THEN** the app SHALL start successfully in deployment mode and register the `deep-research`
  deployment

#### Scenario: Local-dev-mode startup
- **WHEN** the process starts with `MCP_SERVER_NAME`, `MCP_URL`, and `MCP_API_KEY` set
- **THEN** the app SHALL start successfully in local-dev mode

#### Scenario: Local-dev mode missing the static key
- **WHEN** the process starts with `MCP_URL` set but `MCP_API_KEY` unset
- **THEN** the app SHALL exit non-zero before serving any request, with a message naming
  `MCP_API_KEY`

#### Scenario: Neither MCP mode configured
- **WHEN** the process starts with neither `MCP_URL` nor `MCP_DEPLOYMENT_NAME` set
- **THEN** the app SHALL exit non-zero before serving any request, with a message indicating no
  MCP connection is configured

#### Scenario: Startup without a channel config file
- **WHEN** the process starts with a valid MCP mode configured and no `CHANNEL_CONFIG_PATH` in the
  environment
- **THEN** the app SHALL start successfully and register the `deep-research` deployment without
  reading any local config file

#### Scenario: DIAL_API_KEY is not consulted
- **WHEN** the process starts with no `DIAL_API_KEY` set (or with one set)
- **THEN** the app SHALL start successfully and SHALL NOT use it — downstream DIAL Core auth comes
  from the per-request api-key

#### Scenario: LLM_MODELS override resolves at request time
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is set in the environment
  for the configured model
- **THEN** the agent SHALL use that value as the DIAL Core `azure_deployment` id

#### Scenario: LLM_MODELS unset falls back to enum value
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is **not** set
- **THEN** the agent SHALL use the enum member's `.value` (the model id, e.g. `gpt-5.2-2025-12-11`)
  as the DIAL Core deployment id without raising

## REMOVED Requirements

### Requirement: LLM access via DIAL Core with static service key

**Reason**: The app must authenticate to DIAL Core (LLM and file operations) with the per-request
api-key so per-user attribution, quota, and file access work correctly; a single static service
key breaks all three. This requirement — which mandated a static `DIAL_API_KEY` and forbade
forwarding per-request keys — is reversed by this change.

**Migration**: Superseded by the **Per-request authentication to DIAL Core via header
propagation** requirement. Remove `DIAL_API_KEY` from deployment configuration; the per-request
api-key is used automatically via SDK header propagation.
