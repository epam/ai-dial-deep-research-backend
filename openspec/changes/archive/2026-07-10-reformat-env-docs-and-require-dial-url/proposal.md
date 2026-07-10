# Proposal: reformat-env-docs-and-require-dial-url

## Why

The README **Environment variables** section uses a bespoke two-table (Required / Optional)
layout with only `Env var | Used for` columns, which differs from the sibling quickapps repo
and omits each var's default and required status. Separately, `settings.py` bakes a localhost
default into `DIAL_URL` (`http://localhost:8080`) — a dev-only value that silently ships as the
app's built-in Core URL and hides missing configuration in real deployments.

## What Changes

- Reformat the README **Environment variables** section into a single quickapps-style table
  with columns `Variable | Default | Required | Description`, grouped by bold category header
  rows (App server, DIAL Core, MCP server, LLM models, Opik tracing, Scripts & config
  generator).
  - Remove the separate **Required** / **Optional** subheadings and the separate MCP-mode
    table. The exactly-one-of MCP connection modes are expressed in the `Required` column
    (e.g. `mode¹`, `if MCP_URL`) with a footnote stating exactly one MCP mode is required.
  - Keep the `DOCKER_DEFAULT_PLATFORM` note; no Deprecated subsection (no deprecated vars).
  - Update the section's table-of-contents anchors (the Required/Optional sub-anchors go away).
- **BREAKING** (deployment config): remove the `http://localhost:8080` default from `DIAL_URL`
  in `settings.py`, making `DIAL_URL` a required env var — the app fails fast at startup if it
  is unset. This removes the only localhost default in the settings.
- `.env.example` ships `DIAL_URL=http://localhost:8080` as the documented local-dev value, so
  the code carries no localhost default while the local dev loop keeps working.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dial-agent-with-mcp`: the **Configuration via environment variables** requirement changes —
  `DIAL_URL` becomes a required environment variable with no built-in default (the app has no
  fallback Core URL and exits non-zero at startup when it is unset). The requirement's
  README-table reference stands; the table's presentation (single grouped
  `Variable | Default | Required | Description` layout) is documentation content, not a
  behavioral change.

## Impact

- **Code**: `src/dial_deep_research/settings.py` — drop the `DIAL_URL` localhost default
  (`dial_url: HttpUrl` with no default) and update the field comment.
- **Config / ops**: `DIAL_URL` becomes required. Deployments and local `.env` files must set
  it. `.env.example` gains `DIAL_URL=http://localhost:8080`.
- **Docs**: `README.md` env-variables section reformatted (single grouped table) and its
  table-of-contents anchors updated.
- **Tests**: fixtures/tests that relied on the `dial_url` default (`tests/conftest.py`,
  `tests/test_settings.py`) set `DIAL_URL`; add a test that a missing `DIAL_URL` fails fast.
- **Dependencies**: none.
