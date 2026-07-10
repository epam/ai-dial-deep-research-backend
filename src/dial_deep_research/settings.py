"""The single settings model, all env-driven.

Env vars carry deployment concerns (endpoints, keys, ports, knobs). Everything
client-specific (prompt content, names, the iteration cap) is NOT here — it arrives
per request as DIAL application properties (see `app_properties.py`).

When adding a parameter, pick its home by this test: varies per environment for the
same client → env field here; varies per client on the same infrastructure →
`ApplicationProperties`.
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, HttpUrl, SecretStr
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

    # DIAL
    dial_url: HttpUrl = HttpUrl("http://localhost:8080")
    dial_api_key: SecretStr = SecretStr("dial_api_key")
    dial_app_name: str = "deep-research"
    heartbeat_interval: int = Field(default=5, ge=1)

    # generic-RAG MCP server
    mcp_server_name: str = Field(min_length=1)
    mcp_url: HttpUrl
    mcp_api_key: SecretStr = Field(min_length=1)

    # opik tracing
    opik_tracing_enabled: bool = False
    opik_project_name: str = Field(default="deep-research", min_length=1)


# Instantiated at import so bad env fails at startup, not mid-request.
settings = Settings()
