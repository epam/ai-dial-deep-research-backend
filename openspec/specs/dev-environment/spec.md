# dev-environment

## Purpose

The `dial-deep-research` repo ships a consistent developer environment: a Python project managed by **uv**, a Makefile that exposes every common workflow as a short target, a documented toolchain (black + isort + ruff + mypy + pytest), and a README that gets a contributor from fresh clone to a working chat UI without consulting other documentation. This capability is the contract that lets every other change land in a predictable, hygienic workspace.
## Requirements
### Requirement: Python project managed by uv
The repository SHALL declare its Python project via `pyproject.toml` and manage dependencies with **uv**, including a committed `uv.lock` for reproducible installs.

#### Scenario: Fresh clone install
- **WHEN** a contributor clones the repo and runs the documented install command (`make install`)
- **THEN** `uv sync` resolves and installs all runtime and development dependencies from `uv.lock` without errors, and without requiring network access to private package indexes

#### Scenario: Lockfile drift behaviour
- **WHEN** `pyproject.toml` is modified but `uv.lock` is not regenerated
- **THEN** `make install` SHALL re-resolve dependencies and update `uv.lock` on disk via `uv sync`; the Docker build (via `uv sync --frozen`) SHALL fail instead of silently re-resolving, so drift surfaces at container build time at the latest

### Requirement: Pinned Python version
The project SHALL pin a single Python minor version (`>=3.13,<3.14`) via `pyproject.toml` and a `.python-version` file so that local, Docker, and CI environments resolve to the same interpreter.

#### Scenario: Mismatched interpreter
- **WHEN** a contributor's active interpreter does not match the pinned version
- **THEN** `uv sync` / the Makefile install target SHALL fail fast with a message pointing at the pinned version (uv honours `.python-version` natively)

### Requirement: Makefile as the canonical task interface
The repository SHALL expose a top-level `Makefile` providing at minimum the following targets: `help`, `install`, `format`, `lint`, `test`, `up`, `down`, `app`, `logs`, `cleanup`.

#### Scenario: Discoverability
- **WHEN** a contributor runs `make help` (or bare `make`)
- **THEN** the Makefile SHALL print a short description of each available target

#### Scenario: Target semantics
- **WHEN** any of the targets `install`, `format`, `lint`, `test`, `up`, `down`, `app`, `logs`, `cleanup` are invoked
- **THEN** they SHALL perform, respectively: dependency install via `uv sync`; code formatting (ruff --fix + black + isort); static analysis (ruff + mypy + black --check + isort --check); test execution; starting infra services detached; stopping infra services; running the app on the host via `uv run python -m dial_deep_research`; tailing infra logs; stopping infra and removing volumes — without requiring the contributor to remember underlying tool flags

#### Scenario: Install prerequisite check
- **WHEN** a contributor runs `make install` on a machine where `uv` is not on `PATH`
- **THEN** the target SHALL fail fast with a readable message that points at the documented install instructions (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Requirement: Code quality tooling — black, isort, ruff, mypy
The project SHALL use **black** as its code formatter, **isort** with the `black` profile for import ordering, **ruff** (lint-only; its formatter disabled) for static analysis, and **mypy** for type checking. Configuration for all four SHALL live in `pyproject.toml`. All tools SHALL be invoked via `uv run <tool>` from the Makefile.

#### Scenario: Lint passes on a clean checkout
- **WHEN** a contributor runs `make lint` immediately after `make install` on an unmodified checkout
- **THEN** the command SHALL exit 0 after running, in order: `uv run ruff check`, `uv run mypy`, `uv run black --check`, `uv run isort --check-only` (real-issue checks first, cosmetic formatting checks last, since fixes to the former can re-break the latter)

#### Scenario: Format is idempotent
- **WHEN** a contributor runs `make format` twice in a row on an unmodified checkout
- **THEN** the second invocation SHALL produce no file changes (`ruff check --fix` + black + isort all converge in one pass)

#### Scenario: Black and ruff do not conflict
- **WHEN** a source file has been formatted by `make format`
- **THEN** `make lint` SHALL NOT flag any ruff rule triggered by black's chosen formatting (configuration ignores format-adjacent rules such as line-length `E501`)

### Requirement: Minimal developer README
The repository SHALL include a `README.md` at its root that describes, at minimum: prerequisites (Docker, uv install one-liner), how to install dependencies, how to start the stack, how to open the chat UI on `http://localhost:3000`, how to select the `Deep Research` deployment (deployment id `deep-research`), and how to tear the stack down.

The README SHALL order its top-level sections by audience, widening from general to specialized: a general-audience introduction first, then a configuration-and-deployment block (what to configure, the environment-variables reference, and DIAL Core registration) aimed at operators, then the contributor sections (local run with its prerequisites, followed by optional developer tooling). Contributor-only content SHALL NOT precede the configuration-and-deployment block.

#### Scenario: Cold-start contributor
- **WHEN** a new contributor follows the README top-to-bottom
- **THEN** they SHALL reach a working chat UI conversing with the `Deep Research` application without consulting other repositories or internal documentation

#### Scenario: Operator finds configuration before dev setup
- **WHEN** a reader opens the README to configure or deploy the app
- **THEN** the configuration and environment-variables sections SHALL appear before the local-development and contributor sections, so the reader reaches configuration without scrolling past dev setup
