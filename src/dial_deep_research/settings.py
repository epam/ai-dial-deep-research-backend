"""The single settings model, merging the two config sources.

Env vars carry deployment concerns (endpoints, keys, ports, knobs). The `channel`
field carries client-specific behavior (prompt content, names) and is always loaded
from the YAML at `channel_config_path` — env cannot override it.

When adding a parameter, pick its home by this test: varies per environment for the
same client → env field here; varies per client on the same infrastructure →
`ChannelConfig`.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dial_deep_research.channel_config import ChannelConfig

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

    # channel: everything client-specific, from the YAML file
    channel_config_path: Path
    channel: ChannelConfig

    @model_validator(mode="before")
    @classmethod
    def _load_channel(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Fill `channel` from the YAML file.

        Overwrites any env- or init-provided value, so the file stays the only
        source for channel config. If the path is missing, skip loading and let
        validation report the missing field.
        """
        path = data.get("channel_config_path")
        if path:
            data["channel"] = ChannelConfig.from_yaml(path)
        return data


# Instantiated at import so bad env or a missing/invalid channel config fails at
# startup, not mid-request.
settings = Settings()
