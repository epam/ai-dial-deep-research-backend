import pytest
from pydantic import ValidationError

from dial_deep_research.app_properties import (
    APPLICATION_TYPE_DISPLAY_NAME,
    APPLICATION_TYPE_SCHEMA_ID,
    DIAL_META_SCHEMA,
    ApplicationProperties,
    MCPClientSettings,
)


@pytest.fixture
def direct_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a valid direct-mode connection-bundle env var."""
    monkeypatch.setenv(
        "MY_MCP_CONN", '{"url": "http://localhost:8000/mcp", "api_key": "resolved-secret"}'
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
    assert server.connection is None
    assert server.deployment_id == "generic-rag-mcp"
    assert server.tools_to_include == []


def test_direct_mode_server_loads(direct_mode: None) -> None:
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "connection": "$env:{MY_MCP_CONN}",
            "tools_to_include": ["search_docs"],
        }
    )
    bundle = server.direct_connection
    assert bundle.url.encoded_string() == "http://localhost:8000/mcp"
    assert bundle.api_key.get_secret_value() == "resolved-secret"
    assert server.tools_to_include == ["search_docs"]


def test_connection_and_deployment_id_together_are_rejected(direct_mode: None) -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {"server_name": "rag", "deployment_id": "x", "connection": "$env:{MY_MCP_CONN}"}
        )
    assert "cannot be set at the same time" in str(excinfo.value)


def test_no_mode_configured_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "rag"})
    assert "either deployment_id or connection must be set" in str(excinfo.value)


def test_empty_server_name_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "", "deployment_id": "x"})
    assert any(err["loc"] == ("server_name",) for err in excinfo.value.errors())


def test_plaintext_connection_is_rejected(direct_mode: None) -> None:
    # Inline values are refused: connection must be a $env:{VAR} placeholder.
    inline = '{"url": "http://localhost:8000/mcp", "api_key": "resolved-secret"}'
    with pytest.raises(ValidationError, match=r"\$env:\{VAR\} placeholder"):
        MCPClientSettings.model_validate({"server_name": "rag", "connection": inline})


def test_default_placeholder_form_is_rejected(direct_mode: None) -> None:
    # The $env:{VAR|default} form is not a valid placeholder -> refused.
    with pytest.raises(ValidationError, match=r"\$env:\{VAR\} placeholder"):
        MCPClientSettings.model_validate(
            {"server_name": "rag", "connection": "$env:{SOME_VAR|whatever}"}
        )


@pytest.mark.parametrize(
    "bundle, match",
    [
        ("not json at all", "Invalid JSON"),
        ('{"api_key": "k"}', "url"),  # missing url
        ('{"url": "http://localhost/mcp"}', "api_key"),  # missing api_key
        ('{"url": "ftp://localhost/mcp", "api_key": "k"}', "url"),  # non-http url
        ('{"url": "http://localhost/mcp", "api_key": ""}', "api_key"),  # empty api_key
        ('{"url": "http://localhost/mcp", "api_key": "k", "extra": 1}', "extra"),  # extra field
    ],
)
def test_malformed_connection_bundle_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bundle: str, match: str
) -> None:
    monkeypatch.setenv("MY_MCP_CONN", bundle)
    with pytest.raises(ValidationError, match=match):
        MCPClientSettings.model_validate({"server_name": "rag", "connection": "$env:{MY_MCP_CONN}"})


def test_unresolved_env_placeholder_fails_validation(
    direct_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISSING_CONN", raising=False)
    with pytest.raises(ValidationError, match="MISSING_CONN"):
        MCPClientSettings.model_validate(
            {"server_name": "rag", "connection": "$env:{MISSING_CONN}"}
        )


def test_connection_schema_is_plain_string() -> None:
    # The DIAL editor must accept the $env:{...} placeholder, so connection is a plain string
    # in the schema -- the JSON bundle shape is enforced in-app after expansion.
    schema = ApplicationProperties.model_json_schema()
    conn_schema = schema["properties"]["mcp_servers"]["items"]["properties"]["connection"]
    string_variant = next(v for v in conn_schema["anyOf"] if v.get("type") == "string")
    assert "format" not in string_variant or string_variant["format"] == "password"


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
