## REMOVED Requirements

### Requirement: A citation step runs after the report loop settles and before delivery
**Reason**: This change drops scenarios of this requirement that describe behavior it removes,
and a modified requirement cannot drop a scenario. The requirement is therefore removed and added
again under a new title.
**Migration**: See "A citation step runs on the settled report before delivery" under ADDED Requirements in this delta.

## MODIFIED Requirements

### Requirement: Data-query records are captured from the turn's tool results

A data-query citation needs four things the report does not hold: the address that opens the cited
query in the dataset server's data explorer, the URN of the dataset the query ran against, the
number of series the query returned, and the query's filter, which the citation's card shows. The
dataset server reports all four when it runs a query, in the same tool result the research agent
reads, and the app SHALL take them from there. It SHALL NOT ask the server again at the citation
step: a query id means something only in the result that reported it.

**Which results are captured.** A tool result from the configured `statgpt` server is a data-query
result when its `_meta` carries, under the key the server's `client_meta_key` names
(**application-config-schema** owns the field), matched character for character, a payload that
carries a `queries` field. A result without that payload contributes nothing, whatever tool produced
it, so the app SHALL NOT need to know which of the server's tools runs queries. The same key carries
other tools' payloads too — the list-datasets tool's carries a `datasets` array and no `queries` —
so a payload without a `queries` field SHALL contribute no record and SHALL NOT count as an
unreadable payload.

**Where the app reads them.** A data-query result carries two parts the app reads. The structured
result is also serialized into the text content the model reads. The `_meta` payload is outside
what a model reads, which is why a channel keeps the data explorer URL there and out of the
structured result:

- **The `_meta` payload**, a JSON object carrying a **`queries`** array. Each element SHALL carry a
  string **`queryId`**, and MAY carry a string **`dataExplorerUrl`**, the address that opens that
  query's data in the data explorer. The app reads nothing else from the payload.
- **The structured result**, which MAY carry a **`queries`** array whose elements carry a string
  `queryId`. An element MAY carry a string **`datasetUrn`**, the URN of the queried dataset; an
  integer **`seriesCount`**, the number of series the query returned; **`filters`**; and a
  **`requestedPeriod`**. Each filter carries a `dimensionId`, an `operator`, and a `values` array
  whose elements carry an `id`, the code the query used; a filter MAY carry a `dimensionName`, and
  a value MAY carry a `name`. The requested period MAY carry a `startPeriod` and an `endPeriod`.

The data explorer URL SHALL be read from the `_meta` element and from nothing else. Every other
field a citation uses SHALL be read from the structured element. The dataset URN comes from the
structured element because that is the spelling the writer saw in the tool's text content, so the
URN the catalogue is searched for is the URN a `[dataset <urn>]` citation of the same dataset would
carry.

**One result may report several queries**, one per element of `queries[]` — a query that ran
against two datasets, for example, reports one query per dataset. Every element SHALL become its own
record, and the two parts SHALL be joined element to element by `queryId`, never by position. A query
id present in only one of the two parts still becomes a record, carrying what that part reported.
The structured result's **`candidateDatasets`** are read as well: each element MAY carry a
`query`, which becomes the structured-content element of a record for its `queryId`. A candidate is
a query the server offers to run on another dataset. It did not run, so its record has no `_meta`
element, has no explorer link and did not return data (the terms are defined below). It is kept so
the report review can tell a writer that cited it that the query returned no data, rather than that
its id is unknown.

The fields named above are the only ones the app reads. It SHALL NOT refuse an element for carrying
other fields, and it SHALL keep each element whole on its record (see below). A missing or
unreadable part SHALL cost only what that part is for. A missing `_meta` element costs the pill and
the References row. A missing structured element costs the dataset, the series count and the
filter. An unreadable filter costs its own item on the card.

**Assumptions about the data-query server.** This capability relies on the following, which hold
for the StatGPT data-query tool on a correctly configured channel; a channel's configuration faults
are out of scope:

