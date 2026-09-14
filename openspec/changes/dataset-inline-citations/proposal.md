## Why

A delivered report's document citations became pills; its dataset citations did not. A reader who
reaches a sentence sourced from a dataset sees `[dataset IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)]` as
literal text — an identifier whose meaning lives in a server they cannot see — while the sentence
beside it carries a pill naming a publication. The `report-citations` capability states that outcome
as deliberate, and gives the reason: a dataset is not a file, so there is nothing to copy into the
reader's bucket and nothing for the document viewer to open.

That reason has stopped holding, and two checks rather than one argument are what settle it.

**The dataset server already reports a portal link.** The StatGPT MCP's available-datasets tool
answers with one record per dataset carrying `id`, `name` and `url`, the last being that dataset's
page on the portal. It answers as an MCP structured result — `datasets_meta.py` returns an
`AvailableDatasetsStructuredContent` model through a fastmcp `ToolResult` — so the app can read it
the same way it reads the file-sharing tool's answer today. The identifier in those records is the
same string the data-query tool reports as `urn` and the same string the report writer is already
instructed to copy into a marker, so a marker resolves back against the catalogue with no
normalization.

**The client already opens an external citation URL.** DIAL Chat's `openAnnotationAttachment` sends
any attachment URL that does not begin `files/` to `window.open(url, '_blank', 'noopener,noreferrer')`,
and its citation card labels that button "Open in browser" exactly when the annotation's source type
is `text/html` or `application/xhtml+xml`. The pill's own label comes from the attachment title, and
`useAnnotations` re-derives a stored MIME type only from a recognized URL extension, so an
extensionless portal URL keeps the type the app sends. None of that is new work on the client: it is
the path the reference-link citations already use.

So the only thing standing between a dataset citation and a pill is this application.

## What Changes

- **A dataset citation becomes a pill whose link opens the dataset's page on the portal.** The
  `report-citations` requirement that `[dataset <id>]` markers are never converted is reversed. A
  dataset marker is converted on one condition, stated in the same shape as the document condition:
  the cited dataset resolved a URL, and that URL is an absolute `http` or `https` URL. A dataset the
  catalogue does not report, reports without a URL, or reports with a storage-relative URL keeps its
  marker text, so the failure mode stays a missing pill and never a lost citation.

- **A dataset's name, page address and last-update date come from a contracted dataset-metadata
  tool.** The app calls it once per turn with no arguments and filters its answer to the ids the
  delivered report cites. The contract this change states is the tool's answer shape — a structured
  result carrying a `datasets` array whose elements each carry an `id` and a `name`, and optionally a
  `url` and an ISO 8601 `lastUpdated` — not the identity of any server providing it. The two optional
  fields cost different things when absent: no `url` means no pill at all, while no `lastUpdated`
  means one fewer fact on an otherwise normal card.

- **The dataset-metadata tool stays in the research agent's tools.** This is the one place the new
  contract deliberately departs from the file-sharing tool's, which the app removes from what the
  agent is offered. A catalogue listing is how the research agent discovers which datasets exist, so
  hiding it would cost the research to buy the citation. The app resolves the tool from the server's
  full advertised list, as it does for file sharing, and `tools_to_include` continues to govern what
  the agent sees.

- **One new optional configuration field, `dataset_metadata_tool`, names that tool on a `statgpt`
  server.** Only a `statgpt` server may set it, since datasets are what such a server serves. It is
  **optional**, unlike the `generic_rag` server's required `file_sharing_tool`: a StatGPT channel
  whose research value is its data-query tool may advertise no catalogue tool at all, and refusing
  that configuration would reject a working deployment to protect a label.

- **A dataset annotation differs from a document annotation in four fields.** Its
  `body.source.attachment.type` is `text/html` rather than `application/pdf`, which is what makes the
  client's card offer "Open in browser" instead of "Download". Its `body.selector` is **omitted**
  rather than carrying a `pdf_bbox`, because a dataset citation names no page. Its two labels read
  `<name> dataset`, the **card** carrying the name whole and the **pill** carrying it shortened to
  the same `max_pill_title_chars` budget a document title is shortened to, with `dataset` appended
  after the shortening the way a document's cited page is. Neither label carries the URL. It lives in
  `body.source.attachment.url`, and the reader reaches it in two clicks that both belong to the
  client: the pill opens the citation card, and the card's "Open in browser" action opens the page in
  a new tab.

- **A citation's labels now have the same shape whether or not its metadata resolved, and this is
  stated as a requirement for documents as well as datasets.** Every label is a leading part naming
  the source plus a fixed trailing part — `, page <ix>` for a document, ` dataset` for a dataset —
  and a failed lookup changes only what fills the leading slot: `doc <id>` instead of the
  publication title, the URN instead of the dataset name. Nothing in a label tells a reader that a
  lookup failed, because that is the application's problem and a reader shown it is only invited to
  trust one real citation less than another. Documents already behaved this way; the capability
  never said so, and now does.

- **A dataset annotation carries a `body.quote`, which a document annotation still does not.** The
  field the client reserves for a quoted passage is given the two facts that let a reader judge a
  dataset instead — its identifier and, when the server knows one, its last-update date — as a
  Markdown list: `* URN: <urn>` and `* Last update: <date>`. The last-update row is dropped from the
  list entirely when no date was reported, rather than rendered as a placeholder. This also puts to use the blank space the
  client reserves in a popup with a switcher, which for document citations is the subject of an
  outstanding ask to the DIAL Chat team.

