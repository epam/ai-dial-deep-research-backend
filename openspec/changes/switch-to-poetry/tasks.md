# Tasks

## 1. pyproject.toml
- [ ] Replace `[build-system]` (hatchling → `poetry-core>=2.0.0,<3.0.0`)
- [ ] Add `[tool.poetry]` with `packages = [{ include = "dial_deep_research", from = "src" }]`
- [ ] Remove `[tool.hatch.*]` and the `[tool.uv] constraint-dependencies` block
- [ ] Keep the existing dependency version caps under `[project.dependencies]`
- [ ] Add `src` to `[tool.pytest.ini_options] pythonpath` (covers CI's `poetry install --no-root`)

## 2. Lockfile & venv config
- [ ] `poetry lock` to generate `poetry.lock`; commit it
- [ ] `git rm uv.lock`
- [ ] Commit `poetry.toml` with `virtualenvs.in-project = true` (venv in `./.venv`)

## 3. Makefile
- [ ] `UV ?= uv` → `POETRY ?= poetry`; `check_uv` → `check_poetry`
- [ ] `uv sync` → `poetry install`; `uv run` → `poetry run`
- [ ] Update the install-hint message to point at the Poetry install docs

## 4. Dockerfile
- [ ] Drop the `astral-sh/uv` image and `UV_*` env vars
- [ ] Builder: export deps + build/install the project wheel (non-editable) into `.venv`
- [ ] Runner stage unchanged: copy `.venv`, run `python -m dial_deep_research`

## 5. Docs & scripts
- [ ] README: prerequisites (Poetry install) and the `uv run` script examples → `poetry run`
- [ ] CLAUDE.md: "uv-managed" line, the make-equivalents line, the send_conversation examples
- [ ] `scripts/dump_app_schema.py`, `scripts/send_conversation.py`: `uv run` → `poetry run`

## 6. Verify
- [ ] `make install && make format && make lint && make test` all green
- [ ] `poetry check --lock` clean
- [ ] `make app-build` builds; `python -m dial_deep_research` starts in-container
- [ ] `grep -rn '\buv\b'` (excluding `.opik-local/` and `openspec/changes/archive/`) shows no stragglers
