# CLAUDE.md — dial-deep-research

DIAL Deep Research: a per-request LangChain tool-calling agent over a generic-RAG MCP server.
Python 3.13, `uv`-managed, `src/` layout.
See `pyproject.toml` for `make`-equivalent targets
(`make format`, `make lint`, `make test` if present; otherwise `uv run black/ruff/mypy/pytest`).

## Never commit sensitive info

Never commit secrets, real channel configs, or anything else sensitive: API keys, endpoints,
client names, production details. Real channel configs and DIAL core `config.json` stay
untracked; only generic examples like `data/configs/example.yaml` are committed.

## Rules for coding agents (Claude Code, etc)

- Always use simple and clear phrasings, without unnecessary complexity.
  Including comments, docstrings, git commits and pull requests
- If not sure, ask questions. Do not make design decisions based on your assumptions.
  Except for cases when user explicitly asks you to work autonomously or make decisions yourself.
- Do not cite design docs or other code without naming the source.
  User is not LLM and does not remember everything by heart.

## Sending a query to the DR server

Use `scripts/send_conversation.py` to drive a chat with the app from the CLI. The server is
**expected to be already running**; the script does not start it. The base URL, API key, and
deployment id come from the app settings (`.env` + channel config),
so the script targets whatever the .env and channel config point to.

The conversation artifact file *is* the `messages` array, so multi-turn state threads verbatim.
Two modes:

- `overwrite` — clear the file and start fresh with just this query
- `continue` — load prior messages from the file, append this query, send, append the reply back

```bash
# fresh conversation
uv run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite
# follow-up turn, threading prior state
uv run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue
```

Override `--timeout` as needed.

## Conventions

- **LLM prompts use triple-quoted multiline strings**, not adjacent/parenthesized string-literal concatenation. Do **not** escape newlines with trailing backslashes to join wrapped lines — let long lines wrap as real newlines (harmless inside an LLM prompt) and keep each source line within the 100-col limit. A leading `"""\` to avoid a blank first line is fine. This keeps prompt copy readable and diff-friendly. Applies to system prompts (`app/preparation/prompts.py`, `app/research/prompts.py`) and any injected/middleware prompt text.
- **No new aliases on pydantic-settings fields** — rely on the default field-name → env-var mapping (with the class's `env_prefix`). E.g. `heartbeat_interval` under `env_prefix=""` reads `HEARTBEAT_INTERVAL`.
- **Keep `envvars.md` in sync with the settings.** Update it whenever an env var is added or removed (required or optional alike), and whenever a var's required/optional status changes.
- **Keep `data/configs/example.yaml` in sync with the channel config schema.** Update it whenever `ChannelConfig` (`src/dial_deep_research/channel_config.py`) changes: fields added, removed, or their meaning/requiredness changed. Field descriptions live in the pydantic schema (`Field(description=...)`), not as comments in the YAML.
- **LLM structured-output schemas put the verdict last.** Order fields so a decision/verdict field comes *after* the supporting content that justifies it — the model emits fields in schema order, so reasoning-first yields better decisions. E.g. `questions` before `sufficient`; `revised_plan` (or `problems_found`) before `approved` (or `verdict`). Among the supporting fields themselves, order by logical precedence — a precondition/gating check before any check that only matters once it holds (e.g. `recorded_plan_matches` before `user_approved_a_plan`). Pydantic v2 allows a required field after defaulted ones, so the ordering is free.
- **Never name a list-element field `index` in anything persisted to `custom_content.state`.** The DIAL SDK's chunk-merge (`aidial_sdk.utils.merge_chunks` / `_indexed_list`) treats any list of dicts whose elements carry an `index` key as an OpenAI-style indexed streaming delta — it re-slots the elements by `index` and strips the key, corrupting the stored value (a 1-based list comes back as `[{}, {…}, …]` with the key gone). Use another name (e.g. `number`) for an ordinal field on a persisted list element.

## Code Style

- write clean and reusable code, though don't over-engineer. code should be appropriate for the task
- prefer modern python, with type hints
- always use pydantic models instead of dicts and unclear data structures, unless it introduces unnecessary complexity
- after editing code files, always run `make format` and `make lint`
- use kwargs whenever possible instead of positional arguments - this improves readability.
  Note that some functions and methods have positional-only arguments - it's ok.
- use comments to explain non-obvious code. don't write comments that restate the code.
- when writing docstrings, be concise
- when writing LLM prompts, respect the line length limit of 100 characters. Newlines are fine.
