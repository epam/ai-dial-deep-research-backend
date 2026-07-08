## ADDED Requirements

### Requirement: Validated log level setting

The `DialAppSettings` class SHALL expose a `log_level` field restricted to the five stdlib logging level names — `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Input matching is case-insensitive: the value SHALL be uppercased before comparison, and the normalized uppercase form SHALL be the loaded value. Any value that does not normalize to one of the five allowed names SHALL cause `DialAppSettings` instantiation to fail with a Pydantic `ValidationError` that identifies the `log_level` field.

#### Scenario: Default value loads
- **WHEN** `DialAppSettings()` is instantiated with no `LOG_LEVEL` environment variable set
- **THEN** `log_level` equals `"INFO"` and no validation error is raised

#### Scenario: Canonical uppercase value loads
- **WHEN** `LOG_LEVEL=DEBUG` is passed to `DialAppSettings`
- **THEN** `log_level` equals `"DEBUG"` and no validation error is raised

#### Scenario: Mixed-case value is normalized
- **WHEN** `LOG_LEVEL=warning` (or `Warning`, `WaRnInG`) is passed to `DialAppSettings`
- **THEN** `log_level` equals `"WARNING"` — the allowed uppercase form — with no validation error

#### Scenario: Unknown value is rejected
- **WHEN** `LOG_LEVEL=ifno` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `log_level` field
