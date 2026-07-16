import logging
import os
import random
from enum import StrEnum
from typing import Any

import httpx
from langchain.agents.middleware import ModelRetryMiddleware
from langchain_core.runnables import Runnable
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from dial_deep_research.settings import PLACEHOLDER_API_KEY, settings

_log = logging.getLogger(__name__)

# A connection dying after response headers arrived surfaces as one of these raw httpx errors.
# The OpenAI client's max_retries covers only failures before a response starts, so every LLM
# call site retries these itself (see the helpers below).
TRANSIENT_STREAM_DROP_ERRORS: tuple[type[Exception], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
)

# Per LLM call: 2 retries (3 attempts total), exponential backoff with jitter.
STREAM_DROP_MAX_RETRIES = 2
STREAM_DROP_MAX_ATTEMPTS = STREAM_DROP_MAX_RETRIES + 1
_STREAM_DROP_INITIAL_DELAY = 1.0


def stream_drop_retry_middleware() -> ModelRetryMiddleware:
    """Agent middleware retrying model calls that fail on a transient stream drop.

    ``on_failure="error"`` re-raises the exhausted failure so it reaches the DIAL error
    protocol instead of being injected as synthetic model output.
    """
    return ModelRetryMiddleware(
        max_retries=STREAM_DROP_MAX_RETRIES,
        retry_on=TRANSIENT_STREAM_DROP_ERRORS,
        on_failure="error",
        initial_delay=_STREAM_DROP_INITIAL_DELAY,
    )


def with_stream_drop_retry[I, O](runnable: Runnable[I, O]) -> Runnable[I, O]:
    """Retry a non-streaming runnable call on transient stream drops."""
    return runnable.with_retry(
        retry_if_exception_type=TRANSIENT_STREAM_DROP_ERRORS,
        stop_after_attempt=STREAM_DROP_MAX_ATTEMPTS,
        exponential_jitter_params={"initial": _STREAM_DROP_INITIAL_DELAY},
    )


def stream_drop_retry_delay(retry_number: int) -> float:
    """Seconds to wait before retry ``retry_number`` (0-based): exponential with jitter.

    For hand-rolled retry loops (streaming calls, which ``with_retry`` does not cover);
    mirrors the middleware's backoff.
    """
    return _STREAM_DROP_INITIAL_DELAY * (2**retry_number) + random.uniform(0.0, 0.5)


class ReasoningEffortEnum(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class VerbosityEnum(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LLMModelsEnum(StrEnum):
    GPT_5_4_2026_03_05 = "gpt-5.4-2026-03-05"
    GPT_5_4_2026_03_05_REASONING = "gpt-5.4-2026-03-05-reasoning"
    GPT_5_2_2025_12_11 = "gpt-5.2-2025-12-11"
    CLAUDE_OPUS_4_6 = "anthropic.claude-opus-4-6-v1"
    CLAUDE_SONNET_4_6 = "anthropic.claude-sonnet-4-6"

    @property
    def deployment_id(self) -> str:
        return os.getenv(f"LLM_MODELS_{self.name}", self.value)


_API_VERSION = "2025-04-01-preview"


class LLMModelConfig(BaseModel):
    deployment: LLMModelsEnum = Field(default=LLMModelsEnum.GPT_5_4_2026_03_05)
    reasoning_effort: ReasoningEffortEnum | None = Field(default=None)
    verbosity: VerbosityEnum | None = Field(default=None)


def get_chat_model(model_config: LLMModelConfig) -> AzureChatOpenAI:
    params: dict[str, Any] = {
        "azure_endpoint": settings.dial_url.encoded_string(),
        "api_version": _API_VERSION,
        "azure_deployment": model_config.deployment.deployment_id,
        # The per-request api-key is injected by the SDK's header propagation; this
        # placeholder only satisfies the client's construction-time requirement.
        "api_key": SecretStr(PLACEHOLDER_API_KEY),
        "max_retries": 3,
    }
    params.update(model_config.model_dump(mode="json", exclude_none=True, exclude={"deployment"}))
    _log.info(f"Creating chat model with params: {params}")
    return AzureChatOpenAI.model_validate(params)
