import logging
import os
from enum import StrEnum
from typing import Any

from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from dial_deep_research.settings import PLACEHOLDER_API_KEY, settings

_log = logging.getLogger(__name__)


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
