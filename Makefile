UV ?= uv
SRC_DIRS = src tests scripts
MYPY_DIRS = src scripts

# Opik trace stack lives in its own Compose project (`name: opik` upstream),
# so its lifecycle is independent of `infra-up`/`infra-down` here. We pin a specific
# upstream tag rather than tracking `main` / `latest`.
# The pin is passed inline on `opik-up` (the only command that resolves image tags).
# `down`/`ps` act on containers by project label, so the variable doesn't need exporting.
OPIK_VERSION ?= 2.0.17
OPIK_DIR ?= .opik-local
OPIK_COMPOSE = $(OPIK_DIR)/deployment/docker-compose/docker-compose.yaml

# Bare `make` runs the first target listed here — that's `help`, which auto-prints
# every target whose line ends with a `## description` suffix.
#
# The `## description` convention:
#   In Makefiles, `#` starts a comment. By convention, `##` (double hash) at the
#   end of a target line marks it as a USER-facing documented target. The awk
#   regex below matches `##` specifically, so:
#     - `install: deps ## Install everything`   → appears in `make help`
#     - `check_uv: ...` (no `##`)               → hidden; it's an internal helper
#   To add a new target to the help output, just tack on ` ## one-line description`.
#
# The awk one-liner is a common snippet, explained inline:
#
#   @                      — silence make's "echo the command itself" behavior
#   FS = ":.*##"           — split each line on 'colon, any chars, then ##'
#                            so `install: deps ## Install` → $1="install", $2="Install"
#   /^[a-zA-Z_-]+:.*?##/   — only act on lines that look like a documented target
#   \033[36m ... \033[0m   — ANSI escape: cyan / reset (colors the target name)
#   %-14s                  — left-align the target name in a 14-char column
#   $$1, $$2               — awk's $1, $2 (doubled because $ is special in Makefiles)
#   $(MAKEFILE_LIST)       — built-in: every Makefile make has read (just `Makefile`
#                            here, but auto-extends if we later `include` more files)
help: ## Show available make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Available targets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

check_uv:
	@command -v $(UV) >/dev/null 2>&1 || { \
		echo "Error: '$(UV)' not found on PATH."; \
		echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	}

install: check_uv ## Install all dependencies (runtime + dev) from uv.lock
	$(UV) sync

lint: install ## Run ruff, mypy, formatting checks (black, isort), then the schema drift check
	$(UV) run ruff check $(SRC_DIRS)
	$(UV) run mypy --show-error-codes $(MYPY_DIRS)
	$(UV) run black $(SRC_DIRS) --check
	$(UV) run isort $(SRC_DIRS) --check-only --diff
	$(UV) run python scripts/dump_app_schema.py --check

format: install ## Auto-fix everything auto-fixable: ruff, black, isort, regenerate the schema artifact
	$(UV) run ruff check $(SRC_DIRS) --fix
	$(UV) run black $(SRC_DIRS)
	$(UV) run isort $(SRC_DIRS)
	$(UV) run python scripts/dump_app_schema.py

test: install ## Run pytest
	$(UV) run pytest tests

## -------- infra -------- ##

infra-config: install ## Build the local DIAL core config: seed applications.json, pull models from the remote DIAL
	@test -f dial_conf/core/applications.json || { \
		cp dial_conf/core/applications-template.json dial_conf/core/applications.json; \
		echo "seeded dial_conf/core/applications.json from the template"; \
	}
	$(UV) run python scripts/generate_dial_config.py

infra-up: ## Start the infra services (DIAL core, chat UI, themes, redis) detached
	docker compose up -d

infra-down: ## Stop the infra services
	docker compose down

infra-logs: ## Tail logs from the infra services
	docker compose logs -f

infra-cleanup: ## Stop infra and remove volumes (destroys DIAL core data + logs)
	docker compose down --volumes

## -------- app -------- ##

# Both compose files together: infra + the containerized app.
APP_COMPOSE = -f docker-compose.yml -f docker-compose.app.yml

app: install ## Run the app on the host via uvicorn (infra must already be up)
	$(UV) run python -m dial_deep_research

app-build: ## Build the app Docker image
	docker compose $(APP_COMPOSE) build deep-research

app-logs: ## Tail logs from the app container
	docker compose $(APP_COMPOSE) logs -f deep-research

## -------- all: infra + app in docker (opt-in) -------- ##

all-up: ## Start infra + the app container (containerized alternative to `infra-up` + `app`)
	docker compose $(APP_COMPOSE) up -d

all-down: ## Stop infra + the app container
	docker compose $(APP_COMPOSE) down

all-logs: ## Tail logs from the infra + the app container
	docker compose $(APP_COMPOSE) logs -f

## -------- opik -------- ##

$(OPIK_DIR):
	git clone --depth 1 --branch $(OPIK_VERSION) https://github.com/comet-ml/opik.git $(OPIK_DIR)

opik-up: $(OPIK_DIR) ## Start the local Opik trace stack (separate Compose project; UI at http://localhost:5173)
	OPIK_VERSION=$(OPIK_VERSION) docker compose -f $(OPIK_COMPOSE) --profile opik up -d

opik-down: ## Stop the local Opik trace stack (does NOT touch infra)
	docker compose -f $(OPIK_COMPOSE) --profile opik down

opik-logs: ## Tail logs from the local Opik trace stack
	docker compose -f $(OPIK_COMPOSE) --profile opik logs -f

## -------- mcp inspector -------- ##

mcp-inspector:  ## start mcp inspector UI
	docker run --rm \
		-p 127.0.0.1:6274:6274 \
		-p 127.0.0.1:6277:6277 \
		-e HOST=0.0.0.0 \
		-e MCP_AUTO_OPEN_ENABLED=false \
		ghcr.io/modelcontextprotocol/inspector:latest
