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
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, HttpUrl, SecretStr, model_validator

from dial_deep_research.utils.config_env import replace_env_str

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


def _expand_env(value: Any) -> Any:
    """Expand `$env:{VAR}` / `$env:{VAR|default}` placeholders in a string from the environment.

    A placeholder whose env var is unset and has no default raises, so a misconfigured secret
    fails app-properties validation instead of silently passing the literal placeholder through.
    """
    if isinstance(value, str):
        return replace_env_str(value, raise_if_missing=True)
    return value


class MCPClientSettings(BaseModel):
    """Connection config for one MCP server the research agent connects to.

    Two mutually exclusive modes:
    - deployment: the MCP is a DIAL application reached through DIAL Core by deployment id.
      The per-request api-key is supplied by SDK header propagation and the request bearer
      token is forwarded for per-user access.
    - direct: a directly-reachable MCP at `url`, authenticated with the static `api_key`
      sent in the `api-key` header.

    `url` and `api_key` accept `$env:{VAR}` placeholders, expanded from the app's environment
    at load time so secrets stay out of committed config.
    """

    server_name: str = Field(
        min_length=1,
        description="Internal name for this server connection; must be unique across the list."
        " Arbitrary — need not match any remote server name.",
    )
    deployment_id: str | None = Field(
        default=None,
        description="Deployment mode: DIAL deployment id of the MCP application, reached through"
        " Core. Mutually exclusive with url/api_key.",
    )
    url: Annotated[HttpUrl | None, BeforeValidator(_expand_env)] = Field(
        default=None,
        description="Direct mode: URL of a directly-reachable MCP server. Supports $env:{VAR}"
        " placeholders. Requires api_key.",
    )
    api_key: Annotated[SecretStr | None, BeforeValidator(_expand_env)] = Field(
        default=None,
        description="Direct mode: static key sent as the api-key header to url. Supports"
        " $env:{VAR} placeholders.",
    )
    tools_to_include: list[str] = Field(
        default_factory=list,
        description="Names of tools to include from this server. If empty, all tools are included.",
    )

    @model_validator(mode="after")
    def _validate_mode(self) -> MCPClientSettings:
        """Require exactly one mode: direct (url + api_key) or deployment (deployment_id)."""
        if self.url is not None:
            if self.deployment_id:
                raise ValueError("deployment_id and url cannot be set at the same time")
            if not (self.api_key and self.api_key.get_secret_value()):
                raise ValueError("api_key is required when url is set (direct mode)")
        elif not self.deployment_id:
            raise ValueError("either deployment_id or url + api_key must be set")
        return self


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
    mcp_servers: list[MCPClientSettings] = Field(
        min_length=1,
        description="MCP servers the research agent connects to. At least one is required;"
        " server_name must be unique across the list.",
    )
    prompts: Prompts

    @model_validator(mode="after")
    def _validate_unique_server_names(self) -> ApplicationProperties:
        names = [server.server_name for server in self.mcp_servers]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate MCP server_name(s): {duplicates}")
        return self

    @classmethod
    def model_json_schema(  # type: ignore[override]
        cls, *args: Any, include_dial_fields: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        """Generate the DIAL application-type schema for this model.

        This schema is what DIAL Core fetches from the app's schema endpoint; the DIAL
        editor (the admin UI) renders it as the configuration form for an instance's
        `applicationProperties`. The editor renders each root property from its own
        self-contained schema, so nested models are inlined (see `_inline_root_refs`)
        instead of being left as `$ref`s.

        Root properties get a `dial:meta` block (`dial:propertyKind`, `dial:propertyOrder`)
        the editor reads for field ordering. With `include_dial_fields`, the root also
        carries the type identity (`$id`, `$schema`, display name, header flag); the schema
        endpoint serves the schema without it, because DIAL Core supplies those from its
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
    """Inline each root property's `$ref` and drop `$defs`, so every property is self-contained.

    The DIAL editor renders each root property from its own schema and does not resolve
    `$ref`/`$defs`, but pydantic emits nested models as `$ref`s into `$defs`. So `$defs` is
    lifted out up front and each root property's `$ref` is replaced with the model it points
    to. Two shapes are handled (see `_inline_refs`): a nested model directly, or a list of
    one. Anything deeper (a model nested inside another, a recursive model) is not resolved;
    with `$defs` gone it would be a dangling `$ref`, so the final guard raises rather than
    emit a broken schema.
    """
    defs = schema.pop("$defs", {})
    for name, prop_schema in schema.get("properties", {}).items():
        schema["properties"][name] = _inline_refs(prop_schema, defs)
    if "$ref" in json.dumps(schema):
        raise ValueError("nested $refs below root properties are not supported")


def _inline_refs(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Return `node` with a `$ref` resolved from `defs`, on the node itself or its `items`.

    Handles only these two shapes; anything deeper is left in place for the caller's guard
    to reject.
    """
    ref = node.pop("$ref", None)
    if ref is not None:
        target = defs[ref.removeprefix("#/$defs/")]
        # Keep sibling keys (e.g. a field description) alongside the inlined body.
        return {**target, **node}
    items = node.get("items")
    if isinstance(items, dict):
        node["items"] = _inline_refs(items, defs)
    return node
