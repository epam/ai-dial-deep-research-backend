## ADDED Requirements

### Requirement: DIAL SDK runs in pydantic v2 mode

The app SHALL ensure the DIAL SDK uses pydantic v2 models, consistent with the app's own pydantic v2 models (`ApplicationProperties`, `Settings`, LLM structured outputs).

The DIAL SDK selects its model backend from the `PYDANTIC_V2` environment variable, read once
**at import time**, and defaults to pydantic v1 when the variable is unset. The app SHALL
guarantee `PYDANTIC_V2=True` is set in the process environment before the first `aidial_sdk`
import, for every entry point — the running app, the test suite, and helper scripts. It SHALL
enforce this in code (not only via deployment configuration) at the earliest guaranteed import
point, and SHALL NOT override a `PYDANTIC_V2` value that is already set explicitly in the
environment.

#### Scenario: SDK models are pydantic v2 when the app runs

- **WHEN** the application package is imported and the DIAL SDK is subsequently imported
- **THEN** the SDK operates in pydantic v2 mode, so its request/response models are pydantic v2
  models consistent with the app's own models

#### Scenario: Flag is set even without deployment configuration

- **WHEN** the app, the test suite, or a helper script imports the application package in an
  environment where `PYDANTIC_V2` was not set (for example, tests, which do not load `.env`)
- **THEN** `PYDANTIC_V2` is `True` in the process environment before `aidial_sdk` is imported

#### Scenario: Explicit environment override is respected

- **WHEN** `PYDANTIC_V2` is already set to an explicit value in the environment before the
  application package is imported
- **THEN** the app SHALL NOT overwrite that value
