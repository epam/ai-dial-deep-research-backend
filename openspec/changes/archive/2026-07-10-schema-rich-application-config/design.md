# Design: schema-rich-application-config

## Context

Today one process serves one channel: a YAML file selected by `CHANNEL_CONFIG_PATH` is loaded
into the `Settings` singleton at import time (`settings.py`), and its `channel_name` becomes
the DIAL deployment id registered in `app/factory.py`. Prompt content, the research iteration
cap, and the Opik project name all come from that file. The Dockerfile marks this as temporary.

DIAL supports schema-rich application types: a JSON schema (conforming to the DIAL
application-type meta-schema) describes the configuration; DIAL Core stores application
instances (`applicationTypeSchemaId` + `applicationProperties`) and routes them to a single
generic deployment on the backend; the backend fetches and validates the instance's properties
per request. The reference implementation is the Quick Apps 2.0 backend
(`epam/ai-dial-quickapps-backend`).

Verified constraints:

- The pinned aidial-sdk 0.32.x ships `request_dial_application_properties()`.
- The local stack already pins a Core >= 0.41.0, has `includeCustomApps: true` in
  `dial_conf/settings/settings.json`, and enables the `custom-applications`/`quick-apps` chat
  feature flags.

## Goals / Non-Goals

**Goals:**

- One backend process serves any number of channels; each channel is an application instance
  in Core, editable via the DIAL Chat editor.
- The application type schema is generated from a pydantic model, committed, drift-checked in
  lint, and served live from a schema endpoint.
- Per-request configuration is fetched from Core and validated; failures produce a clear,
  friendly error.
- Remove the YAML channel config mechanism completely.

**Non-Goals:**

- DIAL Core < 0.41.0 support (full-schema registration in Core config).
- Editor-support endpoints (`default-configuration`, skills list/validate) and the
  `configuration` endpoint (conversation starters).
- Per-instance MCP server settings — MCP stays env-level; all instances served by one process
  share one MCP server. Natural follow-up change.
- Per-instance Opik projects — the project name moves to the `OPIK_PROJECT_NAME` env var.

## Decisions

1. **Schema registration: endpoint mode only.** Core (>= 0.41.0) fetches the property schema
   from the backend's schema endpoint; the `applicationTypeSchemas` entry in Core config
   carries only the `dial:applicationType*` endpoints and display metadata. Alternative
   (pasting the full generated schema into Core config) supports older Core but duplicates the
   schema and drifts; explicitly out of scope.
2. **Hardcoded deployment id `deep-research`.** Mirrors quickapps (`quick_apps2`). Alternative
   (reuse `settings.dial_app_name`) conflates the OTel service name with the routing contract;
   `dial_app_name` stays OTel-only.
3. **Properties via SDK REST fetch, not header.** `dial:appendApplicationPropertiesHeader:
   false`, so Core sends `X-DIAL-APPLICATION-ID` and the SDK fetches
   `GET /openai/applications/{id}` — authoritative and not spoofable by direct callers. The
   SDK still honors an explicit `X-DIAL-APPLICATION-PROPERTIES` header when present, which the
   test suite uses to inject properties without a Core round-trip.
4. **Missing or invalid properties fail the request** with a friendly error message (same
   pattern as the existing catch-all in `DeepResearchCompletion.chat_completion`). Prompt
   fields are required, so a request to the bare deployment without an application instance
   cannot run with defaults.
5. **Schema `$id` is a generic placeholder** ending in
   `/custom_application_schemas/deep-research`; the repo is public, so no real host appears in
   committed content. Display name: `dial:applicationTypeDisplayName: "Deep Research"`.
6. **Slim schema-generation base, not a copy of quickapps.** A small `model_json_schema()`
   override on the properties model: flatten `$defs` for root properties, inject per-property
   `dial:meta` (`dial:propertyKind: "server"`, auto `dial:propertyOrder`), and optionally wrap
   with root `$id`/`$schema`/display-name keywords (`include_dial_fields` flag; the schema
   endpoint serves the un-wrapped form because Core supplies the wrapper from its
   `applicationTypeSchemas` entry). Quickapps' full base class (~500 lines) covers legacy
   aliases, preview gating, `dial:file`/`dial:resource` — none needed for v1's plain
   strings/int.
7. **Properties model replaces `ChannelConfig`** (new module, e.g.
   `src/dial_deep_research/app_properties.py`): `max_research_iterations` (int, default 10,
   ge=1) and nested `prompts` object (`client_name`, `agent_name`,
   `data_sources_descriptions`; required, min_length=1). `channel_name` is dropped (identity
   comes from the Core instance); `opik_project_name` is dropped (moves to env).
8. **Properties are threaded as parameters, not a singleton.** `_run_turn` validates the
   fetched properties and passes them into `PrepAgentRunner.run(...)` and
   `ResearchRunner.run(...)`; `settings.channel` consumers (`app/preparation/agent.py`,
   `app/research/nodes.py`, `app/research/runner.py`) take the values as arguments. Keeping a
   module-level singleton would be wrong once properties vary per request.
9. **Hard cutover.** The YAML mechanism is deleted in the same change; no dual-mode period.
   The repo is at version 0.0.0. Already-running deployments keep working on their old image;
   upgrading an environment requires creating its application instance in Core first.

## Risks / Trade-offs

- [Per-request Core round-trip for properties] → negligible next to a research run; the
  friendly-error path covers Core being unreachable.
- [Shared process state: MCP server and Opik project are env-level while instances vary] →
  accepted and explicit for v1; per-instance MCP is the follow-up change.
- [Schema drift between model and committed artifact] → `scripts/dump_app_schema.py --check`
  wired into lint fails CI until regenerated.
- [Environments on Core < 0.41.0 cannot register the type] → out of scope by decision;
  documented as a hard prerequisite.
- [`data/configs/example.yaml` disappears while CLAUDE.md and docs reference it] → docs,
  CLAUDE.md rules, and the example artifact are updated in the same change.

## Migration Plan

1. Land the change (code + docs + example core-config snippet).
2. For each environment: ensure Core >= 0.41.0, add the `applicationTypeSchemas` entry
   pointing at the backend, create the application instance with the channel's properties,
   then roll out the new image.
3. Rollback: redeploy the previous image with its YAML config; Core-side entries are additive
   and harmless to leave in place.

## Open Questions

None — all decisions above are resolved (see `tmp/schema-rich-application-plan.md` for the
full exploration notes behind them).
