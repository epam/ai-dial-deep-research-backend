# Design: local-dial-config-generation

## Context

Reference implementation: `ai-dial-quickapps-backend`. There, DIAL Core merges a *list* of
config files (`aidial.config.files`) at startup: a generated `models.json` (pulled from a
remote DIAL by `src/scripts/generate_dial_config.py`) plus committed static JSON files. We
adopt the same shape, adapted to this repo's conventions (uv, flat `scripts/`, pydantic
models, kebab-case make targets) and to its sensitivity constraints (client instances must
never be committed).

## Decisions

### 1. Three-way file split under `dial_conf/core/`

| File | Tracked | Content |
| ---- | ------- | ------- |
| `models-template.json` | committed | base skeleton: empty `models`, `keys` (`dial_api_key` → role `default`), `roles.default.limits` skeleton |
| `generated/models.json` | gitignored | generator output: remote models + rebuilt limits; embeds `REMOTE_DIAL_API_KEY` in upstreams — must stay local |
| `application-schemas-template.json` | committed | Deep Research `applicationTypeSchemas` registration; generic except the app port, carried as an `$env:{APP_PORT}` placeholder |
| `generated/application-schemas.json` | gitignored | the registration rendered by `make infra-config` with `APP_PORT` (default `5000`) substituted |
| `applications-template.json` | committed | one generic example instance (`deep-research-example`, properties mirroring `data/configs/example-application-properties.json`) plus the `roles` fragment granting the default role access to it |
| `applications.json` | gitignored | local copy of the template; contributors add real client instances here |

Rationale: split by sensitivity and genericness. The registration has no secrets, but its
completion/schema endpoints carry the app port, which is machine-specific (macOS binds 5000
to AirPlay Receiver), so the committed artifact is a template and the loadable file is
rendered locally. Instances carry client names — local-only, like the old `config.json`.
The generated models file embeds the remote key — local-only, same as quickapps.

### 1a. App port parameterized via `APP_PORT`

`APP_PORT` already drives the app's bind port (`Settings.app_port`); the renderer reuses it
so one env var moves both ends — the uvicorn bind and Core's routing endpoints. Substitution
uses quickapps' `$env:{VAR}` token syntax, but resolved from an explicit mapping with a
default (`APP_PORT` → `5000` when unset) and a hard error on unknown tokens, rather than
silently passing unresolved tokens through. This applies only to the application-schemas
template; the models template ships no entries needing substitution. The containerized-app
overlay (`docker-compose.app.yml`) is unaffected: the container always listens on 5000 and
only the host mapping uses `APP_PORT`; routing to the containerized app still requires
hand-editing the endpoints' host in the *generated* file (now harmless — it is gitignored).

### 2. Generator script shape

`scripts/generate_dial_config.py`, run via `uv run`. Follows quickapps'
`generate_dial_config.py` but slimmed:

- A small `pydantic-settings` class local to the script reads `REMOTE_DIAL_URL` and
  `REMOTE_DIAL_API_KEY` (no aliases; `.env` loaded like the app does). These stay
  out of the app `Settings` — they are dev tooling, not app runtime config.
- The remote is queried through the `aidial-client` library (a runtime dependency, bumped
  from 0.7.x to 0.14.x for the typed listing fields): `AsyncDial.deployments.list()`
  enumerates the models (Core's `/openai/deployments` lists all models), then
  `model.get(id)` fetches each model's typed info — capabilities, limits, pricing — with
  bounded concurrency. Typed responses replace hand-rolled payload models. Applications are
  not fetched (out of scope).
- Each model with a `chat_completion` or `embeddings` capability becomes a Core entry:
  `endpoint` → `http://ai-dial-adapter-dial:5000/openai/deployments/{id}{path}` (this repo's
  adapter service name, not quickapps' `adapter-dial`), one upstream →
  `{REMOTE_DIAL_URL}/openai/deployments/{id}{path}` with the remote key. Metadata is mapped
  field-by-field to the camelCase keys Core's config expects (`displayName`,
  `maxPromptTokens`, ...) — Core parses its config strictly, so passing the listing API's
  snake_case keys through (as an early version did for `limits`) makes Core fail to start.
  Models with neither capability are skipped.
- Fetched models are merged **over** the template's `models`, then
  `roles.default.limits` is rebuilt with one `{}` entry per model id, granting the
  `default` role access to every model.
- Output written with `indent=2` to `dial_conf/core/generated/models.json`, creating the
  directory when needed. Paths are argparse options with these defaults.
- Pure conversion/merge functions so unit tests need no network.

### 3. Instance access via a roles fragment in the applications file

The generator's rebuilt `roles.default.limits` covers models only. Application instances get
access through a `roles.default.limits` fragment inside `applications-template.json` /
`applications.json`, keeping each instance's config self-contained in one file and the
generator decoupled from local instances. This relies on DIAL Core deep-merging `roles`
across the `aidial.config.files` list — verify on the live stack during implementation.
Fallback if Core does not merge: have the generator fold instance ids from the local
`applications.json` into the rebuilt limits.

### 4. Compose wiring

The `core` service mounts `./dial_conf/core:/opt/config:ro` (directory instead of the single
file) and sets:

```yaml
aidial.config.files: '["/opt/config/generated/models.json", "/opt/config/generated/application-schemas.json", "/opt/config/applications.json"]'
```

Templates land in the container too but are not listed, so Core ignores them. Settings mount
is unchanged.

### 5. `make infra-config`, not a dependency of `infra-up`

`infra-config` seeds `applications.json` from the template when missing (never overwrites),
then runs the generator, which renders the application-schemas registration and pulls the
models. It is a separate documented step, not a prerequisite of `infra-up`:
generation needs remote credentials and a network round-trip, which would tax every stack
start; once generated, the files persist until the contributor refreshes them.

### 6. `.gitignore` narrowing keeps the legacy file ignored

`dial_conf/core/*.json` becomes explicit entries: `applications.json`, `generated/`, and —
deliberately — the legacy `config.json`. Contributors have stale, sensitive `config.json`
files on disk; narrowing the glob without that entry would surface them as committable.

## Risks / Trade-offs

- **Core deep-merge of `roles` across files** (decision 3) is the one behavior not proven by
  the quickapps reference (its static apps carry no roles fragment). Mitigated by the live
  verification task and the documented generator fallback.
- Cold start gains a required step (`make infra-config` before the first `infra-up`); Core
  fails to boot if listed config files are missing. Mitigated by README ordering and the
  make target doing both halves in one command.
- The generated file duplicates the remote key per model upstream (same as quickapps);
  acceptable because the file is gitignored and local-only.
