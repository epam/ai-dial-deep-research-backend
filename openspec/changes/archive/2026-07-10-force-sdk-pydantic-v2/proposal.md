## Why

The DIAL SDK reads the `PYDANTIC_V2` environment variable **at import time** and defaults it
to false. With the flag unset, the SDK builds its `Request`/`Response` (and related) models on
pydantic **v1**, even though this project runs on pydantic v2. The app's own models
(`ApplicationProperties`, `Settings`, LLM structured outputs) are pydantic v2, so the SDK and
the app disagree on model semantics. Turning the flag on makes the SDK use pydantic v2 models,
matching the rest of the codebase.

## What Changes

- Force `PYDANTIC_V2=True` in code, at the earliest guaranteed import point
  (`src/dial_deep_research/__init__.py`), before any `aidial_sdk` import runs.
- Use `os.environ.setdefault`, so an explicit `PYDANTIC_V2` override in the environment is still
  respected.
- Applies to every entry point automatically: the app (`python -m dial_deep_research`), the test
  suite (whose `conftest.py` does not load `.env`), and helper scripts.
- Treat it as an invariant of the code, not a per-environment deployment knob: it is **not** added
  to `.env.example` or `docker-compose.yml`.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `dial-agent-with-mcp`: add a requirement that the app runs the DIAL SDK in pydantic v2 mode, so
  the SDK's models are pydantic v2 and consistent with the app's models.

## Impact

- Code: `src/dial_deep_research/__init__.py` (currently effectively empty) gains an
  `os.environ.setdefault("PYDANTIC_V2", "True")` before other imports.
- Runtime: the DIAL SDK's request/response models load as pydantic v2 across the app, tests, and
  scripts.
- No dependency, API, or configuration-surface changes; no new environment variable to set.