1. A query that ran and **returned data** carries a `seriesCount` greater than zero in its
   structured element and a `dataExplorerUrl` in its `_meta` element.
2. A query that ran and **returned no data** carries no `seriesCount`, and may carry a
   `dataExplorerUrl`. It backs no value. The report review asks the writer to replace or drop a
   citation of it (**report-composition**); one that survives the review is still resolved as well
   as it can be.
3. A query that **did not run** — constructed only, or offered for a candidate dataset — carries no
   `seriesCount` and no `dataExplorerUrl`, and a candidate has no `_meta` element at all.
4. A query id identifies one query within the turn, and the same query run on the same day reports
   the same id.

**What a model reads is unchanged.** Capturing SHALL NOT alter the content a tool result delivers to
the research agent, SHALL NOT add a data explorer URL or anything else to it, and SHALL NOT fail or
delay the tool call. A payload that cannot be read SHALL cost that result's records and nothing
else: the tool call succeeds for the agent exactly as it would with no capture at all, and the
citation step reports the count (see **logging-policy**).

**What the capture keeps.** The app SHALL keep, for the rest of the turn, a map from each
`queryId` to one record with exactly two keys:

- **`_meta`** — that query's element of the `_meta` payload's `queries`, whole, as the server sent
  it; absent when the payload did not report the id.
- **`structured_content`** — that query's element of the structured result's `queries`, or the
  `query` of its `candidateDatasets` element, whole; absent when the structured result did not
  report the id.

Nothing is renamed, derived or dropped at capture. Everything a citation uses is read out of those
two elements: the data explorer URL from the `_meta` element, and the dataset URN, the series
count, the filters and the requested period from the structured element.

**Three terms describe a captured record.** This capability and **report-composition** use them,
and each is decided by one field:

- **A query with an explorer link** is a record whose `_meta` element carries a `dataExplorerUrl`
  that a browser can open: an absolute `http` or `https` URL, judged by the rule a dataset
  citation's URL is judged by. This term decides the delivery. A citation of such a query becomes a
  pill and contributes a References row; a citation of any other query stays text and contributes
  no row.
- **A query that returned data** is a record whose structured element carries a `seriesCount`
  greater than zero. This term decides the report review: only such a query may be cited
  (**report-composition**).
- **The query's dataset** is the dataset whose URN the record's structured element carries as
  `datasetUrn`. Its name, its last-update date and its page URL are what the list-datasets tool
  reports for that URN.

The first two terms are independent of each other. A query that returned data may lack an explorer
link, on a channel that publishes none for its dataset: its citation passes the review and is
delivered as text. A query with an explorer link may have returned no data: the review catches its
citation, and a citation the review leaves in place is still delivered as a pill, because a pill
that opens the query the report named serves the reader better than a bare id.

Keeping the elements whole means a later feature that shows more of a query reads a field the
record already holds, rather than a change to the capture. When a later result reports a `queryId`
already kept, the later record SHALL replace the earlier one. A query id is stable for the same
query run on the same day, so a repeated query reports the same id, and the latest report of it is
the one the agent read last. Records SHALL be kept for one research run only: a query id reported
in an earlier run is not resolvable in a later one. A run that failed and is resumed on a later
turn is still one run. Its snapshot saves the records captured so far, and the resumed run SHALL
start with them restored, whole, before it captures anything new (**research-resume**). A query id
reported before the failure therefore resolves in the report the resumed run delivers. A record
the resumed run captures for an id already restored SHALL replace it, as for any repeated query.

**Why capture rather than read the tool messages.** The MCP adapter the app builds its tools with
passes the structured result on to the tool message and discards `_meta`, so by the time a tool
message exists the data explorer URL is gone. The capture is the only point in the turn where both
parts are in hand.

#### Scenario: An executed query is captured with its link

- **WHEN** a data-query tool result carries, under the configured `_meta` key, a query with
  `queryId` `dq_0123abcd45` and a `dataExplorerUrl`
  `https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE+US.GDP`, and its structured
  result carries the same `queryId` with `datasetUrn` `IMF:WEO(1.0.0)` and `seriesCount` `2`
