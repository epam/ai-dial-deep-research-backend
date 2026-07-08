## Context

`src/dial_deep_research/app/factory.py:25` currently reads:

```python
app.add_chat_completion("echo", EchoCompletion(), heartbeat_interval=5)
```

The `5` is an undocumented integer with no configuration path. The freshly-added `app-config` capability (from `validate-log-level-setting`) now owns the typed, validated settings layer, so the natural home for this value is `DialAppSettings`. The echo handler never triggers heartbeats in practice (instant response), but future deep-research handlers will — making this a good moment to tidy the contract before real consumers appear.

## Goals / Non-Goals

**Goals:**
- Make the heartbeat interval env-tunable via `HEARTBEAT_INTERVAL`, with a sensible default of `5` seconds (preserves existing behavior).
- Reject nonsensical values (≤ 0) at settings-load time with a Pydantic error.
- Eliminate the magic literal from `factory.py`.

**Non-Goals:**
- Supporting "disabled" heartbeats (e.g. `HEARTBEAT_INTERVAL=0` meaning "off"). The DIAL SDK may accept `None` for that, but we have no use case today; a future change can extend the field to `int | None` under the same `app-config` capability.
- Touching other `add_chat_completion` arguments or the echo deployment name.
- Changing logging format, telemetry wiring, or unrelated settings.

## Decisions

### Decision 1: `Field(ge=1)` rather than `PositiveInt` or a custom validator

Use `heartbeat_interval: int = Field(default=5, ge=1, alias="HEARTBEAT_INTERVAL")`. `ge=1` is the most explicit and self-documenting: it says exactly what we mean (1 second or more) and produces a clean Pydantic error message listing the constraint. `PositiveInt` would also work but hides the bound inside a type alias, and a `@field_validator` is overkill for a single-line constraint.

### Decision 2: Default stays `5`, matching the removed literal

No behavior change for anyone who doesn't set the env var. Upgrading is a no-op.

### Decision 3: Document the env var in `.env.example`

`.env.example` already documents `LOG_LEVEL`, `APP_HOST`, etc. Adding `HEARTBEAT_INTERVAL=5` there — with a one-line comment explaining the unit (seconds) and the default — keeps the file as the single place contributors look to learn what's tunable.

## Risks / Trade-offs

- **Pydantic `int` coercion accepts strings like `"30"`** — that's actually what we want for env vars. Risk: none.
- **Breaking change for anyone already setting an undocumented `HEARTBEAT_INTERVAL=0`** — impossible today (the code ignored the env var). Risk: none.
