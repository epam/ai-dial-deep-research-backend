import json
from pathlib import Path

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
    assert properties.max_research_iterations == 5
    assert properties.max_research_graph_steps == 500
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


def test_non_positive_graph_steps_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate({**VALID_PROPERTIES, "max_research_graph_steps": 0})


def test_report_defaults_resolve_without_configuration() -> None:
    properties = ApplicationProperties.model_validate(VALID_PROPERTIES)
    sections = properties.default_report_structure
    assert [section.name for section in sections] == [
        "Overview",
        "Key Findings",
        "Detailed Analysis",
        "Conclusion",
        "References",
    ]
    assert [section.protected for section in sections] == [True, False, False, False, True]
    # Only the closing References section is the sources listing, and only it is exempt from the
    # word ceiling.
    assert [section.references_section for section in sections] == [
        False,
        False,
        False,
        False,
        True,
    ]
    assert properties.max_report_words == 2750
    assert properties.max_report_versions == 3


def test_empty_report_structure_is_rejected() -> None:
    data = {**VALID_PROPERTIES, "default_report_structure": []}
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert any(err["loc"] == ("default_report_structure",) for err in excinfo.value.errors())


@pytest.mark.parametrize("field", ["name", "description"])
def test_empty_report_section_field_is_rejected(field: str) -> None:
    section = {"name": "Summary", "description": "The answer.", "protected": True, field: ""}
    data = {**VALID_PROPERTIES, "default_report_structure": [section]}
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert any(
        err["loc"] == ("default_report_structure", 0, field) for err in excinfo.value.errors()
    )


def test_structure_with_no_protected_section_is_rejected() -> None:
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {"name": "Summary", "description": "The answer."},
            {"name": "Evidence", "description": "What the sources say."},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    message = str(excinfo.value)
    assert "default_report_structure" in message
    assert "at least one section with protected=true" in message


def test_a_references_section_before_the_last_one_is_rejected() -> None:
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {
                "name": "Sources",
                "description": "The cited sources.",
                "protected": True,
                "references_section": True,
            },
            {"name": "Summary", "description": "The answer."},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    message = str(excinfo.value)
    assert "only the last section may set references_section=true" in message
    assert "Sources" in message


def test_a_structure_with_no_references_section_is_accepted() -> None:
    # A deployment may configure a report that lists no sources; nothing is then exempt from the
    # word ceiling.
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {"name": "Summary", "description": "The answer.", "protected": True},
            {"name": "Outlook", "description": "What follows."},
        ],
    }
    sections = ApplicationProperties.model_validate(data).default_report_structure
    assert [section.references_section for section in sections] == [False, False]


def test_duplicate_report_section_names_are_rejected() -> None:
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {"name": "Summary", "description": "The answer.", "protected": True},
            {"name": "Summary", "description": "The answer again."},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert "duplicate report section name(s): ['Summary']" in str(excinfo.value)


def test_a_deployment_protects_a_section_of_its_own() -> None:
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {"name": "Summary", "description": "The answer."},
            {
                "name": "Regulatory disclaimer",
                "description": "The mandated wording, verbatim.",
                "protected": True,
            },
        ],
    }
    properties = ApplicationProperties.model_validate(data)
    assert [section.name for section in properties.default_report_structure] == [
        "Summary",
        "Regulatory disclaimer",
    ]
    assert properties.default_report_structure[1].protected is True


def test_non_positive_report_words_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate({**VALID_PROPERTIES, "max_report_words": 0})


def test_zero_report_versions_is_rejected() -> None:
    # Zero versions would mean no report at all; the minimum is one draft.
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate({**VALID_PROPERTIES, "max_report_versions": 0})


def test_one_report_version_is_accepted() -> None:
    # 1 delivers the first draft unreviewed: the version budget fails already for draft 1.
    properties = ApplicationProperties.model_validate(
        {**VALID_PROPERTIES, "max_report_versions": 1}
    )
    assert properties.max_report_versions == 1


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


def test_schema_inlines_report_section_items() -> None:
    schema = ApplicationProperties.model_json_schema()
    items = schema["properties"]["default_report_structure"]["items"]
    assert "$ref" not in items
    assert set(items["properties"]) == {
        "name",
        "description",
        "protected",
        "references_section",
    }


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


APPLICATIONS_TEMPLATE = Path(__file__).parent.parent / "dial_conf" / "core"
APPLICATIONS_TEMPLATE /= "applications-template.json"


def _template_channels() -> dict[str, dict]:
    return json.loads(APPLICATIONS_TEMPLATE.read_text(encoding="utf-8"))["applications"]


def test_applications_template_channels_validate() -> None:
    for name, channel in _template_channels().items():
        try:
            ApplicationProperties.model_validate(channel["applicationProperties"])
        except ValidationError as error:
            pytest.fail(f"channel {name} in the committed template is not valid: {error}")


def test_applications_template_sets_only_the_required_properties() -> None:
    # The template is an example of the file's shape, not a property reference: it supplies what
    # an operator must supply and nothing else, so a channel seeded from it follows the model's
    # defaults as they change. The reference is the model and `docs/generated-app-schema.json`.
    required = {
        name for name, field in ApplicationProperties.model_fields.items() if field.is_required()
    }
    for name, channel in _template_channels().items():
        assert set(channel["applicationProperties"]) == required, name


def test_schema_dial_root_keywords_absent_when_excluded() -> None:
    schema = ApplicationProperties.model_json_schema(include_dial_fields=False)
    assert "$id" not in schema
    assert "$schema" not in schema
    assert not any(key.startswith("dial:applicationType") for key in schema)
    # Per-property dial:meta blocks stay regardless of the root wrapper.
    assert schema["properties"]["prompts"]["dial:meta"]["dial:propertyKind"] == "server"
