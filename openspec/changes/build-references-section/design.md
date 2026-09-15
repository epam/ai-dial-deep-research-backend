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
apart because they are read under different rules. A pill's title is shortened to the channel's
`max_pill_title_chars` budget and a row's first cell is not, so a channel may deliberately point the
two at different keys — a short label for the pill, a fuller citation string for the row. The specs
say plainly that the two may differ.

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

### 9. A references section a draft wrote is left where it is; the loop is what removes it

The writer is told not to write the section and the reviewer is told never to ask for one. A draft
that writes one anyway carries an extra `##` heading, which the structure check already reports in
Python, so the revision loop removes it — while a version remains. A draft that exhausts the version
budget still carrying its own section is delivered with that section followed by the app's.

Measurement is unchanged: a stray section's words count toward the ceiling, which is why
`_drop_references_section` is deleted rather than kept. A violation must not also earn length budget.

*Alternative rejected:* removing it at delivery, by finding the heading and dropping it together
with everything after it. It reads as the obvious repair, and it is what this change first
specified. But "everything after the heading" is only the section when the writer put it last, and a
writer that disobeys the instruction is exactly the writer who may put it anywhere. Run against the
delivery code, a draft ordered `## Key Findings`, `## References`, `## Conclusion` came back as
`## Key Findings` alone: the repair deleted a content section and reported nothing. A duplicated
References section is visible and costs a reader nothing; a deleted Conclusion is invisible and
costs them the report's answer.

It also keeps the rows honest. The cited ids are read from the text before the section is appended,
so with nothing removed afterwards, every source a row lists is one the delivered report really
cites.

### 10. The build is the last pass, and its failure is its own

Ordering it after the conversion is not only determinism: the link-removal and marker-parsing passes
exist to repair what a model wrote, and the app's own markup is not theirs to repair. Building last
also means the build's failure cannot cost a pill — the conversion has already finished — which is
why it gets a failure kind and a warning of its own rather than joining the conversion's.

### 11. The heading and the cited-nothing text are application properties, not a section entry

The app needs two strings a channel owns: the heading it writes the section under, and what the
section says when the report cited nothing. Both become top-level properties with defaults —
`references_section_name` defaulting to `References`, `references_section_empty_text` to one plain
sentence — so a channel content with English edits nothing, and a channel serving other readers
overrides two fields.

*Alternative rejected:* keeping the section in `default_report_structure` behind a
`references_section` flag, which is what this change first specified. It made `description` mean two
different things, writer instructions for every other section and reader-facing prose for this one.
It needed a validator for "only the last section may set the flag" and a derivation subtracting that
section wherever the writer's sections were needed, which ended up applied at two layers. And it let
a structure satisfy the protected-section floor with a section the writer never writes, which
rendered an empty list of protected names into both the writer and the review prompt.

*Alternative rejected:* hard-coding both strings. Each is text a reader sees, and every other
reader-facing string in this application is configured per channel so it can be written in the
language that channel's readers read.

### 12. A stale `references_section` in a channel's config must fail, not be ignored

`ReportSection` sets no `model_config`, so pydantic's default `extra="ignore"` applies: a channel
whose stored structure still carries `references_section: true` would have the flag ignored and its
References entry kept as an ordinary writer section. The writer would then be told to write it, the
structure check would demand it, and the app would append its own — two References sections on every
report, with nothing in the logs saying why. So `ReportSection` SHALL set `extra="forbid"`, making a
stale section entry a validation error the operator sees as "application not configured", which is
the failure mode this change already chose for a missing `references_table`.

*Alternative rejected:* ignoring the stale field and relying on the migration step to remove the
section. It trades one loud error at configuration time for a wrong report on every turn until
someone notices.

## Risks / Trade-offs

- **The section is non-interactive, so a reader cannot open a source from it.** → The inline pills
  open sources, and they are unchanged. The rows name every cited source, including those whose
  pills failed, which is the job this change exists to do. Making a row openable is a follow-up
  the proposal scopes out.

- **Requiring `references_table` breaks every existing channel's configuration**, and forbidding
  extras on `ReportSection` breaks any channel whose structure still names a references section. →
  Both land in the same wave as the document-metadata fields, which are already a breaking change
  being rolled out by editing each channel's properties. The two new section properties add nothing
  to the break, carrying defaults. The failure is loud and immediate: validation rejects the
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

- **A writer that ignores the instruction to its last permitted version delivers two References
  sections.** → Accepted, and preferred to the alternative that deleted text (decision 9). The app's
  structure check reports the extra heading on every reviewed draft, so this needs a writer that
  disobeys a direct instruction through every revision the budget allows.

- **The section can no longer be switched off.** → Every instance configures at least one MCP server
  and every server carries a references table, so every instance has a citable source kind and a
  section to build. The opt-out protected nothing.

- **The heading and the cited-nothing sentence default to English.** → A channel serving other
  readers overrides two properties. This is the same trade the configured column headings make, and
  the defaults keep the change from adding to the configuration break below.

## Migration Plan

1. Land the code and the regenerated schema together, so DIAL Core serves a schema that matches what
   the app validates.
2. Edit each channel's `applicationProperties` to add a `references_table` to every MCP server entry
   and to remove the References section from any `default_report_structure` it configures itself.
   Until a channel is edited, its turns fail validation and reach the user as "application not
   configured" — for the missing table, and for the removed `references_section` field the section
   entry still carries. The two new section properties need no edit unless the channel wants a
   heading or a cited-nothing sentence of its own.
3. Roll out. There is nothing to migrate in stored conversations: a persisted report is text, and an
   older one simply carries the section its writer wrote.

Rollback is the reverse and is safe in the same way: the previous version reads a
`references_table` it does not know as an extra field it ignores, so a rolled-back deployment serves
channels whose properties carry the new field, with the report writer writing the section again. A
channel that has had its References section removed from its structure needs it put back for that
older version to write one at all.

## Open Questions

- **How a References row should open its source in one click.** The open ask to the DIAL Chat team
  is whether an ordinary link can open a file in the side panel, and what it would take. Until it
  is answered, an openable row means an annotation and therefore a citation card, which is more
  than a row should need. Answering it changes what a row renders as, not what it contains, so
  neither the specs nor the task breakdown here depends on it.
