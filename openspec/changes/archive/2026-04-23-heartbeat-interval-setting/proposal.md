## Why

`factory.py:25` passes `heartbeat_interval=5` to `app.add_chat_completion(...)` as an undocumented magic number. When real deep-research logic replaces the echo handler, long-running completions will actually exercise the heartbeat — and operators will want to tune it without recompiling. Promoting the value to a typed setting documents intent, makes it env-tunable, and extends the freshly-introduced `app-config` capability.

## What Changes

- Add a `heartbeat_interval` field to `DialAppSettings`, env alias `HEARTBEAT_INTERVAL`, default `5`, constrained to positive integers (validation error at settings load if `HEARTBEAT_INTERVAL=0` or negative).
- Replace the hardcoded `heartbeat_interval=5` in `src/dial_deep_research/app/factory.py` with `dial_app_settings.heartbeat_interval`.
- Document `HEARTBEAT_INTERVAL` in `.env.example`.
- Add tests for the new setting (default, valid override, invalid rejection).

## Capabilities

### New Capabilities
*(none)*

### Modified Capabilities
- `app-config`: add a second requirement — a validated, env-driven heartbeat interval — alongside the existing `log_level` requirement.

## Impact

- `src/dial_deep_research/settings.py`: new field.
- `src/dial_deep_research/app/factory.py`: consume the setting instead of the literal.
- `.env.example`: documentation line for the new env var.
- `tests/test_settings.py`: extend with heartbeat cases.
