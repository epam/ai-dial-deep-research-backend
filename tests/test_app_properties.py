import pytest
from pydantic import ValidationError

from dial_deep_research.app_properties import (
    APPLICATION_TYPE_DISPLAY_NAME,
    APPLICATION_TYPE_SCHEMA_ID,
    DIAL_META_SCHEMA,
    ApplicationProperties,
)

VALID_PROPERTIES: dict = {
    "prompts": {
        "client_name": "Test Corp",
        "agent_name": "Test Deep Research",
        "data_sources_descriptions": "## report\n\nA report.",
    },
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
