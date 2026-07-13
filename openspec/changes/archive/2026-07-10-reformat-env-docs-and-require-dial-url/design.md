## Context

The README **Environment variables** section uses a bespoke two-table layout (Required /
Optional, `Env var | Used for` columns) plus a separate MCP-mode table. The sibling quickapps
repo documents env vars in a single grouped table with `Variable | Default | Required |
Description` columns, which also surfaces each var's default and required status. This change
aligns the DR README with that convention.

Separately, `settings.py` defaults `dial_url` to `http://localhost:8080`. It is the only
localhost default in the settings (`app_host="0.0.0.0"` is a bind-all interface, not localhost).
A localhost default silently becomes the app's built-in Core URL, hiding missing configuration
in real deployments.

The env-var *content* was just settled by the archived `per-request-dial-auth` change
(`DIAL_API_KEY` removed; `MCP_DEPLOYMENT_NAME` added; `MCP_URL`/`MCP_API_KEY` optional). This
change builds on that content and only touches presentation plus the `DIAL_URL` default.

## Goals / Non-Goals

**Goals:**
- README env section is a single quickapps-style grouped table.
- `DIAL_URL` is required with no localhost (or any) default; the app fails fast without it.
- Local dev keeps working with no extra steps beyond copying `.env.example`.

**Non-Goals:**
- No change to which env vars exist or their meaning (that was `per-request-dial-auth`).
- No new `DIAL_URL` validation beyond "present and a valid URL" (pydantic `HttpUrl`).
- No Deprecated-vars subsection (DR has none).

## Decisions

- **Single grouped table, quickapps style.** One `Variable | Default | Required | Description`
  table with bold category header rows: App server, DIAL Core, MCP server, LLM models, Opik
  tracing, Scripts & config generator. Drops the Required/Optional subheadings and the separate
  MCP-mode table. Alternative (keep a dedicated MCP-mode subtable) was rejected to stay faithful
  to the quickapps single-table layout.
- **MCP modes in the `Required` column + footnote.** `MCP_DEPLOYMENT_NAME` and `MCP_URL` carry
  `Required = mode¹`; `MCP_API_KEY` carries `if MCP_URL`; a footnote states exactly one MCP mode
  is required (deployment or local-dev). This keeps the exactly-one-of rule visible without a
  second table.
- **`DIAL_URL` required, no code default.** Change `dial_url: HttpUrl = HttpUrl("http://localhost:8080")`
  to `dial_url: HttpUrl` (no default). pydantic-settings then requires it and fails fast at
  startup, matching the existing fail-fast contract for missing required vars. Alternative
  (optional `None` default, error at first use) was rejected: it defers the failure and does not
  match how quickapps treats `DIAL_URL` (Required=Yes).
- **`.env.example` carries the local value.** Add `DIAL_URL=http://localhost:8080`. The localhost
  value lives in the contributor template, not in code — so "no localhost default in the
  settings" holds while `cp .env.example .env` still yields a working local stack.
- **TOC anchors updated.** The README table-of-contents currently links to the `Required` and
  `Optional` sub-anchors under Environment variables; those sub-anchors are removed, so the TOC
  entries are dropped (leaving the single Environment variables entry).

## Risks / Trade-offs

- **[Breaking config: deployments without `DIAL_URL` now fail to start]** → The app previously
  fell back to `http://localhost:8080`, which never worked in real deployments anyway, so a
  fail-fast surfaces latent misconfiguration rather than regressing a working setup. Call it out
  in the proposal as BREAKING; `.env.example` documents the value for local dev.
- **[Existing tests/fixtures relied on the `dial_url` default]** → Audit `tests/conftest.py` and
  `tests/test_settings.py`; set `DIAL_URL` in the fixture env and add a missing-`DIAL_URL`
  fail-fast test.
- **[README/settings drift]** → Per CLAUDE.md, keep the README env table in sync with the
  settings; the reformat and the `DIAL_URL` change land together in this one change.

## Migration Plan

- Local dev: `cp .env.example .env` already includes `DIAL_URL`; no action for fresh clones.
  Existing `.env` files that omitted `DIAL_URL` (relying on the default) must add
  `DIAL_URL=http://localhost:8080`.
- Deployments: set `DIAL_URL` explicitly (most already do). No rollback concern beyond reverting
  the default if needed.
