## ADDED Requirements

### Requirement: Python project managed by Poetry
The repository SHALL declare its Python project via `pyproject.toml` and manage dependencies with **Poetry** (`poetry-core` build backend), including a committed `poetry.lock` for reproducible installs. The `src/` layout SHALL remain an installable package (`packages = [{ include = "dial_deep_research", from = "src" }]`) so `python -m dial_deep_research` works in every environment.

This is a deliberate, temporary alignment with the org's Poetry-based shared CI. uv is faster and preferred; once the shared CI supports uv, the project intends to switch back.

#### Scenario: Fresh clone install
- **WHEN** a contributor clones the repo and runs the documented install command (`make install`)
- **THEN** `poetry install` SHALL resolve and install all runtime and development dependencies from `poetry.lock` without errors

#### Scenario: Lockfile drift behaviour
- **WHEN** `pyproject.toml` is modified but `poetry.lock` is not regenerated
- **THEN** `poetry check --lock` (run by `make lint` / CI) SHALL fail, surfacing the drift instead of silently re-resolving

## REMOVED Requirements

### Requirement: Python project managed by uv
**Reason**: Replaced by "Python project managed by Poetry" to align with the org's shared Poetry-based CI.
**Migration**: `uv.lock` is removed and regenerated as `poetry.lock`; `make install` now runs `poetry install` instead of `uv sync`.

## MODIFIED Requirements

### Requirement: Pinned Python version
The project SHALL pin a single Python minor version (`>=3.13,<3.14`) via `pyproject.toml` and a `.python-version` file so that local, Docker, and CI environments resolve to the same interpreter.

#### Scenario: Mismatched interpreter
- **WHEN** a contributor's active interpreter does not match the pinned version
- **THEN** `poetry install` SHALL fail fast with a message about the incompatible Python version; `poetry env use python3.13` selects a matching interpreter

### Requirement: Makefile as the canonical task interface
The repository SHALL expose a top-level `Makefile` providing at minimum the following targets: `help`, `install`, `format`, `lint`, `test`, `up`, `down`, `app`, `logs`, `cleanup`.

#### Scenario: Discoverability
- **WHEN** a contributor runs `make help` (or bare `make`)
- **THEN** the Makefile SHALL print a short description of each available target

#### Scenario: Target semantics
- **WHEN** any of the targets `install`, `format`, `lint`, `test`, `up`, `down`, `app`, `logs`, `cleanup` are invoked
- **THEN** they SHALL perform, respectively: dependency install via `poetry install`; code formatting (ruff --fix + black + isort); static analysis (ruff + mypy + black --check + isort --check); test execution; starting infra services detached; stopping infra services; running the app on the host via `poetry run python -m dial_deep_research`; tailing infra logs; stopping infra and removing volumes — without requiring the contributor to remember underlying tool flags

#### Scenario: Install prerequisite check
- **WHEN** a contributor runs `make install` on a machine where `poetry` is not on `PATH`
- **THEN** the target SHALL fail fast with a readable message that points at the Poetry install instructions

### Requirement: Code quality tooling — black, isort, ruff, mypy
The project SHALL use **black** as its code formatter, **isort** with the `black` profile for import ordering, **ruff** (lint-only; its formatter disabled) for static analysis, and **mypy** for type checking. Configuration for all four SHALL live in `pyproject.toml`. All tools SHALL be invoked via `poetry run <tool>` from the Makefile.

#### Scenario: Lint passes on a clean checkout
- **WHEN** a contributor runs `make lint` immediately after `make install` on an unmodified checkout
- **THEN** the command SHALL exit 0 after running, in order: `poetry run ruff check`, `poetry run mypy`, `poetry run black --check`, `poetry run isort --check-only` (real-issue checks first, cosmetic formatting checks last, since fixes to the former can re-break the latter)

#### Scenario: Format is idempotent
- **WHEN** a contributor runs `make format` twice in a row on an unmodified checkout
- **THEN** the second invocation SHALL produce no file changes (`ruff check --fix` + black + isort all converge in one pass)

#### Scenario: Black and ruff do not conflict
- **WHEN** a source file has been formatted by `make format`
- **THEN** `make lint` SHALL NOT flag any ruff rule triggered by black's chosen formatting (configuration ignores format-adjacent rules such as line-length `E501`)

### Requirement: Minimal developer README
The repository SHALL include a `README.md` at its root that describes, at minimum: prerequisites (Docker, Poetry install one-liner), how to install dependencies, how to start the stack, how to open the chat UI on `http://localhost:3000`, how to select the `Deep Research` deployment (deployment id `deep-research`), and how to tear the stack down.

The README SHALL order its top-level sections by audience, widening from general to specialized: a general-audience introduction first, then a configuration-and-deployment block (what to configure, the environment-variables reference, and DIAL Core registration) aimed at operators, then the contributor sections (local run with its prerequisites, followed by optional developer tooling). Contributor-only content SHALL NOT precede the configuration-and-deployment block.

#### Scenario: Cold-start contributor
- **WHEN** a new contributor follows the README top-to-bottom
- **THEN** they SHALL reach a working chat UI conversing with the `Deep Research` application without consulting other repositories or internal documentation

#### Scenario: Operator finds configuration before dev setup
- **WHEN** a reader opens the README to configure or deploy the app
- **THEN** the configuration and environment-variables sections SHALL appear before the local-development and contributor sections, so the reader reaches configuration without scrolling past dev setup
