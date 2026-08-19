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
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    model_validator,
)

from dial_deep_research.utils.config_env import is_env_placeholder, replace_env_str

# Fixed deployment id the chat completion is registered under. Every application
# instance of the Deep Research type routes here; per-instance behavior comes from
# the fetched application properties, not from the deployment id.
DEPLOYMENT_NAME = "deep-research"

# Deployment id of the optional playground chat completion (registered only when
# `settings.enable_playground_channel` is set). It reuses the same application
# properties as the research deployment.
PLAYGROUND_DEPLOYMENT_NAME = "deep-research-playground"

# The DIAL application-type meta-schema and this type's identity within it. The
# `$id` is a generic placeholder: instances reference the type by this value, and
# the DIAL Core `applicationTypeSchemas` entry must carry the same one.
DIAL_META_SCHEMA = "https://dial.epam.com/application_type_schemas/schema#"
APPLICATION_TYPE_SCHEMA_ID = "https://mydial.epam.com/custom_application_schemas/deep-research"
APPLICATION_TYPE_DISPLAY_NAME = "Deep Research"


def _expand_required_placeholder(value: Any) -> Any:
    """Require a bare `$env:{VAR}` placeholder and expand it from the environment.

    Rejects anything that is not exactly one `$env:{VAR}` placeholder — a plaintext value or
    the `$env:{VAR|default}` form alike: the value is referenced by env-var name only, never
    inline. A placeholder whose env var is unset raises, so a misconfigured value fails
    validation instead of silently passing the placeholder through.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not is_env_placeholder(value):
        raise ValueError("must be a $env:{VAR} placeholder (no inline value, no default)")
    return replace_env_str(value, raise_if_missing=True)


class _ConnectionBundle(BaseModel):
    """Parsed direct-mode connection: the URL and its api-key, carried together as one unit.

    Not an application-property field itself — `MCPClientSettings.connection` stores the raw
    JSON string (a `SecretStr`) and this parses it on access, so the URL and api-key are never
    independently selectable in config.
    """

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    api_key: SecretStr = Field(min_length=1)


class MCPClientSettings(BaseModel):
    """Connection config for one MCP server the research agent connects to.

    Two mutually exclusive modes:
    - deployment: the MCP is a DIAL application reached through DIAL Core by deployment id.
      The per-request api-key is supplied by SDK header propagation and the request bearer
      token is forwarded for per-user access.
    - direct: a directly-reachable MCP whose URL and api-key come together in `connection`,
      the api-key sent in the `api-key` header.

    `connection` must be a `$env:{VAR}` placeholder, expanded from the app's environment at
    load time; the URL and api-key are bundled in one env var (not two config fields) so they
    cannot be independently selected. Access the parsed pair through `direct_connection`.
    """

    server_name: str = Field(
        min_length=1,
        description="Internal name for this server connection; must be unique across the list."
        " Arbitrary — need not match any remote server name.",
    )
    deployment_id: str | None = Field(
        default=None,
        description="Deployment mode: DIAL deployment id of the MCP application, reached through"
        " Core. Mutually exclusive with connection.",
    )
    connection: Annotated[SecretStr | None, BeforeValidator(_expand_required_placeholder)] = Field(
        default=None,
        description="Direct mode: a $env:{VAR} placeholder (no inline value, no default)"
        ' resolving to a JSON object {"url": "...", "api_key": "..."} with the MCP server URL'
        " and its api-key. Mutually exclusive with deployment_id.",
    )
    tools_to_include: list[str] = Field(
        default_factory=list,
        description="Names of tools to include from this server. If empty, all tools are included.",
    )

    @property
    def direct_connection(self) -> _ConnectionBundle:
        """Parse the direct-mode `connection` JSON into its URL and api-key.

        Only valid in direct mode (`connection` set). Raises on a missing, malformed, or
        incomplete bundle — the same parse runs at load time so misconfig fails validation.
        """
        if self.connection is None:
            raise ValueError("connection is not set (not a direct-mode server)")
        return _ConnectionBundle.model_validate_json(self.connection.get_secret_value())

    @model_validator(mode="after")
    def _validate_mode(self) -> MCPClientSettings:
        """Require exactly one mode: direct (connection) or deployment (deployment_id)."""
        if self.connection is not None:
            if self.deployment_id:
                raise ValueError("deployment_id and connection cannot be set at the same time")
            # Parse eagerly so a malformed bundle fails validation now, not mid-request.
            _ = self.direct_connection
        elif not self.deployment_id:
            raise ValueError("either deployment_id or connection must be set")
        return self


class ReportSection(BaseModel):
    """One section of the report structure.

    `description` is the single home for that section's rules — what belongs in it, how to
    render it, any table columns it carries. It is passed verbatim to the report writer and
    to report-review, so changing a section's behavior means editing this one string.
    """

    name: str = Field(
        min_length=1,
        description="The section's heading in the report.",
    )
    description: str = Field(
        min_length=1,
        description="Everything the report writer and the review step need to know about this"
        " section's content: its purpose, what belongs in it, how to render it, any table columns."
        " This is the only place a section's rules live.",
    )
    protected: bool = Field(
        default=False,
        description="Whether this section survives any user instruction. A protected section can be"
        " neither dropped nor restyled by anything the user asked for, and neither can the rules in"
        " its description. At least one section must be protected.",
    )
    references_section: bool = Field(
        default=False,
        description="Whether this section is the report's list of sources. Only the last section"
        " may be one, and a structure need not have one at all. Its length follows from how much"
        " the research cited rather than from what the report chose to say, so its words do not"
        " count toward max_report_words; in every other way it is a section like any other.",
    )


# The references section's description owns the source-entry rules for every type a report may
# cite. It lives here rather than in the report prompt because a section's rules have one home
# (see `ReportSection.description`). The inline citation format is deliberately NOT here: it
# applies to every section's body, so it stays a report-wide rule in the report prompt.
_REFERENCES_DESCRIPTION = """\
Decode every source cited in the report.
If any document was cited, add a "Documents" table, with columns: `id`, `title`, `publication date`.
If any dataset was cited, add a "Datasets" table, with columns: `title`.
Each table lists only the sources of its type actually cited in the report,
so a type with nothing cited drops its own table.
The section itself is always written: if the research cited no source at all,
say so plainly here rather than leaving the section out or inventing entries."""

DEFAULT_REPORT_STRUCTURE: list[ReportSection] = [
    ReportSection(
        name="Overview",
        description="What the report set out to answer, what was searched to answer it, and the"
        " short answer. Restate the research question, name the sources and topics the research"
        " covered and the approach taken to cover them, then answer the question directly in two"
        " to four sentences. Keep it brief — the findings and the analysis follow below.",
        protected=True,
    ),
    ReportSection(
        name="Key Findings",
        description="A brief summary of what the research found, leading with the direct answer to"
        " the user's question where the findings support one. Short paragraphs or bullets, not a"
        " retelling of the analysis that follows.",
    ),
    ReportSection(
        name="Detailed Analysis",
        description="The substance of the report: what the sources say, how they fit together, and"
        " what follows from them. Use sub-headings, short paragraphs, and tables where they aid"
        " clarity. Note where sources disagree or where a figure rests on a single source.",
    ),
    ReportSection(
        name="Conclusion",
        description="The bottom line the analysis supports, and the limits of what the findings can"
        " answer. No new facts here.",
    ),
    ReportSection(
        name="References",
        description=_REFERENCES_DESCRIPTION,
        protected=True,
        references_section=True,
    ),
]


def references_section(sections: Sequence[ReportSection]) -> ReportSection | None:
    """The structure's references section, or `None` when it declares none.

    Only the last section may be one (`ApplicationProperties._validate_report_structure`), so this
    is the single place that has to know where to look for it.
    """
    last = sections[-1] if sections else None
    return last if last is not None and last.references_section else None


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
        default=5,
        ge=1,
        description="Max number of research iterations (research-agent → research-review loops)"
        " before the report is forced",
    )
    max_research_graph_steps: int = Field(
        default=500,
        ge=1,
        description="Max super-steps in one execution of the research graph, passed to LangGraph"
        " as recursion_limit. A super-step is one iteration over the graph nodes: nodes that run"
        " in parallel belong to the same super-step, sequential ones to separate super-steps. The"
        " count is per graph execution, and a nested graph counts as an execution of its own, so"
        " this is not a total for the DIAL turn (one user message and the assistant's reply to"
        " it). Treat it as a safety stop for research that does not finish on its own, not as a"
        " way to tune research depth: hitting the limit raises GraphRecursionError and the turn"
        " fails with an error. Raise it if long research legitimately runs out of super-steps.",
    )
    default_report_structure: list[ReportSection] = Field(
        default=DEFAULT_REPORT_STRUCTURE,
        min_length=1,
        description="The ordered sections a report follows, each rendered as a Markdown `##`"
        " heading. Section names must be unique, at least one section must be protected, and only"
        " the last section may set references_section. Report-wide rules (the word ceiling, the"
        " ban on confidence scores and processing times, the inline citation format) are not"
        " configured here — only the sections and what belongs in them.",
    )
    max_report_words: int = Field(
        default=2750,
        ge=1,
        description="The report's word ceiling, counted as whitespace-separated tokens of the"
        " report's Markdown. The count leaves out the inline citations, and the references section"
        " where the structure declares one, so it measures the report's prose rather than its"
        " sourcing. Enforced by reviewing the finished report and revising it, never by cutting"
        " text off: a report over the ceiling is rewritten to fit while the version budget allows,"
        " and always ends at a complete sentence.",
    )
    max_report_versions: int = Field(
        default=3,
        ge=1,
        description="How many report versions may be written in one turn. Version 1 is the first"
        " draft; each later version is a rewrite the review demanded, costing one report call plus"
        " one review call. The last permitted version is delivered without another review — its"
        " verdict could not be acted on. 1 means the first draft is delivered unreviewed, with no"
        " review at all.",
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

    @model_validator(mode="after")
    def _validate_report_structure(self) -> ApplicationProperties:
        """Unique section names, at least one protected section, and the references section last.

        Uniqueness mirrors `_validate_unique_server_names`: duplicate headings make "every
        configured section is present" ambiguous. The protected-section floor keeps configuration
        from producing a report whose every section a user instruction may remove. A report lists
        its sources at the end, so at most one section may be the references section and it must be
        the last — a structure may also have none, and then nothing is exempt from the word count.
        """
        sections = self.default_report_structure
        names = [section.name for section in sections]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate report section name(s): {duplicates}")
        if not any(section.protected for section in sections):
            raise ValueError(
                "default_report_structure must contain at least one section with protected=true"
            )
        misplaced = [section.name for section in sections[:-1] if section.references_section]
        if misplaced:
            raise ValueError(
                "only the last section may set references_section=true;"
                f" misplaced section(s): {misplaced}"
            )
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
