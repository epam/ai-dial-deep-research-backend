## Context

See `proposal.md` — Why. What matters here is the shape of the step the section is built inside.

The citation step already resolves, in one `asyncio.gather`, everything a References row needs: the
file-sharing call's id-to-URL mapping, the document-metadata resource's answer for every cited
document, and the dataset catalogue. It runs after the report loop settles and before the text is
appended, and nothing in it may fail the turn. The section is therefore not new data-gathering; it
is a third pass over data the step already holds.

Two constraints come from outside this repository and were checked rather than assumed:

- **A cited document's shared URL is storage-relative.** `get_citation_url` returns whatever
  `copy_file_to_user` produced, which is `files/{appdata}/{name}`
  (`generic-rag/src/generic_rag/dial_client.py`). It is not an absolute URL, so an ordinary Markdown
  link to it in the report body resolves against the chat page's own origin.
- **The document-metadata resource answers with each document's stored metadata verbatim**, under
  the channel's own key names, renaming and adding nothing. That is a settled decision on the
  Generic RAG side. The alternative — the server answering with a canonical row shape — was
  considered and dropped, because canonicalisation stops at the title while a row's other columns
  stay open-ended.

## Goals / Non-Goals

**Goals.** Every row of the delivered References section is a fact a server reported about a source
the delivered report cites. The section is built from data already in hand, so it costs no round
trip. A failure in building it costs the section alone.

**Non-Goals.** Making a row openable in one click; that waits on the DIAL Chat team (see Open
Questions). Changing which sources a report may cite, the inline citation forms, or the annotation
payload. Sorting, grouping or deduplicating rows by anything other than the order the report cites
them in.

## Decisions

### 1. The table's shape is configured per MCP server, not per report section

A row's cells come from a server's own metadata vocabulary: a document's title lives under whatever
key that channel indexed it as, a dataset's last-update date under the field its catalogue reports.
The server entry is already where that vocabulary is configured (`document_title_key` is there
today), so the table belongs there too.

*Alternative rejected:* putting the table on `ReportSection`. The section would then have to name
which server each table describes, re-introducing exactly the server-to-source mapping the entry
already carries.

*Alternative rejected:* the server marking which metadata fields belong in a reference, as a third
schema marker beside `enable_filtering`. It needs a Generic RAG change and release before this work
can land, and it cannot supply a column *heading* — which is user-facing text in the channel's
language.

### 2. Columns are an ordered list, not a heading-to-key mapping

The natural reading of "a mapping from user-facing column names to metadata fields" is a JSON
object. Column order is behavior here, not presentation: the first column is the one that falls back
to the source's identifier, so which column is first has to be unambiguous. JSON object key order is
preserved by every implementation involved and guaranteed by none of their specifications, so the
configuration is `list[ReferenceColumn]` with `heading` and `key` on each. The relation the user
asked for is the same; only its encoding makes the order explicit.

### 3. The first column names the source, and it is the column that degrades

A reference list leads with the name of the thing being referenced, and the fallback has to land
where a reader will look for an identifier. So the first column carries `doc <id>` or the URN when
its key resolves nothing — the same fallback `_document_body` and `_dataset_body` already use for a
pill label — and the other columns are simply left blank.

*Alternative rejected:* linking the fallback to whichever column reads `document_title_key`. It ties
two independent configuration fields together and leaves a dataset table, which has no title key, to
a different rule.

### 4. `document_title_key` stays, beside the table

The two overlap: a channel will normally set the table's first column to the same key. They are kept
apart because they are needed at different times. A structure may declare no references section
while its citations still need titled pills, so the pill's key cannot live inside a table that such
a channel has no reason to think about. The specs say plainly that the two may differ.

### 5. The document-metadata read returns the metadata object, and the caller reads keys out of it

`read_document_titles` becomes `read_document_metadata`, returning `dict[int, dict[str, Any]]`. The
title is then one key the runner reads out of the answer, and every column is another. Nothing on
the wire changes: the resource already answers with the whole object and the read already asks about
every cited document.

This is what makes the pill's title and the row's first cell the same fact rather than two lookups
that can disagree, and it is what the user asked for: extract the fields when resolving citation
markers, reuse them when building the section.

### 6. The dataset read keeps every cited record; the URL condition moves to the conversion

`read_dataset_sources` drops a record whose URL a browser cannot open, because its only consumer was
the pill. A References row wants that record. So the read now returns every record whose `id` is
cited, with `DatasetSource.url` becoming `str | None` — set to `None` when the reported URL is not
one `is_web_url` accepts, so an unusable URL is normalized away at the boundary rather than carried
inward.

