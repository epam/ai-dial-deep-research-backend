import pytest
from pydantic import ValidationError

import dial_deep_research.utils.llm as llm_mod
from dial_deep_research.settings import PLACEHOLDER_API_KEY
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    LLMModelsEnum,
    ReasoningEffortEnum,
    VerbosityEnum,
    format_token_usage,
    get_chat_model,
)

_CACHE_POLICY_HEADER = "X-DIAL-CACHE-POLICY"


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


def test_format_token_usage_includes_cached_count() -> None:
    usage = {
        "input_tokens": 100,
        "output_tokens": 5,
        "total_tokens": 105,
        "input_token_details": {"cache_read": 80},
    }
    assert format_token_usage(usage) == "100/5/80"


def test_format_token_usage_defaults_cached_to_zero_without_details() -> None:
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert format_token_usage(usage) == "10/5/0"


def test_format_token_usage_none_is_graceful() -> None:
    assert format_token_usage(None) == "n/a"


def test_get_chat_model_sends_cache_policy_header_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_mod.settings, "llm_cache_policy", "cache-priority")
    model = get_chat_model(LLMModelConfig())
    assert model.default_headers is not None
    assert model.default_headers[_CACHE_POLICY_HEADER] == "cache-priority"


def test_get_chat_model_omits_cache_policy_header_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_mod.settings, "llm_cache_policy", None)
    model = get_chat_model(LLMModelConfig())
    assert not (model.default_headers or {}).get(_CACHE_POLICY_HEADER)
