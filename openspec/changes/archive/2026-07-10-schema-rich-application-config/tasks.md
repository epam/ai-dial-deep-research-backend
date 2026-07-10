# Tasks: schema-rich-application-config

## 1. Properties model and schema generation

- [x] 1.1 Create `ApplicationProperties` + nested `Prompts` pydantic models (new module,
      e.g. `src/dial_deep_research/app_properties.py`): `max_research_iterations` (int,
      default 10, ge=1) and required non-empty prompt strings
- [x] 1.2 Add the slim schema-generation override: flatten root `$defs`, inject per-property
      `dial:meta` (`dial:propertyKind: "server"`, sequential `dial:propertyOrder`), and an
      `include_dial_fields` toggle adding root `$id`/`$schema`/
      `dial:applicationTypeDisplayName: "Deep Research"`/
      `dial:appendApplicationPropertiesHeader: false`
- [x] 1.3 Add `scripts/dump_app_schema.py` (write + `--check` modes) and commit the generated
      `docs/generated-app-schema.json`
- [x] 1.4 Wire the `--check` mode into the lint gate (Makefile / pyproject equivalent)
- [x] 1.5 Tests: properties validation (defaults, empty-string rejection) and a
      schema-generation test covering `dial:meta` blocks and the `include_dial_fields` toggle

## 2. Per-request properties in the app

- [x] 2.1 Register the completion under the hardcoded `deep-research` deployment id in
      `app/factory.py`; keep `dial_app_name` OTel-only
- [x] 2.2 Move the Opik project name to `Settings.opik_project_name`
      (env `OPIK_PROJECT_NAME`, default `deep-research`) and use it in `configure_opik`
- [x] 2.3 In `DeepResearchCompletion._run_turn`, resolve properties via
      `await request.request_dial_application_properties()` and validate into
      `ApplicationProperties`; on missing/unfetchable/invalid properties, log and emit the
      friendly configuration error (HTTP 200), running no agents
- [x] 2.4 Thread properties as parameters: `PrepAgentRunner` (agent_name,
      data_sources_descriptions), `ResearchRunner`/graph (max_research_iterations),
      researcher prompt (client_name); delete all `settings.channel` reads
- [x] 2.5 Add the schema endpoint `GET /v1/configuration-support/application-schema`
      (un-wrapped schema) as a FastAPI route on the `DIALApp`
- [x] 2.6 Delete `channel_config.py` and the `channel_config_path`/`channel` fields plus the
      loader validator from `settings.py`
- [x] 2.7 Tests: completion turn with properties injected via the
      `X-DIAL-APPLICATION-PROPERTIES` header; friendly error on missing and on invalid
      properties; schema endpoint response; rewrite `tests/test_settings.py` and
      `tests/conftest.py` (drop `CHANNEL_CONFIG_PATH`)

## 3. Local stack and packaging

- [x] 3.1 Replace `data/configs/example.yaml` with an example `applicationProperties` JSON
      artifact kept in sync with the schema; update `data/.gitignore` accordingly
- [x] 3.2 Remove the baked example config and `CHANNEL_CONFIG_PATH` default from the
      Dockerfile; drop the configs mount from `docker-compose.app.yml`
- [x] 3.3 Add generic README snippets for the untracked `dial_conf/core/config.json`: the
      `applicationTypeSchemas` entry (completion + schema endpoints, display name, header
      flag) and an example instance with `applicationTypeSchemaId` + `applicationProperties`
- [x] 3.4 Update the local `dial_conf/core/config.json` (untracked) and verify end-to-end:
      `make up`, `make app`, instance visible in chat UI, turn runs with instance properties

## 4. Tooling and docs

- [x] 4.1 `scripts/send_conversation.py`: add a `--deployment` argument (env fallback) for
      the target application instance; stop importing the channel config
- [x] 4.2 README: rewrite the Configuration section (application properties instead of
      channel YAML) and the env-var table (drop `CHANNEL_CONFIG_PATH`, add
      `OPIK_PROJECT_NAME`); state the DIAL Core >= 0.41.0 prerequisite
- [x] 4.3 CLAUDE.md: replace the channel-config rules with schema-era equivalents (keep
      `docs/generated-app-schema.json` and the example properties in sync with the model)
- [x] 4.4 Run `make format` and `make lint`; full test suite green