- **A dataset citation and a document citation standing next to each other now fold into one pill.**
  They already fold into one run; until now only the document half converted and the dataset marker
  survived as text beside the tag. Both halves converting means the run yields a single pill whose
  popup steps through both sources, which is what the run rule has always specified for two
  convertible citations.

- **The report writer is told what identifies each kind of source, not just what the brackets look
  like.** How a report references a source is an internal contract between the writer's prompt and
  the app's parser, so the prompt states both halves: a document is referenced by its document id
  and the index of the cited page, a dataset by its URN written whole — punctuation and version
  intact, never abbreviated and never percent-encoded. The prompt's dataset line says "the dataset's
  `ID` as the tool reports it" today, which names neither the URN nor what must survive into the
  marker.

- **The citation step's INFO event gains the dataset counts**, so a turn's record states how many
  distinct datasets the report cited and how many of them resolved a usable URL, beside the document
  counts it already carries.

- **The annotations demo is untouched.** The dataset parameters of `convert_citations` default to
  empty, so the demo keeps calling the same function and keeps delivering its dataset marker — if it
  had one — as text. `report-citations` keeps its rule that the demo shows no dataset citation,
  because the demo cites the caller's own attachments and has no portal URL to cite.

## Capabilities

### New Capabilities

None. Every requirement this change adds belongs to a capability that already owns the surrounding
behavior.

### Modified Capabilities

- `report-citations`: the "Dataset citations are never converted" requirement is replaced by a
  conversion condition and its failure modes; the dataset-metadata tool's contract is added beside
  the file-sharing tool's; the annotation payload requirement gains the four fields in which a
  dataset entry differs from a document entry, `body.quote` among them; the run requirement's dataset
  scenario reverses; and the document-metadata read now asks about every cited document rather than
  only the resolved ones, so that it no longer waits on the file-sharing call.
- `application-config-schema`: the new optional `dataset_metadata_tool` field on an MCP server
  entry, its `statgpt`-only restriction, and why it is optional where `file_sharing_tool` is
  required.
- `source-attribution`: the dataset-attribution requirement no longer says a dataset citation is not
  converted, and the verbatim-identifier requirement's dataset half becomes load-bearing — the
  identifier a marker carries is now sent back to a server rather than only read by a human.
- `research-execution`: the report-node requirement states what identifies a source in each
  citation form — a document by id and cited page index, a dataset by its whole URN — rather than
  only what the two forms look like.
- `logging-policy`: the (8c) citation event carries the two dataset counts, and a failed
  dataset-metadata call is one WARNING naming its kind, graded the way the file-sharing failures are.

## Impact

- **`src/dial_deep_research/app_properties.py`**: the `dataset_metadata_tool` field on
  `MCPClientSettings`, a validator refusing it on any server that is not `statgpt`, and a
  `dataset_metadata_tool` accessor on `ApplicationProperties` mirroring the `file_sharing_tool` one.
- **`src/dial_deep_research/app/mcp_tools.py`**: resolving the named tool from the server's full
  advertised list and carrying it on `LoadedMcpTools`, while — unlike the file-sharing tool —
  leaving it in the agent's tool list, which is why its error handling is left alone rather than
  cleared (see `design.md`, decision 6).
- **`src/dial_deep_research/app/research/dataset_metadata.py`** (new): calling the tool, reading its
  structured result, and returning the name and URL of each cited dataset the answer reported, with
  one exception type carrying a failure `kind`, mirroring `file_sharing.py` and
  `document_metadata.py`.
- **`src/dial_deep_research/app/research/citations.py`**: `cited_dataset_ids`; the dataset branch of
  `convert_citations`; `AnnotationAttachment.type` set per citation rather than defaulted to PDF;
  `AnnotationBody.selector` made optional; `log_citations_resolved` gaining the two dataset counts.
- **`src/dial_deep_research/app/research/runner.py`**: the three resolution calls — file sharing,
  document titles, dataset metadata — issued together with `asyncio.gather` instead of one after
  another, the dataset call's own failure kinds and warnings, labelling only from the titles of documents that
  resolved a URL, and the two dataset counts on `_ReportDelivery`.
- **`src/dial_deep_research/app/research/prompts.py`**: the report writer's dataset citation line,
  which must name the URN and say that it is written whole; the review prompt's citation-format
  check, for the same wording.
- **`docs/architecture.md`**: the report-delivery section states that a `[dataset <id>]` marker
  always keeps its text, which this change makes false.
- **`docs/generated-app-schema.json`**: regenerated by `make format` from the new field.
- **Not touched**: `dial_conf/core/applications-template.json`, because the new field is optional and
  the template sets exactly the required properties; the README environment-variable table, because
  no environment variable is added; nothing about the report's citation *forms*, which are
  unchanged — only the prompt text describing what fills them.
- **Dependencies**: none added. The call uses the same tool-call-shaped `ainvoke` and structured-result
  read that `file_sharing.py` already performs.
- **Servers**: the StatGPT MCP satisfies the new contract as deployed. `url` and `lastUpdated` are
  optional in its `DatasetRecord` schema, so a channel whose datasets carry no portal link delivers
  those citations as text without failing anything.
- **Out of scope**: the References "Datasets" table, which is a separate roadmap step and still has
  its own open question about what shape a References row reads its metadata in; series-level
  targeting inside the dataset explorer, which the portal page is the first iteration of.