- **THEN** the app SHALL keep a record for `dq_0123abcd45` carrying that URL, that URN and that
  series count, and the tool message the research agent reads SHALL carry no URL it did not carry
  before

#### Scenario: A constructed query that did not run is captured without a link

- **WHEN** a tool result reports a query that the server constructed but did not run, so its
  `_meta` element carries a `queryId` and no `dataExplorerUrl`, and its structured element carries
  no `seriesCount`
- **THEN** the app SHALL keep a record for that id that has no explorer link and did not return data

#### Scenario: One result reporting two queries yields two records

- **WHEN** a data-query result's `_meta` payload and structured result each carry two query
  elements, `dq_0000000001` against `IMF:WEO(1.0.0)` and `dq_0000000002` against
  `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)`, listed in a different order in the two parts
- **THEN** the app SHALL keep two records, each joining the `_meta` element and the structured
  element that carry its own `queryId`

#### Scenario: A record keeps the elements whole

- **WHEN** a structured-result element carries `querySummary`, `datasetName` and `factualPeriod`
  beside the fields the app reads
- **THEN** the record SHALL hold that element with all of those fields, although no citation reads
  them

#### Scenario: Candidate queries are kept without a link

- **WHEN** a result asks for a dataset to be selected, so its structured result carries
  `candidateDatasets` whose elements each carry a query with a `queryId`
- **THEN** the app SHALL keep a record for each of those ids carrying only `structured_content`, and
  none of them SHALL have an explorer link or count as a query that returned data

#### Scenario: A result without the configured key contributes nothing

- **WHEN** a tool result carries a `_meta` payload under a key other than the configured one, or
  no `_meta` at all
- **THEN** the app SHALL keep no record from it, and SHALL NOT read query ids out of its structured
  result or its text content

#### Scenario: A list-datasets payload under the same key is not a data-query payload

- **WHEN** the research agent calls the list-datasets tool, and its result carries under the
  configured key a payload with a `datasets` array and no `queries` field
- **THEN** the app SHALL keep no record from it, and SHALL NOT count it as an unreadable payload

#### Scenario: An unreadable payload costs only its own records

- **WHEN** a tool result carries a payload under the configured key whose `queries` is not an array
- **THEN** the tool call SHALL succeed for the research agent unchanged, no record SHALL be kept from
  that result, and records kept from other results SHALL be unaffected

#### Scenario: A missing structured result costs the dataset and the filter

- **WHEN** a tool result carries a readable `_meta` payload for a query with a data explorer URL,
  and no structured result
- **THEN** the app SHALL keep the record with its URL, and a citation of that query SHALL still
  become a pill, labelled with its marker text, whose card carries no filter item

#### Scenario: A query captured before a failure resolves after the resume

- **WHEN** research-agent captured a record for `dq_0123abcd45` with a data explorer URL, the run
  then failed with a quota error, and on a later turn the resumed run delivers a report citing
  `[data_query dq_0123abcd45]`
- **THEN** the citation SHALL become a pill that opens that URL, exactly as it would had the run not
  failed

#### Scenario: A research run on a new plan starts with no records

- **WHEN** research starts fresh after the user changed the plan, and the history holds a snapshot
  with data-query records for the old plan
- **THEN** the run SHALL start with no records, and a query id from the old run SHALL NOT resolve

### Requirement: The References section is built by the app from the cited sources' metadata

The app SHALL write the report's References section itself as part of the citation step of every
turn that delivers a report, and the report writer SHALL NOT write it. Only a failure earlier in
that step leaves a delivery without the section (see the citation-failure requirement). The section is no part of the
configured report structure: its heading comes from `references_section_name` and its cited-nothing
text from `references_section_empty_text` (**application-config-schema**), and what the writer is
given and checked against is owned by **report-composition**. Every row SHALL be built from what a
server reported about a cited source, never from what a model recalled about it — which is the whole
reason the section moves into the app.

