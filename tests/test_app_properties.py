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


# Every server entry must declare the References table its cited sources are listed in.
_DOCUMENTS_TABLE: dict = {
    "title": "Documents",
    "columns": [{"heading": "Title", "key": "publication_title"}],
}

_DATASETS_TABLE: dict = {
    "title": "Datasets",
    "columns": [{"heading": "Datasets", "key": "name"}],
}


VALID_PROPERTIES: dict = {
    "prompts": {
        "client_name": "Test Corp",
        "agent_name": "Test Deep Research",
        "data_sources_descriptions": "## report\n\nA report.",
    },
    "mcp_servers": [
        {
            "server_name": "rag",
            "server_type": "generic_rag",
            "references_table": {
                "title": "Documents",
                "columns": [{"heading": "Documents", "key": "publication_title"}],
            },
            "deployment_id": "generic-rag-mcp",
            "file_sharing_tool": "get_citation_url",
            "document_metadata_resource": "documents://metadata/{document_ids}",
            "document_title_key": "publication_title",
        }
    ],
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
    assert set(items["required"]) == {"server_name", "server_type", "references_table"}
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


def test_a_server_must_declare_its_type() -> None:
    """The supported types are a closed list, so a server cannot be left unlabelled."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate({"server_name": "rag", "deployment_id": "x"})
    assert any(err["loc"] == ("server_type",) for err in excinfo.value.errors())


def test_an_unsupported_server_type_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {"server_name": "rag", "server_type": "web_search", "deployment_id": "x"}
        )
    assert any(err["loc"] == ("server_type",) for err in excinfo.value.errors())


def test_one_server_of_each_type_is_accepted() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "dataset_metadata_tool": "list_datasets",
            },
        ],
    }
    properties = ApplicationProperties.model_validate(data)
    assert [server.server_type for server in properties.mcp_servers] == [
        "generic_rag",
        "statgpt",
    ]


def test_two_servers_of_one_type_are_rejected() -> None:
    """Each server numbers its own content, and a citation never says which one issued an id."""
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "rag-a",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
            {
                "server_name": "rag-b",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "b",
                "file_sharing_tool": "get_citation_url",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    message = str(excinfo.value)
    assert "at most one MCP server of each type" in message
    assert "generic_rag" in message
    assert "rag-a" in message and "rag-b" in message


def test_two_dataset_servers_are_rejected_too() -> None:
    """A dataset id is resolved back against the configured dataset server, so two of them
    shipping the same id would let a pill open the wrong dataset's page."""
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "stat-a",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "a",
                "dataset_metadata_tool": "list_datasets",
            },
            {
                "server_name": "stat-b",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "dataset_metadata_tool": "list_datasets",
            },
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert "statgpt" in str(excinfo.value)


def test_a_document_server_must_name_its_file_sharing_tool() -> None:
    """Without it every document citation ships as plain text, which is a broken server."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "deployment_id": "x",
                "references_table": _DOCUMENTS_TABLE,
            }
        )
    assert "must name its file_sharing_tool" in str(excinfo.value)


def test_a_dataset_server_may_leave_the_file_sharing_tool_unset() -> None:
    """A dataset is not a file, so there is nothing for it to share."""
    server = MCPClientSettings.model_validate(
        {
            "server_name": "datasets",
            "server_type": "statgpt",
            "references_table": {
                "title": "Datasets",
                "columns": [{"heading": "Datasets", "key": "name"}],
            },
            "deployment_id": "x",
            "dataset_metadata_tool": "list_datasets",
        }
    )
    assert server.file_sharing_tool is None


def test_a_server_with_no_connection_reports_that_before_the_missing_tool() -> None:
    """A server that cannot be reached at all is the more fundamental misconfiguration."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": _DOCUMENTS_TABLE,
            }
        )
    assert "either deployment_id or connection must be set" in str(excinfo.value)


def test_one_server_may_name_a_file_sharing_tool() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "share_documents",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "dataset_metadata_tool": "list_datasets",
            },
        ],
    }
    properties = ApplicationProperties.model_validate(data)
    assert properties.file_sharing_tool == "share_documents"


def test_no_server_naming_one_switches_inline_citations_off() -> None:
    """A dataset-only configuration names none: it has no documents to make readable."""
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "a",
                "dataset_metadata_tool": "list_datasets",
            }
        ],
    }
    assert ApplicationProperties.model_validate(data).file_sharing_tool is None


