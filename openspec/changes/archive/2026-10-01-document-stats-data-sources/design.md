## Context

`app/data_sources.py` runs the data-sources fetch only when the channel has a `statgpt` server. It
fetches the datasets part and the glossary part concurrently, and `join_data_sources` puts
`prompts.data_sources_descriptions` in front of whatever was fetched. Each call goes through
`call_with_attempts` in `app/data_source_calls.py`, which gives a call three attempts with a
backoff and a per-call deadline, and opens a fresh MCP session per call.

On a Generic RAG server, `list_documents` takes `offset` and `limit`, and returns
`{"total_count": ..., "offset": ..., "limit": ..., "results": [...]}`. Each result is
`{"id", "title", "number_of_pages", **metadata}`, where the metadata keys come from the
channel's own `metadata_schema`, and a field a document does not carry is absent. The server has no
upper bound on `limit`. The order across pages is stable only when the channel sets
`mcp_config.newest_sort`.

## Goals / Non-Goals

**Goals:**

- One place, `app/document_stats.py`, owns the listing, the aggregation and the rendering, in the
  same shape `glossary.py` has for the glossary.
- The assembly of the data-sources string has one owner, so the order and the absence rules in
  **data-sources-discovery** are implemented once.

**Non-Goals:**

- Showing the document list itself to the models. Only the aggregates reach the prompt.
- Telling the research agent anything about the listing's outcome, as the dataset and glossary
  instructions do. The research agent's list-documents calls are unaffected either way, and the
  statistics replace no tool call.
- Reading publication dates from anywhere other than `results`, such as the document-metadata
  resource the References section reads. Both read the same metadata field, but the listing
  already returns it for every document.

## Decisions

**A new module rather than more code in `data_sources.py`.** `data_sources.py` keeps the turn-level
model (`DataSources`) and the assembly; `document_stats.py` gets `DocumentStatsFetch`,
`fetch_document_stats`, the pure aggregation `compute_document_stats` and the pure renderer
`render_document_stats`. The pure functions are what most tests target, as with `glossary.py`.

**Pages are sequential after the first.** The user's guidance: the first call already returns data,
and a `page_size` that covers the collection lists it in one call. A concurrent fan-out after the
first page would only help a collection several pages long, which is outside what the feature is
designed for. The next offset is the number of documents received so far rather than `offset +
page_size`, so a server that caps `limit` below the requested value still pages correctly.

**The listing stops after `MAX_DOCUMENT_PAGES` pages.** Each call is bounded by its deadline, but
without a cap the listing as a whole is not: a server that caps `limit` low, or misreports
`total_count`, would hold the turn before preparation for as many calls as the total implies.
Reaching the cap before the total makes the listing incomplete. The constant lives in
`app_properties.py` rather than in `document_stats.py`, so the field descriptions can name it
without a second copy of the number.

**An incomplete listing renders a failure text, not partial figures.** A missing page would
understate the count and possibly the date range, and nothing in the block could tell the models
that. The failure text follows the datasets and glossary parts: the heading, then
`failed to obtain list of documents`. The static description is a separate part, so it survives.

**`DocumentStatsFetch.text` is always set; `statistics` is `None` when the listing is
incomplete.** The failure text keeps the part present, so the data-sources string never loses the
fact that the channel serves documents. That matters on a channel whose document server sets
`document_stats` and no `description`: without the failure text, a failed listing would leave the
string empty, while the preparation prompt says nothing outside the listed sources is reachable.
Unlike the datasets and glossary failure texts, this one comes with no instruction to the research
agent: the statistics replace no tool call, so there is nothing for it to repeat.

**Dates are parsed with `datetime.fromisoformat`, and the date part is kept.** On Python 3.13
`datetime.fromisoformat` accepts both a calendar date and a date and time, so one call covers both
valid shapes. It also accepts the basic ISO format such as `20250430`, which is still ISO 8601, so
the spec's "parses as ISO 8601" holds.

**Assembly takes the parts in a fixed order, one after another.** `join_data_sources` takes the
five optional parts as keyword arguments and joins the ones that are set with a blank line. The
order lives in that one function. The order follows what reads best rather than which server a
part came from: the document statistics lead, the document description follows, then the datasets
section, the dataset description and the glossary. No tag groups the parts by server; grouping was
considered and rejected by the user, as it adds structure the models do not need.

**Each description gets a tag of its own; the fetched parts get none.** A description is the
admin's text and often carries `##` and `###` headings, so without a boundary the part after it
reads as a subsection of its last heading. Wrapping it in `<documents_description>` or
`<datasets_description>` follows the repository's rule for injected content with formatting of
its own. Two alternatives were rejected: demoting the admin's headings rewrites the admin's text,
and wrapping every part changes the datasets and glossary rendering that existing requirements
specify, while each fetched part already starts with a label line of its own.

**A document server must set a description or document statistics.** A validator on
`MCPClientSettings` rejects a `generic_rag` server that sets neither, because its models would
be told nothing about the documents while the preparation prompt says nothing outside the listed
data sources is reachable. The committed template sets `description` on its document server, the
field that needs no running server. This is a conditional requirement, so the template test that
compares top-level properties is unaffected. `CLAUDE.md` states the exception to its rule that the
template sets no property with a default: a property the instance fails validation without is set.

**One MCP client per server.** `build_mcp_client` is called once for the dataset server and once
for the document server, so the two parts share nothing but the bearer token. A client is built
only for a server that has a part to fetch.

**`Prompts` forbids extra fields.** Without it, a stored configuration that still sets
`data_sources_descriptions` would validate and quietly lose its topics map. Today `Prompts`
accepts unknown fields; no other field of it is known to be set by a deployed configuration.

**`document_stats` lives on `MCPClientSettings`, validated like `glossary`.** It mirrors
`glossary`: a frozen nested model with `extra="forbid"`, and an `MCPClientSettings` validator that
rejects it on a non-`generic_rag` server. `ApplicationProperties` gets a `document_server`
property, the counterpart of `dataset_server`.

**The prompt slot keeps its template name.** The preparation and playground templates fill
`{data_sources_descriptions}`. It is renamed to `{data_sources}`, matching the research graph's
templates, so no code name refers to the removed field.

## Risks / Trade-offs

- [Deployed channel configs still set `data_sources_descriptions`] → they fail validation on the
  first turn after deploy, with an error naming the field. The migration plan moves the text first.
- [A large collection delays the first reply] → at most `MAX_DOCUMENT_PAGES` pages are
  requested, and `page_size` lets a channel cover its collection in one call. A collection the cap
  does not cover gets the failure text on every turn.
- [A server that does not order pages stably] → duplicates or gaps go undetected, by the user's
  decision; the figures can then be off by the documents that moved. A Generic RAG channel avoids
  it by setting `mcp_config.newest_sort`.
- [Every document's metadata crosses the wire on every turn] → the payload is small next to the
  dataset structures already fetched each turn, and it is never shown to a model.

## Migration Plan

1. Before deploying, move each channel's `data_sources_descriptions` text into the `description`
   of its `generic_rag` server, and add `document_stats` where wanted. The application-properties
   schema is fetched from the app, so DIAL Core validates the new shape only once the new version
   runs.
2. Deploy the app and the updated channel configuration together.
3. Rollback: redeploy the previous version and restore the previous configuration, since the old
   version requires `data_sources_descriptions` and rejects nothing it does not know.
