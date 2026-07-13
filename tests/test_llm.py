import pytest
from pydantic import ValidationError

from dial_deep_research.settings import PLACEHOLDER_API_KEY
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    LLMModelsEnum,
    ReasoningEffortEnum,
    VerbosityEnum,
    get_chat_model,
)


def test_model_config_rejects_invalid_reasoning_effort() -> None:
    with pytest.raises(ValidationError):
        LLMModelConfig(reasoning_effort="ULTRA")  # type: ignore[arg-type]


def test_model_config_rejects_invalid_verbosity() -> None:
    with pytest.raises(ValidationError):
        LLMModelConfig(verbosity="EXTREME")  # type: ignore[arg-type]


def test_model_config_accepts_valid_enum_strings() -> None:
    cfg = LLMModelConfig(reasoning_effort=ReasoningEffortEnum.MEDIUM, verbosity=VerbosityEnum.LOW)
    assert cfg.reasoning_effort is ReasoningEffortEnum.MEDIUM
    assert cfg.verbosity is VerbosityEnum.LOW


def test_deployment_id_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODELS_GPT_5_2_2025_12_11", "gpt-5.2-custom-deployment")
    assert LLMModelsEnum.GPT_5_2_2025_12_11.deployment_id == "gpt-5.2-custom-deployment"


def test_deployment_id_falls_back_to_enum_value_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_MODELS_GPT_5_2_2025_12_11", raising=False)
    assert LLMModelsEnum.GPT_5_2_2025_12_11.deployment_id == LLMModelsEnum.GPT_5_2_2025_12_11.value


def test_get_chat_model_wires_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODELS_GPT_5_2_2025_12_11", "gpt-5.2-2025-12-11")
    cfg = LLMModelConfig(
        deployment=LLMModelsEnum.GPT_5_2_2025_12_11,
        reasoning_effort=ReasoningEffortEnum.LOW,
        verbosity=VerbosityEnum.HIGH,
    )
    model = get_chat_model(cfg)
    assert model.deployment_name == "gpt-5.2-2025-12-11"
    assert model.reasoning_effort == ReasoningEffortEnum.LOW.value
    assert model.verbosity == VerbosityEnum.HIGH.value


def test_get_chat_model_uses_placeholder_api_key() -> None:
    # The real per-request key is injected by SDK header propagation; the client is only
    # ever constructed with the placeholder.
    model = get_chat_model(LLMModelConfig())
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == PLACEHOLDER_API_KEY