def test_only_a_document_server_may_name_a_file_sharing_tool() -> None:
    """The tool makes a cited document readable, and the documents come from one server.

    With at most one server per type, this is also what keeps a second server from naming a
    tool at all, so no separate cross-server check is needed.
    """
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "file_sharing_tool": "copy_to_user",
            }
        )
    message = str(excinfo.value)
    assert "only a generic_rag server may set file_sharing_tool" in message
    assert "statgpt" in message


def test_no_configuration_can_name_two_file_sharing_tools() -> None:
    """A consequence of the two rules rather than a check of its own: only the document server
    may name a tool, and only one document server may be configured."""
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "file_sharing_tool": "copy_to_user",
            },
        ],
    }
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate(data)


def test_duplicate_server_names_are_rejected() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
                "document_metadata_resource": "documents://metadata/{document_ids}",
                "document_title_key": "publication_title",
            },
            {
                "server_name": "rag",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "dataset_metadata_tool": "list_datasets",
            },
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ApplicationProperties.model_validate(data)
    assert "duplicate MCP server_name" in str(excinfo.value)


def test_deployment_mode_server_loads() -> None:
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "server_type": "generic_rag",
            "references_table": {
                "title": "Documents",
                "columns": [{"heading": "Documents", "key": "publication_title"}],
            },
            "deployment_id": "generic-rag-mcp",
            "file_sharing_tool": "get_citation_url",
            "document_metadata_resource": "documents://metadata/{document_ids}",
            "document_title_key": "publication_title",
        }
    )
    assert server.connection is None
    assert server.deployment_id == "generic-rag-mcp"
    assert server.tools_to_include == []


def test_direct_mode_server_loads(direct_mode: None) -> None:
    server = MCPClientSettings.model_validate(
        {
            "server_name": "rag",
            "server_type": "generic_rag",
            "references_table": {
                "title": "Documents",
                "columns": [{"heading": "Documents", "key": "publication_title"}],
            },
            "connection": "$env:{MY_MCP_CONN}",
            "tools_to_include": ["search_docs"],
            "file_sharing_tool": "get_citation_url",
            "document_metadata_resource": "documents://metadata/{document_ids}",
            "document_title_key": "publication_title",
        }
    )
    bundle = server.direct_connection
    assert bundle.url.encoded_string() == "http://localhost:8000/mcp"
    assert bundle.api_key.get_secret_value() == "resolved-secret"
    assert server.tools_to_include == ["search_docs"]


def test_connection_and_deployment_id_together_are_rejected(direct_mode: None) -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "x",
                "connection": "$env:{MY_MCP_CONN}",
            }
        )
    assert "cannot be set at the same time" in str(excinfo.value)


def test_no_mode_configured_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": _DOCUMENTS_TABLE,
            }
        )
    assert "either deployment_id or connection must be set" in str(excinfo.value)


def test_empty_server_name_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {"server_name": "", "server_type": "generic_rag", "deployment_id": "x"}
        )
    assert any(err["loc"] == ("server_name",) for err in excinfo.value.errors())


def test_plaintext_connection_is_rejected(direct_mode: None) -> None:
    # Inline values are refused: connection must be a $env:{VAR} placeholder.
    inline = '{"url": "http://localhost:8000/mcp", "api_key": "resolved-secret"}'
    with pytest.raises(ValidationError, match=r"\$env:\{VAR\} placeholder"):
        MCPClientSettings.model_validate(
            {"server_name": "rag", "server_type": "generic_rag", "connection": inline}
        )


def test_default_placeholder_form_is_rejected(direct_mode: None) -> None:
    # The $env:{VAR|default} form is not a valid placeholder -> refused.
    with pytest.raises(ValidationError, match=r"\$env:\{VAR\} placeholder"):
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "connection": "$env:{SOME_VAR|whatever}",
            }
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
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "connection": "$env:{MY_MCP_CONN}",
            }
        )


def test_unresolved_env_placeholder_fails_validation(
    direct_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISSING_CONN", raising=False)
    with pytest.raises(ValidationError, match="MISSING_CONN"):
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "connection": "$env:{MISSING_CONN}",
            }
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


_TITLE_SOURCE = {
    "document_metadata_resource": "documents://metadata/{document_ids}",
    "document_title_key": "publication_title",
}


def _document_server(**overrides: object) -> dict[str, object]:
    return {
        "server_name": "rag",
        "server_type": "generic_rag",
        "references_table": {
            "title": "Documents",
            "columns": [{"heading": "Documents", "key": "publication_title"}],
        },
        "deployment_id": "a",
        "file_sharing_tool": "get_citation_url",
        **_TITLE_SOURCE,
        **overrides,
    }