**What the section contains.** The section SHALL open with a `##` heading carrying
`references_section_name`. It SHALL then carry **one table per configured MCP server whose sources the delivered
report cites**, in a fixed order by the kind of source a table lists: the **dataset** table first,
then the **document** table, whatever order the servers are configured in. Each table SHALL open with a `###`
sub-heading carrying that server's configured table title, and its header row SHALL be the columns
that server's `references_table` configures, in the configured order. After the server tables, the
section SHALL carry the **glossary table** when the channel configures a glossary and the delivered
report cites at least one glossary term (see the requirement on listing cited glossary terms).

A server whose sources the report does not cite SHALL contribute no table at all. A glossary
citation counts as a cited source here. Where the report cites no source of any kind, the section
SHALL carry no table and SHALL carry
`references_section_empty_text` instead, so a report with nothing to cite says so rather than
showing a bare heading.

**One row per cited source.** Each table SHALL carry one row for each distinct source of its kind the
delivered report cites, ordered by where that source is first cited in the report. A source SHALL be
listed **whether or not its metadata resolved, and whether or not its citations became pills**. The
row is what tells a reader which source a citation names, so a source that lost its pill is the one
whose reader needs the row most.

Two citations of one document on different pages are one source and therefore one row: a References
row names the source, never the cited location.

**How a cell is filled.** Each cell SHALL carry the value the row's source reported under that
column's configured key — for a document, that key in the document's metadata object; for a dataset,
that field of the dataset's catalogue record. A value SHALL be rendered by these rules, so what the
channel stores decides the cell rather than the app's ability to interpret it:

- a string carrying something other than whitespace, as written but stripped of the whitespace
  around it;
- a number or a boolean, as its text;
- a list, as its items joined with `, `, each item rendered by these same rules;
- anything else, and any absent, empty or whitespace-only value, as an empty cell.

A rendered value SHALL be escaped so that it cannot break the table it sits in: a `|` SHALL be
escaped, and a line break SHALL become a space.

**The first column names the source, and it is the column that degrades.** Where the first column's
key resolves nothing — including a value that is present but carries only whitespace, which is
nothing a reader can identify a source by — that cell SHALL carry the source's identifier instead — `doc <id>` for a
document, the URN as the marker carried it for a dataset — which is the fallback a citation pill's
label already uses. Every other column SHALL be left empty when its key resolves nothing. Nothing in
a row SHALL mark it as degraded, for the reason no pill label does: which lookup failed is the
application's problem, and a reader shown it is only invited to trust one real source less than
another.

**A row whose source can be opened carries a pill in its first cell.** A row SHALL be openable on
exactly the condition an inline citation of its source is converted: a document row when the
file-sharing tool returned a PDF URL for that document, and a dataset row when the list-datasets
tool reported a URL a browser can open for that dataset. The first cell of an openable row SHALL
carry one empty marker tag, `<cit data-id="…"></cit>`, **in place of** the text it would otherwise
carry, and one annotation of its own SHALL claim that tag, so the client renders the source's name as
a pill inside the cell. The tag's id SHALL be unique across the message, like every other tag's, and
exactly one annotation SHALL claim it. Every other cell of the row SHALL be filled as for any row. A
row whose source is not openable SHALL keep its first cell as text, with no tag, and no annotation
SHALL be emitted for it.

A row is opened through an annotation rather than a link because a document's shared URL is
storage-relative, so an ordinary Markdown link to it opens nothing. The annotation is the one
mechanism that opens both kinds of source, and a row reusing it opens exactly what an inline pill of
the same source opens.

**A row's annotation is an inline citation's annotation with its own labels and page.** It SHALL
carry the attachment type and the URL that a converted citation of the same source carries (the
requirement "A converted citation is a marker tag in the text and an annotation that names it"),
and, like that citation, no `body.quote`. It SHALL differ from it in two things:

