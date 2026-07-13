# Tasks

## 1. Settings

- [x] 1.1 In `src/dial_deep_research/settings.py`, define an `Annotated` type alias combining `Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]` with `BeforeValidator(str.upper)`.
- [x] 1.2 Change the `log_level` field on `DialAppSettings` to use the new alias. Keep the `"INFO"` default and `LOG_LEVEL` env alias.

## 2. Caller cleanup

- [x] 2.1 In `src/dial_deep_research/__main__.py`, drop the redundant `.upper()` in `_configure_logging` — the value is already normalized by the settings validator.

## 3. Tests

- [x] 3.1 Add `tests/test_settings.py` with four cases: default loads as `"INFO"`, canonical `DEBUG` loads, mixed-case `warning` normalizes to `"WARNING"`, and `ifno` raises `ValidationError` mentioning `log_level`.

## 4. Verify

- [x] 4.1 Run `make format && make lint && make test` — all green.