def test_a_document_server_may_name_where_its_titles_come_from() -> None:
    server = MCPClientSettings.model_validate(_document_server(**_TITLE_SOURCE))
    source = server.document_metadata
    assert source is not None
    assert source.server_name == "rag"
    assert source.resource_template == "documents://metadata/{document_ids}"
    assert source.title_key == "publication_title"


def test_a_document_server_naming_no_title_source_is_rejected() -> None:
    """A document id means nothing outside its server, so a pill labelled from one names
    nothing the reader can place."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
            }
        )
    assert "must name its document_metadata_resource and document_title_key" in str(excinfo.value)


@pytest.mark.parametrize("field", ["document_metadata_resource", "document_title_key"])
def test_one_title_field_without_the_other_is_rejected(field: str) -> None:
    """A half-configured pair gets an error of its own: a URI with no key names nothing to take."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "rag",
                "server_type": "generic_rag",
                "references_table": {
                    "title": "Documents",
                    "columns": [{"heading": "Documents", "key": "publication_title"}],
                },
                "deployment_id": "a",
                "file_sharing_tool": "get_citation_url",
                field: _TITLE_SOURCE[field],
            }
        )
    assert "set together or not at all" in str(excinfo.value)


@pytest.mark.parametrize(
    "template",
    [
        "documents://metadata/",
        "documents://metadata/{ids}",
        "documents://{document_ids}/{document_ids}",
    ],
)
def test_a_template_without_exactly_one_placeholder_is_rejected(template: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            _document_server(document_metadata_resource=template, document_title_key="t")
        )
    assert "{document_ids} placeholder exactly once" in str(excinfo.value)


@pytest.mark.parametrize("field", ["document_metadata_resource", "document_title_key"])
def test_only_a_document_server_may_name_a_title_source(field: str) -> None:
    """A dataset server has no documents to title, so a source named there would never be read."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                field: _TITLE_SOURCE[field],
            }
        )
    assert "only a generic_rag server may set" in str(excinfo.value)


def test_properties_expose_the_one_configured_title_source() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            _document_server(**_TITLE_SOURCE),
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "references_table": {
                    "title": "Datasets",
                    "columns": [{"heading": "Datasets", "key": "name"}],
                },
                "deployment_id": "b",
                "dataset_metadata_tool": "list_datasets",
            },
        ],
    }
    source = ApplicationProperties.model_validate(data).document_metadata
    assert source is not None
    assert source.title_key == "publication_title"


def test_properties_expose_no_title_source_when_no_document_server_is_configured() -> None:
    """A document server must name one, so `None` means this channel serves no documents."""
    data = {**VALID_PROPERTIES, "mcp_servers": [_dataset_server()]}
    assert ApplicationProperties.model_validate(data).document_metadata is None


def test_the_pill_title_budget_has_a_default() -> None:
    properties = ApplicationProperties.model_validate(VALID_PROPERTIES)
    assert properties.max_pill_title_chars == 20


def test_a_channel_may_narrow_the_pill_title_budget() -> None:
    data = {**VALID_PROPERTIES, "max_pill_title_chars": 12}
    assert ApplicationProperties.model_validate(data).max_pill_title_chars == 12


def test_a_channel_may_switch_pill_shortening_off() -> None:
    """Null shows every title whole, for a client with the room or one that shortens itself."""
    data = {**VALID_PROPERTIES, "max_pill_title_chars": None}
    assert ApplicationProperties.model_validate(data).max_pill_title_chars is None


def test_a_pill_title_budget_too_small_to_be_useful_is_rejected() -> None:
    """Below the floor a shortened title is an ellipsis and a letter or two."""
    with pytest.raises(ValidationError):
        ApplicationProperties.model_validate({**VALID_PROPERTIES, "max_pill_title_chars": 3})


# --- the dataset-metadata tool ------------------------------------------------------------------


def _dataset_server(**overrides: object) -> dict[str, object]:
    return {
        "server_name": "datasets",
        "server_type": "statgpt",
        "references_table": {
            "title": "Datasets",
            "columns": [{"heading": "Datasets", "key": "name"}],
        },
        "deployment_id": "b",
        "dataset_metadata_tool": "list_datasets",
        **overrides,
    }


def test_a_dataset_server_may_name_its_dataset_metadata_tool() -> None:
    server = MCPClientSettings.model_validate(
        _dataset_server(dataset_metadata_tool="list_datasets")
    )
    assert server.dataset_metadata_tool == "list_datasets"


def test_a_dataset_server_naming_no_dataset_metadata_tool_is_rejected() -> None:
    """Without the tool every dataset citation ships as a bare URN, which opens nothing."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "deployment_id": "b",
                "references_table": _DATASETS_TABLE,
            }
        )
    assert "must name its dataset_metadata_tool" in str(excinfo.value)


