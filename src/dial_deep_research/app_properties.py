"""Per-instance application configuration, delivered as DIAL application properties.

The code ships channel-agnostic; everything specific to one application instance
("channel") — the client wording in prompts, the topics map, the iteration cap —
lives in DIAL Core as the instance's `applicationProperties`, validated against the
JSON schema generated from these models. DIAL Core (>= 0.41.0) fetches that schema
from the app's schema endpoint; `docs/generated-app-schema.json` is the committed
artifact of the same schema, kept in sync by `scripts/dump_app_schema.py`.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

# Fixed deployment id the chat completion is registered under. Every application
# instance of the Deep Research type routes here; per-instance behavior comes from
# the fetched application properties, not from the deployment id.
DEPLOYMENT_NAME = "deep-research"

# The DIAL application-type meta-schema and this type's identity within it. The
# `$id` is a generic placeholder: instances reference the type by this value, and
# the DIAL Core `applicationTypeSchemas` entry must carry the same one.
DIAL_META_SCHEMA = "https://dial.epam.com/application_type_schemas/schema#"
APPLICATION_TYPE_SCHEMA_ID = "https://mydial.epam.com/custom_application_schemas/deep-research"
APPLICATION_TYPE_DISPLAY_NAME = "Deep Research"


class Prompts(BaseModel):
    """Per-instance content injected into the prompt templates."""

    client_name: str = Field(
        min_length=1,
        description="Name of the client using the Deep Research",
    )
    agent_name: str = Field(
        min_length=1,
        description="Name the agent uses to introduce itself in prompts",
    )
    data_sources_descriptions: str = Field(
        min_length=1,
        description="A topics map of the data sources available in the knowledge base",
    )


class ApplicationProperties(BaseModel):
    """One application instance's configuration ("channel")."""

    max_research_iterations: int = Field(
        default=10,
        ge=1,
        description="Max number of research iterations (researcher → reviewer loops) before"
        " the report is forced",
    )
    prompts: Prompts

    @classmethod
    def model_json_schema(  # type: ignore[override]
        cls, *args: Any, include_dial_fields: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        """Generate the DIAL application-type schema for this model.

        Root properties get a `dial:meta` block (`dial:propertyKind`, `dial:propertyOrder`)
        the DIAL editor reads. With `include_dial_fields`, the root also carries the type
        identity (`$id`, `$schema`, display name, header flag); the schema endpoint serves
        the schema without it, because DIAL Core supplies those from its
        `applicationTypeSchemas` entry.
        """
        schema = super().model_json_schema(*args, **kwargs)
        _inline_root_refs(schema)
        for order, prop_schema in enumerate(schema["properties"].values(), start=1):
            prop_schema["dial:meta"] = {
                "dial:propertyKind": "server",
                "dial:propertyOrder": order,
            }
        if include_dial_fields:
            schema = {
                "$schema": DIAL_META_SCHEMA,
                "$id": APPLICATION_TYPE_SCHEMA_ID,
                "dial:applicationTypeDisplayName": APPLICATION_TYPE_DISPLAY_NAME,
                "dial:appendApplicationPropertiesHeader": False,
                **schema,
            }
        return schema


def _inline_root_refs(schema: dict[str, Any]) -> None:
    """Replace root-property `$ref`s with the referenced `$defs` schema, inline.

    The DIAL editor renders each root property from its own inline schema, while
    pydantic emits nested models as `$ref`s into `$defs`. Every nested model here is
    used exactly once at the root, so inlining is loss-free and `$defs` is dropped.
    Deeper `$ref` nesting is not supported by this slim generator — fail loudly so a
    future model change cannot silently produce a broken schema.
    """
    defs = schema.pop("$defs", {})
    for name, prop_schema in schema.get("properties", {}).items():
        ref = prop_schema.pop("$ref", None)
        if ref is not None:
            target = defs[ref.removeprefix("#/$defs/")]
            # Keep sibling keys (e.g. a field description) alongside the inlined body.
            schema["properties"][name] = {**target, **prop_schema}
    if "$ref" in json.dumps(schema):
        raise ValueError("nested $refs below root properties are not supported")