- **The label is the row's name alone.** `body.title` SHALL carry the text the first cell would have
  carried: the value under the first column's key, rendered by the cell rules above, or the source's
  identifier where that key resolves nothing. The `|` escape SHALL NOT be applied, because the label
  is not table text and a reader would see the backslash; a line break still becomes a space. The
  label SHALL carry **no trailing part** — no `, page <ix>`, no ` dataset` and no
  ` - last update <date>` — because the row already sits under a sub-heading naming its kind of
  source, a References row names the source, never the cited location, and a row's other cells
  carry whatever else the channel configured, a last-update column among them. A dataset row's
  pill and card therefore both read the dataset's title alone, such as `World Economic Outlook`. `body.source.attachment.title` SHALL carry the same text,
  shortened to the channel's pill budget exactly as an inline pill's leading part is, or whole where
  the channel names no budget (**application-config-schema** owns the field). A document row labelled
  `doc <id>` SHALL NOT be shortened, for the reason an unresolved inline document label is not: it is
  short by construction, and a cut could eat the id.
- **A document row opens its document at page 1.** Its `pdf_bbox` selector SHALL carry page 1,
  whichever pages the report cites. A row names the whole document rather than a location in it, so
  it opens where the document begins; the selector is still sent, because the document viewer needs
  a page to open at. A dataset row carries no selector, like a dataset citation.

**Row annotations share the array with the inline ones.** They SHALL be emitted in the same
`custom_content.annotations` array as the conversion's annotations, **after** all of them, in the
order the rows are written, with `index` values continuing the array's sequence. The array is still
emitted once, after the content.

A marker tag is not a hyperlink, so an openable row does not breach the no-hyperlink guarantee
(**report-composition**): no cell SHALL carry a Markdown link, an HTML anchor, a URL, or any markup
other than the marker tag. The no-hyperlink rule governs what the report writer writes, and the app
writes no link of its own, so the rule needs no exemption for an app-written section.

**Where it is appended.** The built section SHALL be appended to the text the citation conversion
produced — after the link-removal pass and after the conversion — and SHALL therefore reach the
assistant message content. It SHALL NOT be searched for citation
markers or for hyperlinks: the app wrote it, and it carries neither — its only markup is the marker
tags of its openable rows, which the build writes together with their annotations.

**A section the draft wrote anyway is left where it is.** The app SHALL NOT remove text from a
draft to make room for the built section. A draft that writes its own references section carries an
extra `##` heading, which the structure check reports on every reviewed draft and the revision acts
on (**report-composition**), so the loop is what removes it while a version remains; its words count
toward the ceiling like any other, because a violation must not earn length budget. A draft that
exhausts the version budget still carrying one SHALL be delivered with that section followed by the
built one.

The duplication is deliberate, and it is the cheaper failure: removing a heading and the text after
it removes whatever the writer put below that heading, which a reader cannot see has happened,
while two References sections are visible and cost a reader nothing. It also keeps the rows true —
the cited ids are read before the section is appended and nothing is removed after, so every source
a row lists is one the delivered report cites.

#### Scenario: Every cited source gets a row

- **WHEN** a delivered report cites three documents and two datasets, and the file-sharing tool
  resolved URLs for two of the three documents
- **THEN** the built section SHALL carry a documents table of three rows and a datasets table of two
  rows, each row ordered by where its source is first cited

#### Scenario: The tables follow a fixed order

- **WHEN** the channel configures its document server before its dataset server, configures a
  glossary, and the report cites a document, a dataset and a glossary term
- **THEN** the section SHALL carry the dataset table first, the document table second and the
  glossary table last

#### Scenario: A source whose metadata did not resolve keeps its row

- **WHEN** the metadata answer omits one cited document, and the catalogue omits one cited dataset
- **THEN** each SHALL still have a row, the document's named `doc <id>` and the dataset's named by
  the URN the marker carried, its other cells empty, and nothing in either row SHALL mark it as
  incomplete. The name SHALL be the first cell's text where the row is not openable, and its pill's
  label where it is

