## Why

The models learn what the dataset server holds from what the app fetches on every turn, but what
the document server holds comes only from the hand-written `prompts.data_sources_descriptions`.
That text goes stale as documents are added, and it is shown even on a channel whose configuration
does not serve what it describes. The document server can report its own collection, so the app
can fetch the figures that change — how many documents there are and which dates they cover — and
the hand-written text can shrink to what no server reports.

## What Changes

- **BREAKING**: remove `prompts.data_sources_descriptions`. Every MCP server gains an optional
  `description`, the static text the models are shown about that server's sources. A
  configuration that still sets the removed field fails validation.
- The data-sources string is built from parts written one after another: the document statistics,
  the document server's description, the datasets section, the dataset server's description and
  the glossary. A part appears only when its server is configured and the part has content. Each
  description is wrapped in a tag of its own, so its Markdown headings cannot take in the parts
  after it.
- A `generic_rag` server must set a `description`, `document_stats`, or both.
- A `generic_rag` server may configure an optional `document_stats` object: the list-documents
  tool, the metadata key that holds a document's publication date, an optional metadata key that
  holds its type, and the page size. Without it, the app makes no document call.
- With `document_stats`, the app lists every document once per turn, page by page, with at most
  three attempts per page and at most 10 pages, concurrently with the datasets and glossary parts.
  It then renders a **document statistics** block: the document count and the earliest and latest
  publication dates, and, when the type key is set, the same three figures per document type.
- Missing or malformed dates and types are ignored. A type is written as a quoted string, so a
  whitespace-only type stays visible.
- When a page cannot be obtained, or 10 pages do not reach the total, the block shows a failure
  text instead of figures. The server's description is still shown, and the turn continues.
- The data-sources fetch runs whenever the channel has work for it: a dataset server, or a
  document server with `document_stats`. It is no longer tied to the dataset server alone.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-sources-discovery`: the fetch gains a documents part, the data-sources string is assembled
  from per-server sections with no fixed hand-written prefix, and the documents fetch has its own
  logging and failure rules.
- `application-config-schema`: `prompts.data_sources_descriptions` is removed, every MCP server
  gains an optional `description`, and a `generic_rag` server gains the optional `document_stats`
  object.
- `research-execution`: the inputs of the research graph's calls describe the data-sources string
  by its new composition.
- `clarification-and-plan-alignment`: the inputs of the preparation calls describe the
  data-sources string by its new composition.

## Impact

- Code: `app_properties.py` (`Prompts`, `MCPClientSettings`, a new `DocumentStats` model),
  `app/data_sources.py` (assembly and the fetch gate), a new `app/document_stats.py` (fetch,
  aggregation and rendering), and the preparation and playground prompt fill-ins that name the old
  field.
- Configuration: `dial_conf/core/applications-template.json` drops the removed field, and
  `docs/generated-app-schema.json` is regenerated. Every deployed channel configuration that sets
  `data_sources_descriptions` must move that text into a server's `description` before it deploys
  this version.
- Docs: `docs/architecture.md` (the data-sources diagram and prose).
- Tests: every test fixture that sets `data_sources_descriptions`, plus new tests for the
  documents fetch, the aggregation and the rendering.
- Generic RAG: the app depends on the `list_documents` tool taking `offset` and `limit` and
  answering with `total_count` and `results`. It relies on the server to order pages stably.
