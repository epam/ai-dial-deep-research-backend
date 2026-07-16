"""The single settings model, all env-driven.

Env vars carry deployment concerns (endpoints, keys, ports, knobs). Everything
client-specific (prompt content, names, the iteration cap) is NOT here — it arrives
per request as DIAL application properties (see `app_properties.py`).

When adding a parameter, pick its home by this test: varies per environment for the
same client → env field here; varies per client on the same infrastructure →
`ApplicationProperties`.
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Annotated[
    Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    BeforeValidator(lambda v: v.upper() if isinstance(v, str) else v),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    # app server
    app_host: str = "0.0.0.0"
    app_port: int = 5000
    log_level: LogLevel = "INFO"

    # DIAL. Downstream DIAL Core calls authenticate with the per-request api-key, injected by
    # the SDK's header propagation (see `app/factory.py`), so there is no static key here.
    # Required — no built-in default, so a missing DIAL_URL fails fast at startup.
    dial_url: HttpUrl
    dial_app_name: str = "deep-research"
    heartbeat_interval: int = Field(default=5, ge=1)

    # When true, also register the playground chat completion (a single tool-calling agent over
    # the configured MCP servers, no clarification/research flow) for testing MCP tools.
    enable_playground_channel: bool = False

    # opik tracing
    opik_tracing_enabled: bool = False
    opik_project_name: str = Field(default="deep-research", min_length=1)


# Placeholder key for DIAL clients that need a credential at construction. The SDK's header
# propagation (DIALApp(propagate_auth_headers=True)) overwrites the outgoing api-key with the
# per-request key, so this value is never actually sent to DIAL Core.
PLACEHOLDER_API_KEY = "propagated-per-request"


# Instantiated at import so bad env fails at startup, not mid-request.
settings = Settings()
