## Why

CI already runs on the org's shared `epam/ai-dial-ci` reusable workflows, which are
Poetry-native: `python_prepare` runs `poetry install`, and the PR/release workflows call
`make lint` / `make test`. This repo is uv-managed, so it diverges from the org toolchain
and from the sibling `generic-rag` project (also Poetry, Python 3.13).

Switch the repo to Poetry to align with CI. This is a deliberate, temporary step: uv is
faster and we prefer it. Once the shared CI supports uv, we intend to switch back.

## What Changes

- Manage the project with **Poetry** (`poetry-core` build backend) instead of uv. Keep the
  `src/` layout as an installable package so `python -m dial_deep_research` still works
  everywhere (CI installs with `--no-root`, so `pythonpath = ["src"]` covers tests).
- Replace the committed `uv.lock` with a committed `poetry.lock`. Keep the existing
  dependency version caps in `pyproject.toml`; let Poetry resolve to the latest within those
  caps (this may incidentally clear some known advisories).
- Commit a `poetry.toml` with `virtualenvs.in-project = true` so the venv lives in the
  project (`./.venv`) rather than Poetry's global cache.
- Drop the uv-only `[tool.uv] constraint-dependencies` litellm floor — Poetry has no
  equivalent, and the lock captures a patched litellm within the existing caps anyway.
- Rewrite the Makefile targets and the Dockerfile to use Poetry. Update README, CLAUDE.md,
  and the helper-script usage strings.
- No application code or runtime behaviour change: same Python 3.13, same deps within caps.

## Capabilities

### Modified Capabilities
- `dev-environment`: managed by Poetry (lockfile, install command, Makefile tool
  invocations, README prerequisite) instead of uv.
- `local-stack`: `make app` runs the app via `poetry run python -m dial_deep_research`.

## Impact

- `pyproject.toml`, `poetry.lock` (new), `poetry.toml` (new), `uv.lock` (removed),
  `Makefile`, `Dockerfile`, `README.md`, `CLAUDE.md`, `scripts/dump_app_schema.py`,
  `scripts/send_conversation.py`.
- No application source changes. Dependabot config unchanged (still `pip` ecosystem).
