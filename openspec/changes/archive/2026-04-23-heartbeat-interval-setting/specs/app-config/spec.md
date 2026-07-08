## ADDED Requirements

### Requirement: Validated heartbeat interval setting

The `DialAppSettings` class SHALL expose a `heartbeat_interval` field of type `int` driven by the `HEARTBEAT_INTERVAL` environment variable, representing the seconds between keep-alive heartbeats emitted by the DIAL chat-completion endpoint during long-running responses. The field SHALL default to `5`. Only strictly positive integers SHALL be accepted; zero, negative, or non-integer values SHALL cause `DialAppSettings` instantiation to fail with a Pydantic `ValidationError` identifying the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` alias). The value SHALL be the sole source of the heartbeat interval passed to `app.add_chat_completion(...)` — no other hardcoded literal for this parameter SHALL remain in application code.

#### Scenario: Default value loads
- **WHEN** `DialAppSettings()` is instantiated with no `HEARTBEAT_INTERVAL` environment variable set
- **THEN** `heartbeat_interval` equals `5` and no validation error is raised

#### Scenario: Valid positive override loads
- **WHEN** `HEARTBEAT_INTERVAL=30` is passed to `DialAppSettings`
- **THEN** `heartbeat_interval` equals `30` (as `int`) and no validation error is raised

#### Scenario: Zero is rejected
- **WHEN** `HEARTBEAT_INTERVAL=0` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` env alias)

#### Scenario: Negative value is rejected
- **WHEN** `HEARTBEAT_INTERVAL=-1` is passed to `DialAppSettings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry references the `heartbeat_interval` field (or its `HEARTBEAT_INTERVAL` env alias)

#### Scenario: App factory consumes the setting
- **WHEN** `create_app()` registers the echo chat completion
- **THEN** the heartbeat interval passed to `app.add_chat_completion(...)` SHALL equal `dial_app_settings.heartbeat_interval`, and no integer literal for this parameter SHALL appear in `factory.py`
