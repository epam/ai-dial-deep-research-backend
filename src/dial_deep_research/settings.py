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

# DIAL Core cache routing retry policy, sent as the X-DIAL-CACHE-POLICY header. See the DIAL
# prompt-caching tutorial. `cache-priority` keeps retries on the cache-warm upstream;
# `availability-priority` fails over to another upstream (Core's own default when no header
# is sent).
CachePolicy = Literal["availability-priority", "cache-priority"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    # app server
    app_host: str = "0.0.0.0"
    app_port: int = 5000

    # logging (see `utils/logging_config.py` for how these feed the dictConfig).
    # `log_level` drives the root logger and every managed logger except the app's own;
    # `deep_research_log_level` pins the `dial_deep_research` logger independently.
    log_level: LogLevel = "INFO"
    deep_research_log_level: LogLevel = "INFO"
    log_format: str = (
        "%(levelprefix)s | %(asctime)s | %(process)d | %(name)s | %(otel_context)s%(message)s"
    )
    log_date_format: str = "%Y-%m-%d %H:%M:%S"
    # Payload-debugging switch (see the logging-policy spec). Off: no payload content in logs at
    # any level, and the payload-capable third-party loggers (openai/httpx/httpcore) are capped
    # at INFO. On: payload records are emitted at DEBUG, each string truncated to the cap below.
    # Local development only — never enable in a shared environment.
    log_payloads: bool = False
    log_payloads_max_length: int = Field(default=2000, ge=1)

    # DIAL. Downstream DIAL Core calls authenticate with the per-request api-key, injected by
    # the SDK's header propagation (see `app/factory.py`), so there is no static key here.
    # Required — no built-in default, so a missing DIAL_URL fails fast at startup.
    dial_url: HttpUrl
    dial_app_name: str = "deep-research"
    heartbeat_interval: int = Field(default=5, ge=1)

    # When set, every LLM call sends `X-DIAL-CACHE-POLICY` with this value so DIAL Core's
    # prompt-cache routing follows the chosen retry policy; unset sends no header and Core
    # applies its own default (`availability-priority`).
    llm_cache_policy: CachePolicy | None = None

    # Cap on image content blocks in any LLM request (see the image-budget spec). The
    # default matches Azure OpenAI's images-per-request limit (50, counted across the
    # conversation history) — documented for GPT-4o/GPT-4.1 and observed on the newer
    # models we run. Other providers differ — OpenAI's own API documents up to 1500 images
    # / 512 MB payload per request — and the values may change over time.
    max_context_images: int = Field(default=50, ge=1)

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