def test_only_a_dataset_server_may_name_a_dataset_metadata_tool() -> None:
    """A document server serves no datasets, so a tool named there would never be called."""
    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(_document_server(dataset_metadata_tool="list_datasets"))
    assert "only a statgpt server may set dataset_metadata_tool" in str(excinfo.value)


def test_properties_expose_the_one_configured_dataset_metadata_tool() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            _document_server(),
            _dataset_server(dataset_metadata_tool="list_datasets"),
        ],
    }
    assert ApplicationProperties.model_validate(data).dataset_metadata_tool == "list_datasets"


def test_properties_expose_no_dataset_metadata_tool_when_no_dataset_server_is_configured() -> None:
    """A dataset server must name one, so `None` means this channel serves no datasets."""
    data = {**VALID_PROPERTIES, "mcp_servers": [_document_server()]}
    assert ApplicationProperties.model_validate(data).dataset_metadata_tool is None


# --- the References table each server declares ---------------------------------------------------


def _server(**overrides: object) -> dict:
    data: dict = {
        "server_name": "rag",
        "server_type": "generic_rag",
        "deployment_id": "x",
        "file_sharing_tool": "get_citation_url",
        "document_metadata_resource": "documents://metadata/{document_ids}",
        "document_title_key": "publication_title",
        "references_table": _DOCUMENTS_TABLE,
    }
    data.update(overrides)
    return data


def test_a_server_without_a_references_table_is_rejected() -> None:
    """A server whose cited sources cannot be listed is a broken channel, not a choice."""
    data = _server()
    del data["references_table"]

    with pytest.raises(ValidationError) as excinfo:
        MCPClientSettings.model_validate(data)

    assert any(err["loc"] == ("references_table",) for err in excinfo.value.errors())


@pytest.mark.parametrize(
    ("table", "case"),
    [
        ({"title": "", "columns": [{"heading": "Title", "key": "t"}]}, "the title is empty"),
        ({"title": "Documents", "columns": []}, "there are no columns"),
        (
            {"title": "Documents", "columns": [{"heading": "", "key": "t"}]},
            "a column heading is empty",
        ),
        (
            {"title": "Documents", "columns": [{"heading": "Title", "key": ""}]},
            "a column key is empty",
        ),
    ],
)
def test_an_unusable_references_table_is_rejected(table: dict, case: str) -> None:
    with pytest.raises(ValidationError):
        MCPClientSettings.model_validate(_server(references_table=table))
    assert case  # names the case under test


def test_the_configured_column_order_is_preserved() -> None:
    """The order is behavior: the first column is the one that falls back to the identifier."""
    table = {
        "title": "Documents",
        "columns": [
            {"heading": "Publication", "key": "publication_title"},
            {"heading": "Published", "key": "publication_date"},
        ],
    }

    server = MCPClientSettings.model_validate(_server(references_table=table))

    assert [c.heading for c in server.references_table.columns] == ["Publication", "Published"]
    assert [c.key for c in server.references_table.columns] == [
        "publication_title",
        "publication_date",
    ]


def test_the_title_key_and_the_first_column_are_independent() -> None:
    """The pill's title exists whether or not the structure declares a references section, so
    the two are configured apart and may name different keys."""
    table = {"title": "Documents", "columns": [{"heading": "Name", "key": "document_name"}]}

    server = MCPClientSettings.model_validate(
        _server(document_title_key="publication_title", references_table=table)
    )

    assert server.document_title_key == "publication_title"
    assert server.references_table.columns[0].key == "document_name"


def test_a_table_is_required_even_with_no_references_section_configured() -> None:
    data = {
        **VALID_PROPERTIES,
        "default_report_structure": [
            {"name": "Summary", "description": "The answer.", "protected": True}
        ],
    }

    properties = ApplicationProperties.model_validate(data)

    assert properties.default_report_structure[-1].references_section is False
    assert properties.mcp_servers[0].references_table.title == "Documents"


def test_the_references_tables_follow_the_configured_server_order() -> None:
    data = {
        **VALID_PROPERTIES,
        "mcp_servers": [
            {
                "server_name": "datasets",
                "server_type": "statgpt",
                "deployment_id": "statgpt-mcp",
                "dataset_metadata_tool": "list_datasets",
                "references_table": _DATASETS_TABLE,
            },
            _server(),
        ],
    }

    tables = ApplicationProperties.model_validate(data).references_tables

    assert [t.table.title for t in tables] == ["Datasets", "Documents"]
    assert [t.source_kind for t in tables] == ["dataset", "document"]
