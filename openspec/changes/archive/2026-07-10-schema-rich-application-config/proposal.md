# Proposal: schema-rich-application-config

## Why

Channel configuration is a local YAML file baked into each deployment (`CHANNEL_CONFIG_PATH`),
so every channel needs its own process, image config, and DIAL Core deployment entry. The
Dockerfile already marks this as temporary. DIAL has a first-class replacement — schema-rich
application types — where per-channel configuration lives in DIAL Core as application
instances, validated against a JSON schema and editable in the DIAL Chat UI.

## What Changes

- Define the DIAL application type "Deep Research": a JSON schema generated from a pydantic
  model, covering what the channel config covers today (research iteration cap, prompt
  content: client name, agent name, data sources descriptions).
- Register a single hardcoded `deep-research` deployment; per-channel identity becomes an
  application instance in Core carrying `applicationProperties`.
- Fetch and validate application properties per request via the aidial-sdk instead of loading
  a YAML file at startup.
- Serve the application type schema from a new schema endpoint
  (`GET /v1/configuration-support/application-schema`) for DIAL Core (>= 0.41.0) and the editor.
- Commit the generated schema and guard it against drift in lint.
- **BREAKING**: remove the YAML channel config mechanism (`ChannelConfig`,
  `CHANNEL_CONFIG_PATH`, `data/configs/*.yaml`). No dual-mode period. `opik_project_name`
  moves from channel config to the `OPIK_PROJECT_NAME` env var.

Out of scope: DIAL Core < 0.41.0 (full-schema registration), editor-support endpoints
(default-configuration, skills), the `configuration` endpoint (conversation starters),
per-instance MCP server settings (MCP stays env-level; natural follow-up change).

## Capabilities

### New Capabilities

- `application-config-schema`: the Deep Research application type — properties model, DIAL
  JSON-schema generation (`dial:meta`, `dial:propertyKind`, `dial:propertyOrder`, root
  `dial:applicationType*` keywords), committed schema artifact with lint drift check, schema
  endpoint, per-request property fetch/validation, and error behavior for missing or invalid
  properties.

### Modified Capabilities

- `dial-agent-with-mcp`: the chat completion registers under the fixed `deep-research`
  deployment id (was: `channel_name` from YAML); prompt content and the iteration cap come
  from per-request application properties (was: startup-loaded channel config).
- `app-config`: `channel_config_path`/`channel` settings are removed; the Opik project name
  becomes the env-driven `OPIK_PROJECT_NAME` setting again. Stale class names in the spec
  (`DialAppSettings`, `OpikSettings`) are corrected to the consolidated `Settings` class.
- `local-stack`: the local Core config gains an `applicationTypeSchemas` entry for the Deep
  Research type plus an example application instance (documented for the untracked
  `dial_conf/core/config.json`).

## Impact

- **Code**: `src/dial_deep_research/channel_config.py` (deleted), `settings.py`,
  `app/factory.py`, `app/completion.py`, `app/preparation/agent.py`, `app/research/nodes.py`,
  `app/research/runner.py`; new properties/schema module and dump script.
- **Config/infra**: Dockerfile (drop baked config), `docker-compose.app.yml` (drop configs
  mount), `data/configs/example.yaml` replaced by an example `applicationProperties` JSON,
  README env-var table and configuration section, CLAUDE.md channel-config rules.
- **Tooling**: `scripts/send_conversation.py` gains a `--deployment` argument;
  `scripts/dump_app_schema.py` added; lint gains a schema drift check.
- **Tests**: `tests/conftest.py`, `tests/test_settings.py` rewritten; new schema-snapshot,
  properties-validation, and completion tests.
- **Dependencies/systems**: DIAL Core >= 0.41.0 required (the local stack already pins a
  compatible version);
  aidial-sdk 0.32.x already supports the property fetch. Existing deployments must have their
  application instance created in Core before upgrading to the new image.
