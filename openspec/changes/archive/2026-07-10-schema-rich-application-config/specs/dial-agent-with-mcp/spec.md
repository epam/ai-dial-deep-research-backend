# dial-agent-with-mcp (delta)

## MODIFIED Requirements

### Requirement: Configuration via environment variables
The app SHALL be configurable through environment variables documented in `.env.example` and the README environment-variables table. The MCP server URL and the MCP API key SHALL be required at process startup. The app SHALL NOT require a channel-config file path (`CHANNEL_CONFIG_PATH` is removed); per-channel behavior comes from DIAL application properties (see the **application-config-schema** capability). The DIAL API key SHALL be optional with a default of `dial_api_key` (matching the dev key registered in `dial_conf/core/config.json`); deployments shipping a real key SHALL override it via `DIAL_API_KEY`. `LLM_MODELS_<NAME>` env mappings SHALL be supported as overrides for the per-enum-member DIAL Core deployment id; if unset, the app SHALL fall back to the enum member's value (the model id).

#### Scenario: Missing startup-required variable
- **WHEN** the process starts without one of `MCP_URL` or `MCP_API_KEY`
- **THEN** the app SHALL exit non-zero before serving any request, with a log/error message that names the missing variable

#### Scenario: Startup without a channel config file
- **WHEN** the process starts with the required MCP variables set and no `CHANNEL_CONFIG_PATH` in the environment
- **THEN** the app SHALL start successfully and register the `deep-research` deployment without reading any local config file

#### Scenario: DIAL_API_KEY default
- **WHEN** the process starts without `DIAL_API_KEY` set in the environment
- **THEN** `settings.dial_api_key` SHALL resolve to the `dial_api_key` default and the app SHALL start successfully

#### Scenario: LLM_MODELS override resolves at request time
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is set in the environment for the configured model
- **THEN** the agent SHALL use that value as the DIAL Core `azure_deployment` id

#### Scenario: LLM_MODELS unset falls back to enum value
- **WHEN** a chat completion request is processed and `LLM_MODELS_<NAME>` is **not** set
- **THEN** the agent SHALL use the enum member's `.value` (the model id, e.g. `gpt-5.2-2025-12-11`) as the DIAL Core deployment id without raising
