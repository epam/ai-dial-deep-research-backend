## Context

`DialAppSettings` (`src/dial_deep_research/settings.py`) loads five env-driven settings via pydantic-settings. `log_level` is currently `str`, so Pydantic accepts anything and the stdlib `logging.basicConfig(level=...)` call in `__main__.py` is the only line that rejects bad values — with a generic `ValueError: Unknown level: 'IFNO'`. Moving the check into the settings layer gives contributors a clear Pydantic error at import time, before logging is even configured.

## Goals / Non-Goals

**Goals:**
- Reject invalid `LOG_LEVEL` values at settings-load time, with a Pydantic error naming the field.
- Keep case-insensitive ergonomics (contributors often write `info` in `.env`).

**Non-Goals:**
- Validating other settings (`dial_url`, `app_host`, etc.) — scoped out; follow-up changes can extend `app-config`.
- Supporting numeric log levels (`LOG_LEVEL=20`). Stdlib supports it, but no one in this repo uses it, and it would complicate the `Literal` contract.
- Changing how `__main__.py` configures logging — it continues to call `logging.basicConfig(level=value)` on the already-uppercased value.

## Decisions

### Decision 1: `Literal[...]` + `BeforeValidator` rather than custom `field_validator`

Use a `typing.Annotated[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], BeforeValidator(str.upper)]` alias. The `BeforeValidator` normalizes case before `Literal` runs, so `info` → `"INFO"` passes, and `ifno` → `"IFNO"` fails with a Pydantic error that already lists the allowed values.

**Alternative considered:** a `@field_validator("log_level", mode="before")` method. Equivalent behavior but more code and less composable — the `Annotated` type alias can be reused if we add another case-insensitive enum-like field later.

### Decision 2: Five canonical levels, no aliases

Accept only `DEBUG / INFO / WARNING / ERROR / CRITICAL`. Not `WARN` (deprecated stdlib alias), not `FATAL` (alias for `CRITICAL`), not `NOTSET`. Keeps the allowed set obvious and matches what every contributor types.

### Decision 3: Normalize on load, not on use

Store `log_level` as the uppercased string. `__main__.py:23` then passes it to `basicConfig` without calling `.upper()` again — we can remove that redundant `.upper()` as part of this change.

## Risks / Trade-offs

- **Existing `.env` files with lowercase values keep working** — case-insensitive normalization is explicit, so no one breaks on upgrade. Risk: low.
- **`LOG_LEVEL=20` (numeric) now fails** where it silently worked before via stdlib coercion. Mitigation: documented as a non-goal; nobody in this repo uses it.
