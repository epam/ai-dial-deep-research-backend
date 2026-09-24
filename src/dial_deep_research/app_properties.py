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
from copy import deepcopy
from typing import Annotated, Any, Literal

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

# Deployment id of the inline-citations demo (registered only when
# `settings.enable_annotations_demo` is set). It reads no application properties:
# its reply is a fixed report exercising the citation mechanism.
ANNOTATIONS_DEMO_DEPLOYMENT_NAME = "deep-research-annotations-demo"

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


# The retrieval servers this application is built against, and the reason the list is closed:
# a report's citations carry the ids and page numbers a server reports, and that shape is no
# part of the MCP protocol. A server outside this list may attribute its results in a form no
# citation format here can express — documents without pages, or web pages — so plugging one in
# is a change to the citation format and its parser, not a configuration entry.
MCPServerType = Literal["generic_rag", "statgpt"]

# What a report cites a server's sources as: a document by its id and cited page, a dataset by its
# URN. The distinction is the citation form rather than the server, which is why it is named here
# once rather than re-derived wherever a cited id has to be routed back to the server that issued
# it.
SourceKind = Literal["document", "dataset"]

# Which kind of source each supported server type serves. Written out per type rather than as a
# default plus one exception, so adding a server type raises here instead of quietly filing its
# sources under the other kind.
SOURCE_KIND_BY_SERVER_TYPE: dict[MCPServerType, SourceKind] = {
    "generic_rag": "document",
    "statgpt": "dataset",
}

# The one placeholder a document-metadata resource template carries. The app substitutes the cited
# ids for it literally rather than through `str.format`, which would choke on any other brace a URI
# may hold and would accept a template carrying placeholders the app does not fill.
DOCUMENT_IDS_PLACEHOLDER = "{document_ids}"


class DocumentMetadataSource(BaseModel):
    """Where a report's document titles come from: which server, which resource, which key.

    The three travel together because none of them is usable alone, and the citation step wants
    one value rather than three that could disagree.
    """

    model_config = ConfigDict(frozen=True)

    server_name: str
    resource_template: str
    title_key: str


class ReferenceColumn(BaseModel):
    """One column of a References table: the heading a reader sees, and the key it reads."""

    model_config = ConfigDict(frozen=True)

    heading: str = Field(
        min_length=1,
        description="The column's header text in the report's References table. A reader sees it,"
        " so write it in the language this channel's readers read.",
    )
    key: str = Field(
        min_length=1,
        description="The name this server reports the value under — a key of a document's metadata"
        " object, or a field of a dataset's catalogue record. A source that reports nothing usable"
        " under it leaves the cell empty, except in the first column, which falls back to the"
        " source's own identifier.",
    )


