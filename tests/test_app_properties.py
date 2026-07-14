import pytest
from pydantic import ValidationError

from dial_deep_research.app_properties import (
    APPLICATION_TYPE_DISPLAY_NAME,
    APPLICATION_TYPE_SCHEMA_ID,
    DIAL_META_SCHEMA,
    ApplicationProperties,
    MCPClientSettings,
)

VALID_PROPERTIES: dict = {
    "prompts": {
        "client_name": "Test Corp",
        "agent_name": "Test Deep Research",
        "data_sources_descriptions": "## report\n\nA report.",
    },
    "mcp_servers": [{"server_name": "rag", "deployment_id": "generic-rag-mcp"}],
}


def test_valid_properties_load_with_default_iterations() -> None:
    properties = ApplicationProperties.model_validate(VALID_PROPERTIES)
    assert properties.max_research_iterations == 10
    assert properties.prompts.client_name == "Test Corp"


@pytest.mark.parametrize("field", ["client_name", "agent_name", "data_sources_descriptions"])
def test_empty_prompt_string_is_rejected(field: str) -> None:
    data = {"prompts": {**VALID_PROPERTIES["prompts"], field: ""}}
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert any(err["loc"] == ("prompts", field) for err in excinfo.value.errors())


def test_missing_prompts_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate({})
    assert any(err["loc"] == ("prompts",) for err in excinfo.value.errors())


def test_non_positive_iterations_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate({**VALID_PROPERTIES, "max_research_iterations": 0})


def test_schema_root_properties_carry_dial_meta() -> None:
    schema = ApplicationProperties.model_json_schema()
    orders = []
    for prop_schema in schema["properties"].values():
        meta = prop_schema["dial:meta"]
        assert meta["dial:propertyKind"] == "server"
        orders.append(meta["dial:propertyOrder"])
    assert orders == list(range(1, len(schema["properties"]) + 1))


def test_schema_inlines_nested_models() -> None:
    schema = ApplicationProperties.model_json_schema()
    assert "$defs" not in schema
    prompts = schema["properties"]["prompts"]
    assert "$ref" not in prompts
    assert set(prompts["required"]) == {"client_name", "agent_name", "data_sources_descriptions"}


def test_schema_inlines_list_item_model() -> None:
    schema = ApplicationProperties.model_json_schema()
    items = schema["properties"]["mcp_servers"]["items"]
    assert "$ref" not in items
    assert set(items["required"]) == {"server_name"}
    assert "tools_to_include" in items["properties"]


def test_at_least_one_mcp_server_required() -> None:
    data = {**VALID_PROPERTIES, "mcp_servers": []}
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert any(err["loc"] == ("mcp_servers",) for err in excinfo.value.errors())


def test_duplicate_server_names_are_rejected() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {"server_name": "rag", "deployment_id": "a"},
            {"server_name": "rag", "deployment_id": "b"},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert "duplicate MCP server_name" in str(excinfo.value)


def test_deployment_mode_server_loads() -> None:
    server = MCPClientSettings.model_validate(
        {"server_name": "rag", "deployment_id": "generic-rag-mcp"}
    )
    assert server.url is None
    assert server.deployment_id == "generic-rag-mcp"
    assert server.tools_to_include == []


def test_direct_mode_server_loads() -> None:
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "url": "http://localhost:8000/mcp",
            "api_key": "secret",
            "tools_to_include": ["search_docs"],
        }
    )
    assert server.url is not None
    assert server.api_key is not None
    assert server.api_key.get_secret_value() == "secret"
    assert server.tools_to_include == ["search_docs"]


def test_url_and_deployment_id_together_are_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "deployment_id": "x",
                "url": "http://localhost:8000/mcp",
                "api_key": "secret",
            }
        )
    assert "cannot be set at the same time" in str(excinfo.value)


def test_direct_mode_requires_api_key() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "rag", "url": "http://localhost:8000/mcp"})
    assert "api_key is required" in str(excinfo.value)


def test_no_mode_configured_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "rag"})
    assert "either deployment_id or url + api_key" in str(excinfo.value)


def test_empty_server_name_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "", "deployment_id": "x"})
    assert any(err["loc"] == ("server_name",) for err in excinfo.value.errors())


def test_env_placeholders_in_url_and_api_key_are_expanded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_MCP_URL", "http://localhost:9000/mcp")
    monkeypatch.setenv("MY_MCP_KEY", "resolved-secret")
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "url": "$env:{MY_MCP_URL}",
            "api_key": "$env:{MY_MCP_KEY}",
        }
    )
    assert server.url is not None
    assert server.url.encoded_string() == "http://localhost:9000/mcp"
    assert server.api_key is not None
    assert server.api_key.get_secret_value() == "resolved-secret"


def test_env_placeholder_default_is_used_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "url": "http://localhost:8000/mcp",
            "api_key": "$env:{MISSING_KEY|fallback}",
        }
    )
    assert server.api_key is not None
    assert server.api_key.get_secret_value() == "fallback"


def test_unresolved_env_placeholder_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(ValidationError, match="MISSING_KEY"):
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "url": "http://localhost:8000/mcp",
                "api_key": "$env:{MISSING_KEY}",
            }
        )


def test_schema_dial_root_keywords_present_by_default() -> None:
    schema = ApplicationProperties.model_json_schema()
    assert schema["$schema"] == DIAL_META_SCHEMA
    assert schema["$id"] == APPLICATION_TYPE_SCHEMA_ID
    assert schema["dial:applicationTypeDisplayName"] == APPLICATION_TYPE_DISPLAY_NAME
    assert schema["dial:appendApplicationPropertiesHeader"] is False


def test_schema_dial_root_keywords_absent_when_excluded() -> None:
    schema = ApplicationProperties.model_json_schema(include_dial_fields=False)
    assert "$id" not in schema
    assert "$schema" not in schema
    assert not any(key.startswith("dial:applicationType") for key in schema)
    # Per-property dial:meta blocks stay regardless of the root wrapper.
    assert schema["properties"]["prompts"]["dial:meta"]["dial:propertyKind"] == "server"
