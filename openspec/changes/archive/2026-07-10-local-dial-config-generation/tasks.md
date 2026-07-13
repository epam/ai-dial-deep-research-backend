# Tasks: local-dial-config-generation

## 1. Core config templates and layout

- [x] 1.1 Add committed `dial_conf/core/models-template.json`: empty `models`, `keys`
      (`dial_api_key` → role `default`), `roles.default.limits` skeleton
- [x] 1.2 Add committed `dial_conf/core/application-schemas.json` with the Deep Research
      `applicationTypeSchemas` registration (generic `host.docker.internal` endpoints)
- [x] 1.3 Add committed `dial_conf/core/applications-template.json`: one generic
      `deep-research-example` instance (properties mirroring
      `data/configs/example-application-properties.json`) plus its `roles.default.limits`
      fragment
- [x] 1.4 Rework `.gitignore`: drop the `dial_conf/core/*.json` glob; ignore
      `dial_conf/core/applications.json`, `dial_conf/core/generated/`, and the legacy
      `dial_conf/core/config.json`

## 2. Generator script

- [x] 2.1 Add `scripts/generate_dial_config.py`: pydantic-settings class for
      `REMOTE_DIAL_URL`/`REMOTE_DIAL_API_KEY` (env_file `.env`), httpx fetch of
      `GET /openai/models` with `Api-Key` header, chat/embedding conversion routed via
      `ai-dial-adapter-dial` with the remote upstream, merge over the template, rebuild
      `roles.default.limits`, write `dial_conf/core/generated/models.json`
- [x] 2.2 Unit tests for the pure conversion/merge/limits functions (no network)
- [x] 2.3 Add `make infra-config`: seed `applications.json` from the template when missing
      (never overwrite), then run the generator

## 3. Compose wiring

- [x] 3.1 `core` service: mount `./dial_conf/core:/opt/config:ro` (directory) and set
      `aidial.config.files` to the three-file list (generated models, application schemas,
      applications)

## 4. Docs

- [x] 4.1 README: update Prerequisites and Local run steps (add `make infra-config`),
      rewrite the "DIAL core configuration" section around the new file layout and
      instance-adding workflow, add `REMOTE_DIAL_URL`/`REMOTE_DIAL_API_KEY` to the optional
      env table
- [x] 4.2 `.env.example`: add the two `REMOTE_DIAL_*` vars with a comment scoping them to
      `make infra-config`

## 5. Verification

- [x] 5.1 `make format`, `make lint`, `make test` pass
- [x] 5.2 Live check against a real remote DIAL (manual): `make infra-config` generates
      models, `make infra-up` boots core on the split config, chat UI lists models and a
      Deep Research instance answers — confirms Core deep-merges the `roles` fragments
      across config files (fallback per design decision 3 if not).
      Confirmed live (after sections 6 and 7): instance answers through the chat UI —
      Core does deep-merge the `roles` fragments; the fallback was not needed.

## 6. App port parameterization (amendment: port 5000 taken on macOS)

- [x] 6.1 Rename `dial_conf/core/application-schemas.json` to
      `application-schemas-template.json` with `$env:{APP_PORT}` in both endpoints
- [x] 6.2 Generator: render the template into `dial_conf/core/generated/
      application-schemas.json`, substituting `$env:{APP_PORT}` (env value, default `5000`);
      fail on unresolvable tokens; unit tests for the rendering
- [x] 6.3 Compose: `aidial.config.files` points at `generated/application-schemas.json`;
      fix the stale `dial_conf/core/config.json` reference in `docker-compose.app.yml`
- [x] 6.4 Docs: README (config-file table, macOS port-5000 note, containerized-app note)
      and `.env.example` (`APP_PORT` comment)
- [x] 6.5 Re-run `make format`, `make lint`, `make test`

## 7. Fetch via aidial-client (amendment: snake_case limits broke core start)

- [x] 7.1 Bump `aidial-client` to `>=0.14.0,<0.15.0` (shared with the app; full suite
      confirms compatibility)
- [x] 7.2 Rewrite the fetch: `AsyncDial.deployments.list()` + per-model `model.get()` with
      bounded concurrency; typed client responses replace the hand-rolled payload models
- [x] 7.3 Map limits/pricing/features field-by-field to Core's camelCase config keys —
      fixes core failing to start on snake_case `limits` keys passed through from the
      listing API
- [x] 7.4 Tests: camelCase limits mapping (`max_prompt_tokens` → `maxPromptTokens`),
      `maxTotalTokens` variant, typed-object conversion; re-run gates
