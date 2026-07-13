# Tasks

## 1. Settings

- [x] 1.1 Add `heartbeat_interval: int = Field(default=5, ge=1, alias="HEARTBEAT_INTERVAL")` to `DialAppSettings` in `src/dial_deep_research/settings.py`.

## 2. Factory

- [x] 2.1 In `src/dial_deep_research/app/factory.py`, replace the literal `heartbeat_interval=5` in `app.add_chat_completion(...)` with `dial_app_settings.heartbeat_interval`. Verify no other integer literal for this parameter remains in the module.

## 3. Docs

- [x] 3.1 Append a `HEARTBEAT_INTERVAL=5` line to `.env.example`, with a one-line comment above it explaining the unit (seconds between keep-alive heartbeats during long completions) and that the default is `5`.

## 4. Tests

- [x] 4.1 In `tests/test_settings.py`, add coverage for heartbeat: default loads as `5`, `HEARTBEAT_INTERVAL=30` loads as `30`, `HEARTBEAT_INTERVAL=0` raises `ValidationError` referencing the field, `HEARTBEAT_INTERVAL=-1` raises `ValidationError` referencing the field.

## 5. Verify

- [x] 5.1 Run `make format && make lint && make test` — all green.