`_convertible_citation` then reads `source.url is None or not is_web_url(source.url)`, and the
runner's `datasets_resolved` count becomes the number of selected records carrying a URL — which
keeps the (8c) event's contract ("those the tool reported a usable page URL for") exactly as
**logging-policy** states it.

### 7. The section is built in a module of pure functions

`app/research/references.py` takes the cited ids in report order, the resolved metadata, the
catalogue records and the configured tables, and returns Markdown. No DIAL objects, no LangChain, no
I/O — the same shape `citations.py` has, and for the same reason: every rule about a degraded row, a
dropped table or an escaped cell is testable without a server, a model or a browser.

### 8. Cell rendering handles more than strings, and escapes what it renders

A metadata value is whatever the channel indexed. A string renders as written; a number or boolean
renders as its text (a year stored as an integer should not blank a cell); a list joins with `, `;
anything else is an empty cell. Every rendered value has `|` escaped and
line breaks collapsed to spaces, because a stray pipe
silently shifts every cell after it into the wrong column.

### 9. A stray references section is removed at delivery, not at measurement

The writer is told not to write the section, and a draft that writes one is a structure violation
the review reports. Two consequences are deliberately split: the violation counts toward the word
ceiling (a violation must not earn budget, which is why `_drop_references_section` is deleted rather
than kept), and the stray section is removed at delivery (a reader must not see two). Measurement
judges the writer; delivery serves the reader.

### 10. The build is the last pass, and its failure is its own

Ordering it after the conversion is not only determinism: the link-removal and marker-parsing passes
exist to repair what a model wrote, and the app's own markup is not theirs to repair. Building last
also means the build's failure cannot cost a pill — the conversion has already finished — which is
why it gets a failure kind and a warning of its own rather than joining the conversion's.

## Risks / Trade-offs

- **The section is non-interactive, so a reader cannot open a source from it.** → The inline pills
  open sources, and they are unchanged. The rows name every cited source, including those whose
  pills failed, which is the job this change exists to do. Making a row openable is a follow-up
  the proposal scopes out.

- **Requiring `references_table` breaks every existing channel's configuration.** → It lands in the
  same wave as the document-metadata fields, which are already a breaking change being rolled out by
  editing each channel's properties. The failure is loud and immediate: validation rejects the
  properties and the turn is delivered as "application not configured", rather than a report
  silently losing its section.

- **A channel that configures a first column reading a key its documents do not carry gets a table
  of bare `doc <id>` rows.** → The degraded row is the specified behavior, so nothing breaks; the
  gap between the resolved and titled counts on the (8c) event is where an operator sees it. No
  runtime check can tell a wrong key from a channel whose documents genuinely lack the value.

- **Column headings are configured in one language per channel while the report is written in the
  user's.** → Accepted. It is inherent to the app writing the section: the same trade the cited-
  nothing text makes. A channel serving several languages configures the headings its readers
  mostly read.

- **`ReportSection.description` means one thing for a writer-written section and another for the
  references section.** → The field's own description states both branches, and the branch is
  decided by a sibling field the model already validates (`references_section`), which is the same
  pattern `file_sharing_tool` and `server_type` already use. A dedicated field was the alternative;
  it costs every configuration a field that only one section may set, to remove an ambiguity the
  field description resolves in a sentence.

## Migration Plan

1. Land the code and the regenerated schema together, so DIAL Core serves a schema that matches what
   the app validates.
2. Edit each channel's `applicationProperties` to add a `references_table` to every MCP server entry
   and to replace the References section's `description` with the cited-nothing text. Until a
   channel is edited, its turns fail validation and reach the user as "application not configured".
3. Roll out. There is nothing to migrate in stored conversations: a persisted report is text, and an
   older one simply carries the section its writer wrote.

Rollback is the reverse and is safe in the same way: the previous version reads a
`references_table` it does not know as an extra field it ignores, so a rolled-back deployment serves
channels whose properties carry the new field, with the report writer writing the section again.

## Open Questions

- **How a References row should open its source in one click.** The open ask to the DIAL Chat team
  is whether an ordinary link can open a file in the side panel, and what it would take. Until it
  is answered, an openable row means an annotation and therefore a citation card, which is more
  than a row should need. Answering it changes what a row renders as, not what it contains, so
  neither the specs nor the task breakdown here depends on it.