#### Scenario: A server with nothing cited contributes no table

- **WHEN** a channel configures a document server and a dataset server, and the delivered report
  cites documents only
- **THEN** the section SHALL carry the documents table alone, and no datasets sub-heading and no
  empty datasets table SHALL appear

#### Scenario: A report citing nothing carries the configured text

- **WHEN** a delivered report cites no document, no dataset and no glossary term
- **THEN** the section SHALL be present, SHALL carry no table, and SHALL carry
  `references_section_empty_text`

#### Scenario: A draft that wrote the section anyway keeps every section it wrote

- **WHEN** a draft that exhausted its version budget carries a `## References` heading with rows the
  model wrote, followed by a `## Conclusion` section
- **THEN** the delivered text SHALL still carry that Conclusion, the model's references heading and
  rows SHALL still be there, and the built section SHALL follow them

#### Scenario: A source cited only inside the draft's own references section still gets a row

- **WHEN** a draft cites one document in its body and a second document only inside the references
  section it wrote itself
- **THEN** both documents SHALL have a row, both citations SHALL be converted where their
  conditions hold, and no row SHALL name a source the delivered text does not cite

#### Scenario: A value that only looks filled leaves its cell empty

- **WHEN** a cited document that resolved no URL has a first-column key holding a string of spaces,
  and its other column holds a value padded with spaces
- **THEN** the first cell SHALL carry the source's identifier rather than the spaces, and the other
  cell SHALL carry its value with the padding gone

#### Scenario: A value that would break the table is escaped

- **WHEN** a cited document that resolved no URL has a title containing a `|` and a publication date
  field holding a value spanning two lines
- **THEN** the `|` SHALL be escaped and the line break SHALL be rendered as a space, so the table
  keeps its columns

#### Scenario: A document row with a PDF URL opens at page 1

- **WHEN** a delivered report cites document 12 first at page 13 and later at page 4, the
  file-sharing tool returned a PDF URL for it, and the documents table's first column reads the
  title `Market Outlook 2025`
- **THEN** that row's first cell SHALL carry one marker tag and no other text, and exactly one
  annotation SHALL claim the tag, with type `application/pdf`, that URL, a `pdf_bbox` selector on
  page 1, no `body.quote`, and both `body.title` and `body.source.attachment.title` reading
  `Market Outlook 2025` with no page

#### Scenario: A dataset row with a portal URL opens its page

- **WHEN** a delivered report cites `IMF:WEO(1.0.0)`, and the list-datasets tool reported the name
  `World Economic Outlook` and the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** that row's first cell SHALL carry one marker tag, and its annotation SHALL carry type
  `text/html`, that URL unchanged, no `body.quote`, no selector, and both labels reading
  `World Economic Outlook` with no ` dataset` and no last-update part, even when the catalogue
  reported a last-update date

#### Scenario: A row whose source cannot be opened stays text

- **WHEN** a delivered report cites a document the file-sharing tool returned no URL for, and a
  dataset whose catalogue record carries no URL
- **THEN** both rows SHALL carry their first cell as text, neither SHALL carry a marker tag, and no
  annotation SHALL be emitted for either row

#### Scenario: A row named by its identifier is labelled with it

- **WHEN** a cited document resolved a PDF URL and no metadata, and the channel sets a pill budget
  of 10
- **THEN** its row's pill and card SHALL both read `doc <id>`, unshortened

#### Scenario: The pill budget shortens a row's pill and not its card

- **WHEN** the channel sets a pill budget and an openable row's name is longer than it
- **THEN** `body.source.attachment.title` SHALL carry the name shortened to that budget with an
  ellipsis, and `body.title` SHALL carry it whole

#### Scenario: A row's label is not escaped for the table

- **WHEN** an openable document row's title contains a `|` and a line break
- **THEN** both labels SHALL carry the `|` without a backslash and the line break as a space, and the
  cell SHALL carry the marker tag alone, so the table keeps its columns

