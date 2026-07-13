"""The single settings model, all env-driven.

Env vars carry deployment concerns (endpoints, keys, ports, knobs). Everything
client-specific (prompt content, names, the iteration cap) is NOT here — it arrives
per request as DIAL application properties (see `app_properties.py`).

When adding a parameter, pick its home by this test: varies per environment for the
same client → env field here; varies per client on the same infrastructure →
`ApplicationProperties`.
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, HttpUrl, SecretStr, model_validator
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

    # generic-RAG MCP server. Two mutually exclusive modes (see `_validate_mcp_mode`):
    #  - deployment: the MCP is a DIAL application reached through Core — set `mcp_deployment_name`.
    #  - local dev:  a directly-reachable MCP — set `mcp_url` (+ `mcp_api_key`).
    mcp_server_name: str = Field(min_length=1)
    mcp_deployment_name: str | None = None
    mcp_url: HttpUrl | None = None
    mcp_api_key: SecretStr | None = None

    # opik tracing
    opik_tracing_enabled: bool = False
    opik_project_name: str = Field(default="deep-research", min_length=1)

    @model_validator(mode="after")
    def _validate_mcp_mode(self) -> "Settings":
        """Require exactly one MCP mode: local-dev (`mcp_url` + key) or deployment (name)."""
        if self.mcp_url is not None:
            if not (self.mcp_api_key and self.mcp_api_key.get_secret_value()):
                raise ValueError("MCP_API_KEY is required when MCP_URL is set (local-dev mode)")
        elif not self.mcp_deployment_name:
            raise ValueError(
                "No MCP connection configured: set MCP_DEPLOYMENT_NAME (deployment mode) "
                "or MCP_URL and MCP_API_KEY (local-dev mode)"
            )
        return self


# Placeholder key for DIAL clients that need a credential at construction. The SDK's header
# propagation (DIALApp(propagate_auth_headers=True)) overwrites the outgoing api-key with the
# per-request key, so this value is never actually sent to DIAL Core.
PLACEHOLDER_API_KEY = "propagated-per-request"


# Instantiated at import so bad env fails at startup, not mid-request.
settings = Settings()