class ReferencesTable(BaseModel):
    """How one server's cited sources are listed in the report's References section."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(
        min_length=1,
        description="The sub-heading this table is written under, for example Documents or"
        " Datasets. A reader sees it, so write it in the language this channel's readers read.",
    )
    columns: tuple[ReferenceColumn, ...] = Field(
        min_length=1,
        description="The table's columns, in the order they are rendered. The order matters beyond"
        " layout: the first column is the one a reader identifies a row by, so it is the one that"
        " falls back to the source's identifier — a document id, or a dataset's URN — when its key"
        " resolves nothing. Put the column naming the source first.",
    )


class ServerReferencesTable(BaseModel):
    """One server's References table, with the kind of source that fills it.

    The two travel together because the citation step needs both to build a table: the table says
    how the rows are rendered, and the server type says which cited sources are its rows.
    """

    model_config = ConfigDict(frozen=True)

    server_type: MCPServerType
    table: ReferencesTable

    @property
    def source_kind(self) -> SourceKind:
        """Which cited sources fill this table: the ones this server's type serves."""
        return SOURCE_KIND_BY_SERVER_TYPE[self.server_type]


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
        " Arbitrary — it need not match any remote server name, and nothing routes on it. It"
        " labels this server in the application's logs, so name it after what the server"
        " serves for this channel rather than after the software it runs: server_type already"
        " says which retrieval server it is.",
    )
    server_type: MCPServerType = Field(
        description="Which supported retrieval server this is. generic_rag serves documents,"
        " which the report cites as [doc <id>, page <ix>]; statgpt serves datasets, cited as"
        " [dataset <id>]. The list of types is closed because the report's citations carry the"
        " ids and page numbers the server reports, and that is not part of the MCP protocol."
        " At most one server of each type may be configured: a citation names an id and never"
        " the server that issued it, so two servers of one type — each numbering its own"
        " content — would make an id ambiguous.",
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
    file_sharing_tool: str | None = Field(
        default=None,
        description="Name of this server's tool that copies a cited document into the DIAL"
        " storage of the person reading the report and returns the URL of that copy, so a"
        " citation in the report can open the cited page. The application calls this tool"
        " itself when it delivers a report and never offers it to the research agent, so it"
        " does not have to appear in tools_to_include. Required on a generic_rag server, whose"
        " documents a report cites by id and page: without it every one of those citations is"
        " delivered as plain text, which is a broken document server rather than a choice. No"
        " other server type may set it — a dataset citation has no file to open — so exactly"
        " one configured server names one whenever any document is served at all.",
    )

    document_metadata_resource: str | None = Field(
        default=None,
        description="Name of this server's MCP resource serving document metadata, written as a"
        f" URI template with a {DOCUMENT_IDS_PLACEHOLDER} placeholder — for example"
        f" documents://metadata/{DOCUMENT_IDS_PLACEHOLDER}. The application reads it when it"
        " delivers a report, substituting the cited document ids joined with commas, and takes"
        " each document's title from it so a citation pill names the publication instead of its"
        " id. Set it together with document_title_key, which says where the title sits in the"
        " answer. Required on a generic_rag server, and only a generic_rag server may set it: a"
        " document id means nothing outside the server that issued it, so a channel without this"
        " resource labels every pill with a number the reader cannot place.",
    )
    document_title_key: str | None = Field(
        default=None,
        description="Key holding a document's human title in this channel's metadata, for example"
        " publication_title. The metadata resource answers with each document's metadata under"
        " the channel's own key names, so this says which of them to read. A document whose"
        " metadata has no usable value under this key keeps the doc <id>, page <ix> label. Set"
        " it together with document_metadata_resource, which is required on a generic_rag server;"
        " only a generic_rag server may set either.",
    )

    dataset_metadata_tool: str | None = Field(
        default=None,
        description="Name of this server's tool listing the datasets this channel exposes. The"
        " application calls it when it delivers a report, to learn a cited dataset's name and the"
        " address of its page, so a dataset citation becomes a pill that opens that page. The tool"
        " takes no arguments and answers with the whole catalogue; the application selects the"
        " datasets the report cites. It stays available to the research agent, which uses the same"
        " listing to discover which datasets exist, so naming it here only adds a caller."
        " Required on a statgpt server, and only a statgpt server may set it: without it every"
        " dataset citation is delivered as a bare URN in square brackets, which names nothing the"
        " reader can open.",
    )

    references_table: ReferencesTable = Field(
        description="How this server's cited sources are listed in the report's References section:"
        " the sub-heading the table is written under, and its columns. The application builds that"
        " section itself from what the servers reported about the sources the report cites, so this"
        " is where a channel says what a row holds. Required on every server, whatever it serves:"
        " a server without a table is a server whose cited sources cannot be listed. The section is"
        " built for every report, and the report structure has no say in whether it is — it names"
        " only the sections the report writer writes.",
    )

    @property
    def document_metadata(self) -> DocumentMetadataSource | None:
        """Where this server serves document titles from, or `None` when it names none.

        The two fields are validated as a pair, so either both are set or neither is.
        """
        if self.document_metadata_resource is None or self.document_title_key is None:
            return None
        return DocumentMetadataSource(
            server_name=self.server_name,
            resource_template=self.document_metadata_resource,
            title_key=self.document_title_key,
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

    # Declared after the mode check on purpose: pydantic runs `mode="after"` validators in
    # declaration order, and a server with no usable connection at all is the more fundamental
    # misconfiguration, so its error is the one the operator should be shown first.
    @model_validator(mode="after")
    def _validate_file_sharing_tool(self) -> MCPClientSettings:
        """The file-sharing tool belongs to the document server, and it must name one.

        A `generic_rag` server serves the documents a report cites by id and page, and such a
        citation is only useful when the reader can open the cited page — which needs the copy
        this tool makes in the reader's own storage. A document server configured without the
        tool delivers every document citation as plain text, so it is refused here rather than
        costing every report its citations.

        No other type may name one. A `statgpt` server has datasets to cite and no files to
        share, so a tool named there would never be called for a dataset citation; and were it
        to serve documents too, their ids would collide with the document server's, which is
        the ambiguity `ApplicationProperties._validate_one_server_per_type` exists to refuse.
        Since at most one server of each type is configured, these two halves together make
        "at most one server names a file-sharing tool" a consequence rather than a third check.
        """
        if self.server_type == "generic_rag" and not self.file_sharing_tool:
            raise ValueError(
                "a generic_rag server must name its file_sharing_tool: the documents it serves"
                " are cited by id and page, and a citation can only be opened through the copy"
                " that tool makes in the reader's own storage"
            )
        if self.server_type != "generic_rag" and self.file_sharing_tool:
            raise ValueError(
                f"only a generic_rag server may set file_sharing_tool, and this one is"
                f" {self.server_type}: the tool exists to make a cited document readable, and"
                " the documents a report cites come from the document server"
            )
        return self

    @model_validator(mode="after")
    def _validate_document_metadata(self) -> MCPClientSettings:
        """The title fields belong to the document server, and it must name both of them.

        A document citation carries an id that means something only inside the server that
        issued it, so the reader is shown the publication's name instead — which the app can
        only learn by reading it back from that server. A document server that names no
        metadata resource therefore labels every pill with an internal identifier, and it is
        refused here rather than at every delivery.

        Set one without the other and neither works — a URI with no key names nothing to take,
        a key with no URI has nothing to take it from — so a half-configured pair is refused
        with an error of its own.
        """
        resource = self.document_metadata_resource
        title_key = self.document_title_key
        named = [
            name
            for name, value in (
                ("document_metadata_resource", resource),
                ("document_title_key", title_key),
            )
            if value
        ]
        if self.server_type != "generic_rag":
            if named:
                raise ValueError(
                    f"only a generic_rag server may set {' and '.join(named)}, and this one is"
                    f" {self.server_type}: the titles label document citations, and the documents"
                    " a report cites come from the document server"
                )
            return self
        if not named:
            raise ValueError(
                "a generic_rag server must name its document_metadata_resource and"
                " document_title_key: its documents are cited by id and page, and the id is"
                " internal to the server, so without them every citation pill labels the source"
                " with a number the reader cannot place"
            )
        if not resource or not title_key:
            raise ValueError(
                "document_metadata_resource and document_title_key are set together or not at"
                f" all, and only {named[0]} was given: the resource says where to read the"
                " metadata and the key says which value in it is the title, so one without the"
                " other resolves no title"
            )
        if resource.count(DOCUMENT_IDS_PLACEHOLDER) != 1:
            raise ValueError(
                f"document_metadata_resource must carry the {DOCUMENT_IDS_PLACEHOLDER}"
                f" placeholder exactly once, because the cited document ids are substituted for"
                f" it; got: {resource}"
            )
        return self

    @model_validator(mode="after")
    def _validate_dataset_metadata_tool(self) -> MCPClientSettings:
        """The dataset-metadata tool belongs to the dataset server, and it must name one.

        A `[dataset <urn>]` marker names no server, so the app matches every cited URN against
        the one configured dataset server's catalogue. A second server answering about dataset
        ids would make that match ambiguous, which is why only a `statgpt` server may name the
        tool — the same split `file_sharing_tool` has, from the other side.

        Required for the reason the file-sharing tool is: it is the only way a cited id becomes
        something the reader can open. Without it every dataset citation is delivered as a URN in
        square brackets, an identifier that means nothing outside the server that issued it, so a
        dataset server configured without the tool is refused rather than costing every report
        its dataset pills.
        """
        if self.server_type == "statgpt" and not self.dataset_metadata_tool:
            raise ValueError(
                "a statgpt server must name its dataset_metadata_tool: the datasets it serves are"
                " cited by URN, and that tool is the only thing that turns a URN into a dataset"
                " name and a page the reader can open"
            )
        if self.server_type != "statgpt" and self.dataset_metadata_tool:
            raise ValueError(
                f"only a statgpt server may set dataset_metadata_tool, and this one is"
                f" {self.server_type}: the tool names the datasets a report cites and gives each"
                " of them a page address, and those come from the dataset server"
            )
        return self


class ReportSection(BaseModel):
    """One section of the report structure, which is one section the report writer writes.

    `description` is the single home for that section's rules — what belongs in it, how to render
    it, any table columns it carries. It is passed verbatim to the report writer and to
    report-review, so changing a section's behavior means editing this one string.

    The References section is no section of this list: the application builds and appends it
    (`references_section_name` and `references_section_empty_text` are its whole configuration),
    which is why an unknown field is refused here rather than ignored. A stored structure still
    carrying the withdrawn `references_section` flag would otherwise keep a References entry the
    writer is then asked to write beside the one the app appends.
    """

    model_config = ConfigDict(extra="forbid")

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


# What the References section shows when the report cited nothing. It is the section's whole
# content in that case, so it is written as prose a reader reads rather than as instructions.
_REFERENCES_EMPTY_TEXT = "This report cites no source: the research found no citable evidence."

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
]


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
        description="The ordered sections the report writer writes, each rendered as a Markdown"
        " `##` heading. Section names must be unique and at least one section must be protected."
        " The References section is not one of them: the application appends it to every report,"
        " under the heading references_section_name. Report-wide rules (the word ceiling, the ban"
        " on confidence scores and processing times, the inline citation format) are not"
        " configured here — only the sections and what belongs in them.",
    )
    max_report_words: int = Field(
        default=2750,
        ge=1,
        description="The report's word ceiling, counted as whitespace-separated tokens of the"
        " report's Markdown. The count leaves out the inline citations, so it measures the report's"
        " prose rather than its sourcing. The References section is outside it because it is"
        " outside the draft: the application appends that section after the report is settled, so"
        " its length never consumes the writer's budget. Enforced by reviewing the finished report"
        " and revising it, never by cutting text off: a report over the ceiling is rewritten to fit"
        " while the version budget allows, and always ends at a complete sentence.",
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
    references_section_name: str = Field(
        default="References",
        min_length=1,
        description="The heading the application writes the report's References section under. The"
        " application builds that section itself, from what the servers reported about the sources"
        " the report cites, so this names a section the report writer never writes. A reader sees"
        " it, so write it in the language this channel's readers read.",
    )
    references_section_empty_text: str = Field(
        default=_REFERENCES_EMPTY_TEXT,
        min_length=1,
        description="What the References section says when the report cited no source at all. It is"
        " the whole of the section in that case — a report with nothing to cite says so rather than"
        " showing a bare heading — and the only prose an app-built section holds. A reader sees it,"
        " so write it in the language this channel's readers read.",
    )
    max_pill_title_chars: int | None = Field(
        default=None,
        ge=10,
        description="How much of a citation pill's leading part it shows — a cited document's"
        " publication title, or a cited dataset's name, or that dataset's identifier where no name"
        " resolved — the ellipsis counted within it. It also limits the name on a References row's"
        " pill. Null, the default, shows every label whole. Set a number if your client has no room"
        " for long names: a pill is a narrow element and also carries the client's own count"
        " marker when it stands for several sources, and the client does not shorten the label"
        " itself. What follows the leading part of an inline pill — a document's cited page, the"
        " word dataset — is appended after the shortening and is never lost to a long name, and"
        " the citation card keeps the name whole regardless of this value.",
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
    def _validate_one_server_per_type(self) -> ApplicationProperties:
        """At most one MCP server of each supported type.

        Every server of one type numbers its own content, and a citation carries that number
        without saying which server issued it — `[doc 442, page 3]` for a document,
        `[dataset ABC:DEF]` for a dataset. Two servers of one type therefore make an id
        ambiguous, with nothing in the marker, the retrieval result or the MCP protocol able to
        tell the two apart. The configuration is refused rather than resolved by guessing, and
        supporting several servers of one type means qualifying a citation with its source
        first.

        The ambiguity costs the reader rather than only the logs: a cited id is resolved back
        against its server — a document id to the file-sharing tool, a dataset id to the
        catalogue — so two servers shipping the same id would let a pill open the wrong source.
        """
        names_by_type: dict[str, list[str]] = {}
        for server in self.mcp_servers:
            names_by_type.setdefault(server.server_type, []).append(server.server_name)
        repeated = {
            server_type: names for server_type, names in names_by_type.items() if len(names) > 1
        }
        if repeated:
            raise ValueError(
                "at most one MCP server of each type may be configured;"
                f" more than one was given for: {repeated}"
            )
        return self

    @model_validator(mode="after")
    def _validate_report_structure(self) -> ApplicationProperties:
        """Unique section names, and at least one protected section.

        Uniqueness mirrors `_validate_unique_server_names`: duplicate headings make "every
        configured section is present" ambiguous. The protected-section floor keeps configuration
        from producing a report whose every section a user instruction may remove.
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
        return self

    @model_validator(mode="after")
    def _validate_no_section_claims_the_references_heading(self) -> ApplicationProperties:
        """No configured section carries the heading the app writes its References section under.

        The app appends that section to every report, so a section of the same name is one the
        report writer is told to write — by the structure it must reproduce — and told not to
        write, by the rule naming the appended section. The reader would see the heading twice.

        Compared case-folded and stripped, because the collision is about the heading a reader
        sees rather than about an exact string: `references` and `References` render the same. The
        error names both halves of the fix, the section and the property, since either can change.
        """
        wanted = self.references_section_name.strip().casefold()
        claimed = [
            section.name
            for section in self.default_report_structure
            if section.name.strip().casefold() == wanted
        ]
        if claimed:
            raise ValueError(
                "no section may be named like the appended References section"
                f" (references_section_name={self.references_section_name!r});"
                f" rename the section or the property: {claimed}"
            )
        return self

    @property
    def file_sharing_tool(self) -> str | None:
        """The configured file-sharing tool's name, or `None` when no server names one.

        At most one server can name one — only a `generic_rag` server may, and at most one
        server of each type is configured — so this reads the single name rather than choosing
        between candidates. `None` means the configuration has no document server, and its
        reports carry every citation marker as the report writer wrote it.
        """
        return next(
            (server.file_sharing_tool for server in self.mcp_servers if server.file_sharing_tool),
            None,
        )

    @property
    def references_tables(self) -> list[ServerReferencesTable]:
        """Each server's References table, in the order the servers are configured.

        The order is the order the tables are written in, so an operator decides it by ordering
        the servers. Every server carries a table, so this never selects between candidates — it
        pairs each table with the server type that says which cited sources fill it.
        """
        return [
            ServerReferencesTable(server_type=server.server_type, table=server.references_table)
            for server in self.mcp_servers
        ]

    @property
    def document_metadata(self) -> DocumentMetadataSource | None:
        """Where cited documents' titles come from, or `None` when no document server is
        configured.

        At most one server can name one, for the reason `file_sharing_tool` gives: only a
        `generic_rag` server may, and at most one server of each type is configured. A document
        server must name one, so `None` means this channel serves no documents at all — the same
        configuration that leaves `file_sharing_tool` unset.
        """
        return next(
            (
                source
                for server in self.mcp_servers
                if (source := server.document_metadata) is not None
            ),
            None,
        )

    @property
    def dataset_metadata_tool(self) -> str | None:
        """The configured dataset-metadata tool's name, or `None` when no dataset server is
        configured.

        At most one server can name one, for the reason `file_sharing_tool` gives: only a
        `statgpt` server may, and at most one server of each type is configured. A dataset server
        must name one, so `None` means this channel serves no datasets at all, and its reports
        cite none.
        """
        return next(
            (
                server.dataset_metadata_tool
                for server in self.mcp_servers
                if server.dataset_metadata_tool
            ),
            None,
        )

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
    """Inline every `$ref` under the root properties and drop `$defs`, so each is self-contained.

    The DIAL editor renders each root property from its own schema and does not resolve
    `$ref`/`$defs`, but pydantic emits nested models as `$ref`s into `$defs`. So `$defs` is
    lifted out up front and every `$ref` beneath a root property is replaced with the model it
    points to, at whatever depth — a model inside a list item inside another model included,
    which is the shape an MCP server entry's References table has. The final guard catches a
    `$ref` the walk did not reach rather than emitting one that now dangles.
    """
    defs = schema.pop("$defs", {})
    for name, prop_schema in schema.get("properties", {}).items():
        schema["properties"][name] = _inline_refs(prop_schema, defs, ())
    if "$ref" in json.dumps(schema):
        raise ValueError("nested $refs below root properties are not supported")


def _inline_refs(node: Any, defs: dict[str, Any], expanding: tuple[str, ...]) -> Any:
    """Return `node` with every `$ref` beneath it resolved from `defs`.

    `expanding` names the models already being expanded on this branch, so a model that refers
    to itself raises instead of expanding for ever: an inlined schema has to be a finite
    document, and a recursive one cannot be written without `$ref`.

    Each target is copied before expansion, because one model referenced from two places would
    otherwise be inlined once and reused half-expanded.
    """
    if isinstance(node, list):
        return [_inline_refs(item, defs, expanding) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.pop("$ref", None)
    if ref is not None:
        name = ref.removeprefix("#/$defs/")
        if name in expanding:
            raise ValueError(f"a recursive model cannot be inlined: {name}")
        target = _inline_refs(deepcopy(defs[name]), defs, (*expanding, name))
        # Keep sibling keys (e.g. a field description) alongside the inlined body.
        return {**target, **node}
    return {key: _inline_refs(value, defs, expanding) for key, value in node.items()}
