## Context

The DIAL SDK (`aidial_sdk`) supports both pydantic v1 and v2. It chooses at **import time**:

```python
# aidial_sdk/_pydantic/__init__.py
INSTALLED_PYDANTIC_V2 = VERSION.startswith("2.")
USE_PYDANTIC_V2 = env_bool("PYDANTIC_V2", False)   # os.getenv("PYDANTIC_V2", "False")
PYDANTIC_V2 = INSTALLED_PYDANTIC_V2 and USE_PYDANTIC_V2
```

This project installs pydantic v2, but with `PYDANTIC_V2` unset `USE_PYDANTIC_V2` is `False`, so
the SDK builds its `Request`/`Response` models on pydantic **v1**. Verified: by default
`aidial_sdk.chat_completion.Request` subclasses `pydantic.v1.BaseModel`; with `PYDANTIC_V2=True`
it subclasses `pydantic.BaseModel`. The rest of the app is pydantic v2.

Because the flag is read at import time, it must be present in the environment **before** the
first `aidial_sdk` import. Entry points differ:

- App: `src/dial_deep_research/__main__.py` loads `.env` via `dotenv` before importing the app
  factory (which imports `aidial_sdk`).
- Tests: `tests/conftest.py` sets required vars with `os.environ.setdefault` and does **not** load
  `.env`; it then imports the app factory.
- Scripts: talk to the running server over HTTP and generally do not import `aidial_sdk`.

The common thread across all of these: importing any `dial_deep_research` submodule first runs the
package's `__init__.py`. `src/dial_deep_research/__init__.py` is currently effectively empty.

## Goals / Non-Goals

**Goals:**
- The DIAL SDK uses pydantic v2 models everywhere the app code runs (app, tests, scripts).
- The guarantee holds without relying on each deployment or test setup remembering to set an env
  var.

**Non-Goals:**
- Exposing `PYDANTIC_V2` as a tunable deployment knob (it is invariant, not per-environment).
- Changing the SDK, pydantic versions, or any app models.
- Adding `PYDANTIC_V2` to `.env.example`, `docker-compose.yml`, or the README env-var table.

## Decisions

**Decision: Set the flag in code via `os.environ.setdefault` at package import.**
Add to the top of `src/dial_deep_research/__init__.py`, before any other import:

```python
import os

# The DIAL SDK reads PYDANTIC_V2 at import time and defaults to pydantic v1. The app runs on
# pydantic v2, so force the SDK into v2 mode before aidial_sdk is imported. Set here (the
# earliest import point) so it also applies to tests and scripts, which do not load .env.
os.environ.setdefault("PYDANTIC_V2", "True")
```

- *Why the package `__init__.py`*: it runs before any submodule that imports `aidial_sdk`, for
  every entry point, so ordering is deterministic. It is the single earliest guaranteed point.
- *Why `setdefault` (not a hard assignment)*: an explicit `PYDANTIC_V2` in the environment is left
  untouched, keeping an escape hatch and avoiding surprising override behavior.

**Alternatives considered:**
- *Env config only* (`.env.example` + `docker-compose.yml` + `Dockerfile` + `conftest.py`):
  rejected — scattered across files, and any miss silently reverts the SDK to v1. Tests would need
  their own copy because they do not load `.env`.
- *Set it in `__main__.py`*: rejected — covers only `python -m dial_deep_research`, not tests or
  scripts.

## Risks / Trade-offs

- [Import side effect in `__init__.py`] → It is a single, well-commented line mutating one env var;
  the repo already performs env manipulation at import boundaries (`conftest.py` `setdefault`,
  `__main__.py` dotenv load), so this fits the existing pattern.
- [A stray `import aidial_sdk` before `import dial_deep_research`] → Would read the flag first. Not
  a concern in this codebase: all SDK use is behind `dial_deep_research` submodules, so the package
  `__init__.py` always runs first. Covered by a test that asserts the SDK is in v2 mode.
