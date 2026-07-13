## Why

`DialAppSettings` types `log_level` as a free-form `str`, so an invalid value like `LOG_LEVEL=ifno` loads successfully and only blows up later inside `logging.basicConfig`, with a generic stdlib error that doesn't mention which env var was wrong. We want configuration errors caught at settings-load time with a Pydantic error that names the field and the allowed values.

## What Changes

- Restrict `log_level` to the five stdlib log level names (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- Accept any letter-case (`info`, `Info`, `INFO` all valid) via a Pydantic validator that uppercases before checking.
- Reject unknown values at `DialAppSettings` instantiation with a Pydantic `ValidationError`.
- Add a test asserting valid values load and invalid values raise.

## Capabilities

### New Capabilities
- `app-config`: the typed, validated settings layer that maps environment variables to the app's runtime configuration. Introduced now, scoped to `log_level`; future changes add other settings (e.g. heartbeat interval, DIAL URL) under the same capability.

### Modified Capabilities
*(none)*

## Impact

- `src/dial_deep_research/settings.py`: `log_level` type and validator.
- `tests/`: new `test_settings.py` covering valid/invalid/case-insensitive cases.
- No changes to `__main__.py` — `logging.basicConfig` keeps accepting the uppercased string.
