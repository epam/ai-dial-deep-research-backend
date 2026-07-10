# Proposal: local-dial-config-generation

## Why

The local DIAL Core config (`dial_conf/core/config.json`) is a single hand-written, untracked
file. Every contributor builds it from README snippets: dozens of model entries (each
embedding the remote DIAL key in its upstream), the Deep Research application-type
registration, application instances, API keys, and role limits. That is slow to set up, drifts
per machine, and mixes generic content (the type registration) with sensitive content (client
instances, remote keys). The quickapps repo already has a working pattern: pull model configs
from a remote DIAL and generate them locally, keep generic templates committed, and keep
client-specific and key-bearing files local-only.

## What Changes

- Add `scripts/generate_dial_config.py`: fetch model definitions from a remote DIAL via the
  `aidial-client` library (deployments listing + per-model info, typed responses; the
  dependency is bumped to 0.14.x), convert each chat/embedding model into a DIAL Core model
  entry routed through the local `ai-dial-adapter-dial` with the remote deployment as
  upstream — mapping metadata to the camelCase keys Core's strict config parser expects —
  merge the result over a committed `dial_conf/core/models-template.json` (keys + roles
  skeleton), rebuild `roles.default.limits`, and write the gitignored
  `dial_conf/core/generated/models.json`.
- Commit `dial_conf/core/application-schemas-template.json` — the Deep Research
  application-type registration (generic `host.docker.internal` endpoints, no secrets) with
  an `$env:{APP_PORT}` placeholder — rendered by `make infra-config` into the gitignored
  `dial_conf/core/generated/application-schemas.json` so the app port is configurable per
  machine (macOS binds 5000 to AirPlay Receiver; `APP_PORT` already drives the app bind).
- Add a committed generic `dial_conf/core/applications-template.json` (one example instance)
  seeded to a gitignored local `dial_conf/core/applications.json`, where real client
  instances live.
- Point the `core` service at the split config: mount `dial_conf/core/` as a directory and
  list the three files in `aidial.config.files`.
- Add a `make infra-config` target: seed `applications.json` from the template when missing,
  then run the generator.
- New optional env vars `REMOTE_DIAL_URL` / `REMOTE_DIAL_API_KEY` (used only by the
  generator), documented in `.env.example` and the README.
- Rework `.gitignore` for `dial_conf/core/`: track the committed files, keep
  `applications.json`, `generated/`, and the legacy `config.json` ignored.
- **BREAKING** (local dev only): the hand-made `dial_conf/core/config.json` is no longer
  read by the stack; its content moves to the generated/template files.

Out of scope: pulling remote DIAL *applications* (Deep Research consumes data via MCP and
LLMs via Core model deployments; no remote DIAL application is needed), the Admin UI export
overlay quickapps has, and `$env:{}` substitution in the models template (it ships no model
entries that would need it; substitution applies only to the application-schemas template).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-stack`: model configs become generated (pulled from a remote DIAL) instead of
  hand-written; the app-type registration becomes a committed static config file; application
  instances move to a gitignored local file seeded from a committed template; the compose
  `core` service loads the split file list; `.env` gains the two optional `REMOTE_DIAL_*`
  vars; cold-start flow gains the `make infra-config` step.
