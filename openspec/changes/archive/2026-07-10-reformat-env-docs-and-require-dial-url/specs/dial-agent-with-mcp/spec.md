## MODIFIED Requirements

### Requirement: Configuration via environment variables

The app SHALL be configurable through environment variables documented in `.env.example` and the
README environment-variables table. The README environment-variables table SHALL present every
variable in a single table listing its default and its required status. The app SHALL NOT require
a channel-config file path (`CHANNEL_CONFIG_PATH` is removed); per-channel behavior comes from
DIAL application properties (see the **application-config-schema** capability).

`DIAL_URL` SHALL be a required environment variable with no built-in default: the app SHALL NOT
carry a fallback DIAL Core URL, and SHALL exit non-zero at startup with a message naming
`DIAL_URL` when it is unset. `.env.example` SHALL document `DIAL_URL` with the local-dev value
`http://localhost:8080`, so the code carries no localhost default while the local dev loop still
works.

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

#### Scenario: Startup with DIAL_URL set
- **WHEN** the process starts with a valid MCP mode configured and `DIAL_URL` set
- **THEN** the app SHALL start successfully and use `DIAL_URL` as the DIAL Core base URL

#### Scenario: Missing DIAL_URL fails fast
- **WHEN** the process starts with a valid MCP mode configured but no `DIAL_URL` set
- **THEN** the app SHALL exit non-zero before serving any request, with a message naming
  `DIAL_URL`, and SHALL NOT fall back to any built-in URL

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