#### Scenario: Row annotations follow the inline ones

- **WHEN** the conversion emitted five annotations, and the section makes two rows openable
- **THEN** the array SHALL carry the two row annotations at indices 5 and 6, in the order their rows
  are written, and each row's tag id SHALL differ from every inline tag id

#### Scenario: The built section carries no hyperlink

- **WHEN** the section is built for a report citing a document whose URL resolved and a dataset whose
  catalogue record carries an absolute portal URL
- **THEN** neither row SHALL carry a Markdown link, an HTML anchor, a URL, or any markup other than
  its marker tag, and the delivered text SHALL still satisfy the no-hyperlink guarantee

## ADDED Requirements

### Requirement: A citation step runs on the settled report before delivery

The app SHALL run one citation step per turn, after the report review loop has settled on the draft
to deliver (see **report-composition**) and before that draft's text is appended to the assistant
message content. The step SHALL NOT run at all on a turn that delivers no report.

The step SHALL be the only thing that alters the settled draft, and it SHALL make exactly three
kinds of alteration, in this order:

1. **Remove everything that points the reader outward** — every hyperlink form the
   **report-composition** capability enumerates, each repaired the way that capability states: the
   label kept where the form has one, the construct deleted whole where it has none. That capability
   owns which forms count and how each is repaired; this step owns only that they go first.
2. **Replace each convertible citation marker** with that citation's marker tag.
3. **Append the References section** the app builds from the cited sources' metadata (see the
   References-section requirement below). It is an addition only: this step removes no text the
   writer wrote, including a references section the writer wrote itself.

The order is fixed so the outcome is deterministic. The first two do not repair each other's input:
link removal runs first, and citation conversion then reads the text it produced, making no
distinction about where a marker came from. The third is ordered last for a stronger reason than
determinism — it writes text the two passes before it would otherwise act on, and the app's own
markup is not the writer's output to be repaired. Nothing else about the draft SHALL be rewritten,
reordered, shortened or reformatted, and the step SHALL NOT call a model.

The text the step produces SHALL be the text appended to the assistant content, and the assistant
content is the one place the delivered report is kept. The research record keeps each draft as the
writer wrote it (**research-resume**), not the delivered text, and no later turn reads a delivered
report back. That text carries the marker tags, which are markup only this feature's reader understands: a renderer
that knows them replaces each tag with a pill, and one that does not either drops the tag or shows
it. This is a property of the delivered report, not an accident, and the failure modes it creates
are covered by the delivery-failure requirement below and by the **research-execution** capability.

#### Scenario: The step runs once on the settled draft

- **WHEN** the report review loop settles on a draft and the turn is about to deliver it
- **THEN** the citation step SHALL run once on that draft, before any of its text reaches the
  assistant message content, and the loop SHALL NOT be re-entered

#### Scenario: An unreviewed draft still gets the deterministic edits

- **WHEN** an instance configures `max_report_versions` as 1, so the first draft is delivered with
  no review call at all, and that draft carries a bare URL beside a convertible citation
- **THEN** the step SHALL still run on it: the URL SHALL be gone from the delivered text, the
  citation SHALL be converted and the References section SHALL be built, because the step is gated
  on a report being delivered and never on a review having judged it

#### Scenario: A turn with no report runs no citation step

- **WHEN** a turn ends without a delivered report — the preparation agent asked a clarifying
  question, or the turn failed
- **THEN** no citation step SHALL run, no annotations SHALL be emitted and no References section
  SHALL be built

#### Scenario: The delivered text is the assistant content

- **WHEN** the citation step converts citations in the settled draft and builds its References
  section
- **THEN** the text appended to the assistant content SHALL carry the marker tags of the converted
  citations and the built section, and SHALL be the post-processed text rather than the draft the
  review judged
- **AND** the turn's research record SHALL hold the draft the review judged, unchanged, as the last
  of its drafts, and SHALL hold no copy of the delivered text
