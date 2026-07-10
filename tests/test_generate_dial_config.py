"""Unit tests for the pure conversion/merge/render logic in scripts/generate_dial_config.py."""

import json
from typing import Any

import generate_dial_config as gen
import pytest
from aidial_client.types.deployment import Deployment, Features
from aidial_client.types.model import ModelCapabilities, ModelInfo

REMOTE_URL = "https://remote-dial.example.com"
REMOTE_KEY = "remote-key"


def _deployment(model_id: str = "gpt-test", **overrides: Any) -> Deployment:
    data: dict[str, Any] = {
        "id": model_id,
        "object": "model",
        "model": model_id,
        "created_at": 0,
        **overrides,
    }
    return Deployment.model_validate(data)


def _model_info(model_id: str = "gpt-test", **overrides: Any) -> ModelInfo:
    data: dict[str, Any] = {
        "id": model_id,
        "model": model_id,
        "capabilities": {"chat_completion": True},
        **overrides,
    }
    return ModelInfo.model_validate(data)


CHAT_PAIR = (
    _deployment(
        display_name="GPT Test",
        description="A chat model.",
        features=Features(system_prompt=True, tools=True),
    ),
    _model_info(),
)

EMBEDDING_PAIR = (
    _deployment("text-embedding-test"),
    _model_info("text-embedding-test", capabilities={"embeddings": True}),
)

UNSUPPORTED_PAIR = (
    _deployment("image-gen-test"),
    _model_info("image-gen-test", capabilities={}),
)


def _convert(deployment: Deployment, info: ModelInfo) -> tuple[str, dict] | None:
    return gen.to_config_model(deployment, info, remote_url=REMOTE_URL, remote_api_key=REMOTE_KEY)


def _template() -> dict:
    return {
        "models": {},
        "applications": {},
        "routes": {},
        "keys": {"dial_api_key": {"project": "deep-research", "role": "default"}},
        "roles": {"default": {"limits": {}}},
    }


def test_chat_model_routes_through_local_adapter_with_remote_upstream() -> None:
    result = _convert(*CHAT_PAIR)
    assert result is not None
    model_id, entry = result
    assert model_id == "gpt-test"
    assert entry["type"] == "chat"
    assert entry["endpoint"] == (
        "http://ai-dial-adapter-dial:5000/openai/deployments/gpt-test/chat/completions"
    )
    assert entry["upstreams"] == [
        {
            "endpoint": f"{REMOTE_URL}/openai/deployments/gpt-test/chat/completions",
            "key": REMOTE_KEY,
        }
    ]


def test_chat_model_copies_display_metadata_and_features() -> None:
    result = _convert(*CHAT_PAIR)
    assert result is not None
    _, entry = result
    assert entry["displayName"] == "GPT Test"
    assert entry["description"] == "A chat model."
    assert entry["features"] == {"systemPromptSupported": True, "toolsSupported": True}


def test_limits_are_mapped_to_camel_case() -> None:
    # DIAL Core parses its config strictly: snake_case limit keys make it fail to start.
    info = _model_info(limits={"max_prompt_tokens": 1048576, "max_completion_tokens": 65536})
    result = _convert(_deployment(), info)
    assert result is not None
    _, entry = result
    assert entry["limits"] == {"maxPromptTokens": 1048576, "maxCompletionTokens": 65536}


def test_max_total_tokens_limit_is_mapped() -> None:
    result = _convert(_deployment(), _model_info(limits={"max_total_tokens": 200000}))
    assert result is not None
    _, entry = result
    assert entry["limits"] == {"maxTotalTokens": 200000}


def test_empty_limits_are_omitted() -> None:
    result = _convert(*CHAT_PAIR)
    assert result is not None
    _, entry = result
    assert "limits" not in entry


def test_embedding_model_uses_embeddings_path() -> None:
    result = _convert(*EMBEDDING_PAIR)
    assert result is not None
    model_id, entry = result
    assert model_id == "text-embedding-test"
    assert entry["type"] == "embedding"
    assert entry["endpoint"].endswith("/openai/deployments/text-embedding-test/embeddings")


def test_model_without_chat_or_embedding_capability_is_skipped() -> None:
    assert _convert(*UNSUPPORTED_PAIR) is None


def test_model_without_capabilities_is_skipped() -> None:
    info = ModelInfo.model_validate({"id": "no-caps", "model": "no-caps"})
    assert _convert(_deployment("no-caps"), info) is None


def test_configuration_feature_maps_to_adapter_endpoint() -> None:
    features = Features(configuration=True)
    config = gen.features_to_config(features, deployment_id="conf-model")
    assert config == {
        "configurationEndpoint": (
            "http://ai-dial-adapter-dial:5000/openai/deployments/conf-model/configuration"
        )
    }


def test_capabilities_type_detection_prefers_chat() -> None:
    capabilities = ModelCapabilities(chat_completion=True, embeddings=True)
    result = _convert(_deployment(), _model_info(capabilities=capabilities.model_dump()))
    assert result is not None
    assert result[1]["type"] == "chat"


def test_build_config_merges_models_and_rebuilds_default_role_limits() -> None:
    template = _template()
    config = gen.build_config(
        template,
        [CHAT_PAIR, EMBEDDING_PAIR, UNSUPPORTED_PAIR],
        remote_url=REMOTE_URL,
        remote_api_key=REMOTE_KEY,
    )
    assert set(config["models"]) == {"gpt-test", "text-embedding-test"}
    assert config["roles"]["default"]["limits"] == {"gpt-test": {}, "text-embedding-test": {}}
    assert config["keys"] == {"dial_api_key": {"project": "deep-research", "role": "default"}}
    # The input template is not mutated.
    assert template["models"] == {}
    assert template["roles"]["default"]["limits"] == {}


def test_build_config_keeps_template_models_in_limits() -> None:
    template = _template()
    template["models"]["local-test-model"] = {"type": "chat", "endpoint": "http://host:1/x"}
    config = gen.build_config(
        template, [CHAT_PAIR], remote_url=REMOTE_URL, remote_api_key=REMOTE_KEY
    )
    assert set(config["models"]) == {"local-test-model", "gpt-test"}
    assert set(config["roles"]["default"]["limits"]) == {"local-test-model", "gpt-test"}


def test_substitute_placeholders_replaces_known_tokens() -> None:
    result = gen.substitute_placeholders("port=$env:{APP_PORT}!", {"APP_PORT": "5001"})
    assert result == "port=5001!"


def test_substitute_placeholders_rejects_unknown_tokens() -> None:
    with pytest.raises(ValueError, match=r"\$env:\{UNKNOWN\}"):
        gen.substitute_placeholders("$env:{UNKNOWN}", {"APP_PORT": "5001"})


def test_committed_schemas_template_renders_with_custom_port() -> None:
    template_text = gen.DEFAULT_SCHEMAS_TEMPLATE.read_text(encoding="utf-8")
    rendered = gen.render_application_schemas(template_text, app_port="5001")
    assert "$env:" not in rendered
    entry = json.loads(rendered)["applicationTypeSchemas"][0]
    assert entry["dial:applicationTypeCompletionEndpoint"] == (
        "http://host.docker.internal:5001/openai/deployments/deep-research/chat/completions"
    )
    assert entry["dial:applicationTypeSchemaEndpoint"] == (
        "http://host.docker.internal:5001/v1/configuration-support/application-schema"
    )
