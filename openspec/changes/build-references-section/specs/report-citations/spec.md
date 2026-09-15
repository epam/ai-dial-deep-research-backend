## ADDED Requirements

### Requirement: The References section is built by the app from the cited sources' metadata

Where the configured structure declares a references section, the app SHALL write that section
itself as part of the citation step, and the report writer SHALL NOT write it. Which section that is
comes from the configuration (**application-config-schema**), and what the writer is given and
checked against is owned by **report-composition**. Every row SHALL be built from what a server
reported about a cited source, never from what a model recalled about it — which is the whole reason
the section moves into the app.

**What the section contains.** The section SHALL open with a `##` heading carrying the configured
section name. It SHALL then carry **one table per configured MCP server whose sources the delivered
report cites**, in the order the servers are configured. Each table SHALL open with a `###`
sub-heading carrying that server's configured table title, and its header row SHALL be the columns
that server's `references_table` configures, in the configured order.

A server whose sources the report does not cite SHALL contribute no table at all. Where the report
cites no source of any kind, the section SHALL carry no table and SHALL carry the references
section's configured `description` text instead, so a report with nothing to cite says so rather
than showing a bare heading.

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

- a non-empty string, as written;
- a number or a boolean, as its text;
- a list, as its items joined with `, `, each item rendered by these same rules;
- anything else, and any absent or empty value, as an empty cell.

A rendered value SHALL be escaped so that it cannot break the table it sits in: a `|` SHALL be
escaped, and a line break SHALL become a space.

**The first column names the source, and it is the column that degrades.** Where the first column's
key resolves nothing, that cell SHALL carry the source's identifier instead — `doc <id>` for a
document, the URN as the marker carried it for a dataset — which is the fallback a citation pill's
label already uses. Every other column SHALL be left empty when its key resolves nothing. Nothing in
a row SHALL mark it as degraded, for the reason no pill label does: which lookup failed is the
application's problem, and a reader shown it is only invited to trust one real source less than
another.

**No row is interactive in this iteration.** No cell SHALL carry a hyperlink, a marker tag, or any
other markup that opens something. A document's shared URL is storage-relative, so an ordinary
Markdown link to it opens nothing; making a row openable therefore means an annotation of its own,
which renders the row as a pill with a citation card. Because the app writes no link, the report's
no-hyperlink guarantee (**report-composition**) holds over the delivered text whole and needs no
exemption for app-written markup.

**Where it is appended.** The built section SHALL be appended to the text the citation conversion
produced — after the link-removal pass and after the conversion — and SHALL therefore reach both the
assistant message content and the persisted report message. It SHALL NOT be searched for citation
markers or for hyperlinks: the app wrote it, and nothing in it is either.

**A section the draft wrote anyway is removed first.** Where the delivered draft carries a `##`
heading whose text matches the configured references section's name, that heading and everything
after it SHALL be removed before the built section is appended, so a reader never sees the section
twice. The draft is still judged as the writer wrote it: the stray section is reported as a structure
violation and its words count toward the ceiling (**report-composition**), because a violation must
not earn length budget.

**A structure declaring no references section gets none.** Where no configured section sets
`references_section: true`, the app SHALL build nothing and append nothing, and the delivered report
decodes its citations nowhere. That is the deliberate consequence of that configuration.

#### Scenario: Every cited source gets a row

- **WHEN** a delivered report cites three documents and two datasets, and the file-sharing tool
  resolved URLs for two of the three documents
- **THEN** the built section SHALL carry a documents table of three rows and a datasets table of two
  rows, each row ordered by where its source is first cited

#### Scenario: A source whose metadata did not resolve keeps its row

- **WHEN** the metadata answer omits one cited document, and the catalogue omits one cited dataset
- **THEN** each SHALL still have a row, its first cell reading `doc <id>` and the dataset's reading
  the URN the marker carried, its other cells empty, and nothing in either row SHALL mark it as
  incomplete

#### Scenario: A server with nothing cited contributes no table

- **WHEN** a channel configures a document server and a dataset server, and the delivered report
  cites documents only
- **THEN** the section SHALL carry the documents table alone, and no datasets sub-heading and no
  empty datasets table SHALL appear

#### Scenario: A report citing nothing carries the configured text

- **WHEN** a delivered report cites no document and no dataset
- **THEN** the section SHALL be present, SHALL carry no table, and SHALL carry the references
  section's configured `description` text

#### Scenario: A draft that wrote the section anyway does not deliver it twice

- **WHEN** the delivered draft carries a `## References` heading with rows the model wrote, and the
  configured references section is named `References`
- **THEN** the delivered text SHALL carry exactly one `## References` heading, the rows under it
  SHALL be the app's, and the model's heading and rows SHALL NOT appear

#### Scenario: A structure with no references section gets no section

- **WHEN** an instance configures a structure whose every section leaves `references_section` at its
  default of `False`, and the delivered report cites two documents
- **THEN** no section SHALL be appended, and the delivered text SHALL end with the draft's own last
  section

#### Scenario: A value that would break the table is escaped

- **WHEN** a cited document's title contains a `|` and its publication date field holds a value
  spanning two lines
- **THEN** the `|` SHALL be escaped and the line break SHALL be rendered as a space, so the table
  keeps its columns

#### Scenario: The built section carries no link

- **WHEN** the section is built for a report citing a document whose URL resolved and a dataset whose
  catalogue record carries an absolute portal URL
- **THEN** neither row SHALL carry a Markdown link, a marker tag, or any other openable markup, and
  the delivered text SHALL still satisfy the no-hyperlink guarantee

## MODIFIED Requirements

### Requirement: A citation step runs after the report loop settles and before delivery

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
3. **Write the References section**, where the configured structure declares one — removing a
   references section the draft wrote anyway, and appending the one the app builds from the cited
   sources' metadata (see the References-section requirement below).

The order is fixed so the outcome is deterministic. The first two do not repair each other's input:
link removal runs first, and citation conversion then reads the text it produced, making no
distinction about where a marker came from. The third is ordered last for a stronger reason than
determinism — it writes text the two passes before it would otherwise act on, and the app's own
markup is not the writer's output to be repaired. Nothing else about the draft SHALL be rewritten,
reordered, shortened or reformatted, and the step SHALL NOT call a model.

The text the step produces SHALL be the text appended to the assistant content **and** the text
persisted as the turn's report message, so what a later turn reads back is what the user saw. That
text carries the marker tags, which are markup only this feature's reader understands: a renderer
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

#### Scenario: The delivered text is what gets persisted

- **WHEN** the citation step converts citations in the settled draft and builds its References
  section
- **THEN** the text appended to the assistant content and the text persisted as the report message
  SHALL be identical to each other, SHALL carry the marker tags of the converted citations and the
  built section, and SHALL be the post-processed text rather than the draft the review judged

### Requirement: A cited document's title comes from a contracted metadata resource

A citation's labels name the publication the reader is about to open, and a References row names the
same publication and whatever else that row's columns ask for. The app holds none of it: the only
human-readable string it has per cited document is the file name inside the shared URL, which is a
storage path segment. It SHALL obtain all of it by reading one **MCP resource**, the
document-metadata resource, and SHALL depend on nothing about that resource beyond the contract
stated here.

**Both the resource and the title key come from configuration.** An MCP server entry SHALL be able to
name the resource's URI template and the metadata key holding the human title, and the app SHALL read
exactly what that entry names (**application-config-schema** owns the two fields, and the
`references_table` whose columns name the further keys a row reads). There SHALL be no default URI,
no default key, and no discovery by convention: the app SHALL NOT infer any of them from what a
server advertises, from a key's name, or from any naming pattern. A channel's metadata schema is its
own, so which key carries which fact is configuration rather than a constant.

**A document server must name both**, as it must name its file-sharing tool
(**application-config-schema** owns that rule and what it costs): a document id is internal to the
server that issued it, so a channel with no metadata resource labels every pill with a number the
reader cannot place. What stays optional is the **answer** — an id the resource does not know, or a
document carrying nothing usable under a configured key, costs that citation its title, or that row
its cell, and nothing else.

**The contract.** A resource named as a server's document-metadata resource SHALL satisfy all of the
following. These are requirements on the server, not observations of any one implementation: a named
resource that breaks any of them SHALL fail the way the delivery-failure requirement below
prescribes rather than degrade the report.

- **Address**: a resource URI template carrying exactly one placeholder, `{document_ids}`. The app
  SHALL build the concrete URI by substituting the cited ids joined with commas and nothing else,
  and SHALL send the identifiers verbatim as the **source-attribution** capability requires.
- **Output**: one JSON object at the top level, with no wrapper key, mapping each known document id
  to that document's metadata object. Keys MAY arrive as JSON strings rather than numbers, and the
  app SHALL accept either.
- **The title**: the configured title key's value within a document's metadata object, when present
  and a non-empty string. The app SHALL NOT fall back to another key, and SHALL NOT derive a title
  from the shared URL or from any part of it.
- **The other keys**: every remaining key of a document's metadata object SHALL be available to the
  References row, which reads the keys its columns configure and ignores the rest. The app SHALL NOT
  interpret a key it was not configured to read.
- **Partial answers**: an id the resource does not know MAY be absent from the object, and a document
  present but carrying no usable value under a configured key is equally permitted. Neither SHALL
  make the read fail, and neither SHALL invalidate what did resolve.
- **No side effect**: the read SHALL change nothing on the server. This is why it is a resource
  rather than a tool, and why the app may read it for every turn that delivers a cited report.

The app SHALL read it **once per turn**, asking for **every document id the delivered report
cites**, and SHALL use the one answer for both the citation labels and the References rows. Reading
it once for both is what makes a row's title and its pill's title the same fact rather than two
lookups that can disagree.

A title SHALL NOT label a citation that was not converted, and SHALL NOT be counted among the titles
resolved (see **logging-policy**). That constraint is about **use** rather than about disposal: a
title read for a document that resolved no URL is still a fact the server reported about a source the
report genuinely cites, and the References section lists that source like any other.

Asking for every cited id rather than only the resolved ones is also what frees this read from the
file-sharing call's answer, so the two run **together** rather than one after the other and the step
costs one round trip instead of two.

The resource SHALL NOT be offered to any LLM. It is read by application code at the citation step,
and an MCP resource does not appear in a tool listing, so nothing has to be filtered out of the
agent's tools for this to hold.

#### Scenario: One read covers every cited document and serves both uses

- **WHEN** the settled draft cites five documents and the file-sharing tool returned URLs for three
  of them
- **THEN** the app SHALL make exactly one document-metadata read, asking for all five ids, SHALL
  label citations from the titles of the three that resolved a URL and from no others, and SHALL
  build a References row for all five from that same answer

#### Scenario: The metadata read does not wait for the file-sharing call

- **WHEN** a turn's citation step resolves documents and datasets
- **THEN** the document-metadata read SHALL be issued without waiting for the file-sharing call's
  answer, the ids it asks for being known from the report text alone

#### Scenario: A title for a document that resolved no URL is not shown on a pill

- **WHEN** the answer carries a usable title for a document the file-sharing tool returned no URL for
- **THEN** that document's citations SHALL keep their marker text, no annotation SHALL be emitted for
  them, that title SHALL NOT be counted among the titles resolved, and the document's References row
  SHALL still carry it

#### Scenario: The configured key decides which value is the title

- **WHEN** a document's metadata object carries several string values and the configuration names one
  title key
- **THEN** the label SHALL be built from that key's value, and no other key SHALL be read as a title

#### Scenario: A document with no usable title keeps the marker label

- **WHEN** the answer omits one requested id, or carries it with the configured key absent, empty, or
  holding something that is not a string
- **THEN** that document's citations SHALL still become pills, labelled from the marker, and the other
  documents' titles SHALL be unaffected

#### Scenario: A channel serving no documents makes no metadata read

- **WHEN** a configuration carries no document server, so nothing names a file-sharing tool or a
  document-metadata resource
- **THEN** no metadata read SHALL be made, and the absence SHALL be recorded at DEBUG rather than
  warned about

#### Scenario: A document server naming no resource is not a configuration at all

- **WHEN** a `generic_rag` server names a file-sharing tool and no document-metadata resource
- **THEN** the configuration SHALL be rejected (see **application-config-schema**), so no turn is
  ever served with document citations labelled from their markers by configuration

### Requirement: Cited datasets are named and linked through a contracted dataset-metadata tool

A dataset citation needs three things the app does not hold: the dataset's human name, which labels
the pill and the card and leads its References row; the address of its page, which no label shows and
which the reader reaches through the card's open-in-browser action; and its last-update date, which
the card's body carries when the server knows one. All come from **one MCP tool**, the
**dataset-metadata tool**, and the app SHALL depend on nothing about it beyond the contract stated
here. Which server provides it, what that server names it, and where it keeps the catalogue are all
outside the contract, and the app SHALL behave identically for any server that satisfies it.

**The name comes from configuration.** Each MCP server entry in the application properties SHALL be
able to name that server's dataset-metadata tool, and the app SHALL call exactly the tool that entry
names (**application-config-schema** owns the field). There SHALL be no default name and no
discovery by convention: the app SHALL NOT infer the tool from a server's advertised tool list, from
a tool's description, or from any naming pattern. Only a **dataset** server may name one, and at
most one dataset server may be configured, so at most one configured server names a dataset-metadata
tool — which is what makes asking that server about an id correct, since a `[dataset <id>]` marker
names no server.

A dataset server **must** name one, exactly as a document server must name its file-sharing
tool, and for the same reason: the tool is the only thing that turns a cited URN into a name and a
page the reader can open, so a dataset server without it serves datasets that cannot be cited. The
rule lives in **application-config-schema**, which also records what it costs — a channel whose
dataset server advertises no catalogue tool cannot be configured.

A channel that configures **no dataset server at all** remains ordinary: nothing names a
dataset-metadata tool, no call is made, and a dataset marker in a delivered report keeps its text.
That is the case recorded at DEBUG rather than warned about on every turn (see **logging-policy**).

**The contract.** A tool named as a server's dataset-metadata tool SHALL satisfy all of the
following. These are requirements on the server, not observations of any one implementation: a named
tool that breaks any of them is a misconfiguration, and it SHALL fail the way the delivery-failure
requirement below prescribes rather than degrade the report.

- **Input**: none. The app SHALL call it with no arguments and SHALL pass no cited ids to it. The
  tool answers with the channel's catalogue, and the app selects from that answer.
- **Output**: one JSON object at the top level carrying a **`datasets`** array. Each element SHALL
  carry a string **`id`**, the URN the report's `[dataset <id>]` markers carry and the
  dataset-query tools accept; a string **`name`**, the dataset's human name; and MAY carry two
  further strings — **`url`**, the address of that dataset's own page, and **`lastUpdated`**, the
  date the dataset was last updated. Any other field an element carries SHALL be ignored for the
  purposes of the pill, and SHALL be available to a References row, which reads the fields its
  columns configure — so a server may report a description, a provider or an indicator count
  without breaking the contract, and a channel may put any of them in a column.

  The two named optional fields are optional in different senses, and the difference is what each
  absence costs. An element whose **`url`** is absent is a dataset that cannot be cited as a pill at
  all, because the pill would open nothing; it is still a cited dataset and still gets a References
  row. An element whose **`lastUpdated`** is absent is cited normally and simply carries one fewer
  fact on its card. Neither absence is a malformed answer.

  `lastUpdated` SHALL be a date the reader can act on, written as an **ISO 8601 date** such as
  `2025-04-30`. A server that cannot produce one SHALL omit the field rather than send free text it
  failed to parse, because the app displays this value verbatim and cannot tell a date it does not
  understand from one it does. A value that reaches the app as anything but a non-empty string SHALL
  be read as absent.
- **Structured result**: the tool SHALL return that object as its MCP **structured result**, which
  means declaring the output schema MCP requires for one. The app reads the structured result and
  nothing else — a tool that answers with text content alone SHALL be treated as a failed call. MCP
  carries the same object a second time as serialized text, which the app ignores.
- **Complete for the channel**: the answer SHALL carry every dataset the channel exposes, because
  the app cannot ask about a subset. A dataset absent from the answer is uncitable.
- **Idempotent and read-only**: the app calls the tool once per turn, and repeated calls across
  turns SHALL be safe and SHALL change nothing on the server.

The app SHALL call the tool **once per turn**, and only on a turn whose delivered report cites at
least one dataset. It SHALL NOT call the tool once per cited dataset, and SHALL NOT call it for a
dataset that research touched but the delivered report does not cite.

The app SHALL select from the answer **every** record whose `id` equals a cited id, and SHALL ignore
every other record. Selection SHALL NOT depend on what a record carries: a record with no usable page
URL is selected like any other, because the pill is not the only thing that reads it. What a missing
URL costs is decided where the pill is decided, not here. That the answer is the whole catalogue is a
property of the contract rather than a cost the report pays per citation: one call carries however
many datasets the report cites.

#### Scenario: One call serves every cited dataset

- **WHEN** the delivered report cites four datasets and research queried three more it did not cite
- **THEN** the app SHALL call the dataset-metadata tool exactly once, with no arguments, and SHALL
  read the four cited ids out of its answer

#### Scenario: A report citing no dataset makes no call

- **WHEN** the delivered report cites documents only
- **THEN** the app SHALL NOT call the dataset-metadata tool

#### Scenario: A record with no page URL is still selected

- **WHEN** a cited dataset's record carries an `id` and a `name` and no `url`
- **THEN** that record SHALL be selected, its citations SHALL keep their marker text for want of a
  page to open, and its References row SHALL carry its name

#### Scenario: Extra fields in a record are available to a row

- **WHEN** a reported record carries a description and a provider beside its `id`, `name`, `url` and
  `lastUpdated`, and the channel configures a column reading the provider
- **THEN** the record SHALL be accepted, the pill SHALL be built from the `name` and the `url`
  alone, and the References row SHALL carry the provider in its configured column

#### Scenario: A text-only answer is a failed call

- **WHEN** the named tool returns its catalogue as text content with no structured result
- **THEN** the call SHALL be treated as failed, every dataset citation SHALL keep its marker text,
  and the report SHALL be delivered

### Requirement: A citation failure costs the citations, never the report

No failure in the citation step SHALL fail the turn, discard the report, or delay it beyond the
step's own work. On any of the following the app SHALL deliver the report with the affected markers
left as text, and SHALL convert whatever remains:

- no configured file-sharing tool;
- the configured tool is absent from the server's advertised tools;
- the tool call raises, times out, or reports an error;
- the tool returns no structured result;
- the structured result cannot be read as an id-to-URL mapping;
- an id is missing from an otherwise valid response.

Each of these SHALL be logged once, naming the failure kind, at the level the **logging-policy**
capability's level semantics give it. **No configured file-sharing tool is not a failure**: only a
deployment with no document server can be configured that way, so it has no document citations to
convert, and this is a routine expected outcome of every turn it serves — recorded at DEBUG rather
than warning on each report. The other
five SHALL each be a WARNING — an id missing from an otherwise valid response included, since it
costs the reader a pill the report was written to offer.

**A failure of the dataset-metadata call costs the dataset citations their pills**, and is graded
exactly as the file-sharing failures are, for the same reason: it is the one resolution that makes a
dataset citation convertible. On any of the following the app SHALL deliver the report with every
dataset marker left as text, and SHALL convert whatever document citations it otherwise would:

- no dataset server configured, and so no dataset-metadata tool;
- the configured tool is absent from the server's advertised tools;
- the tool call raises, times out, or reports an error;
- the tool returns no structured result;
- the structured result cannot be read as a list of dataset records;
- a cited dataset id is missing from an otherwise valid answer, or its record carries no usable URL.

**No configured dataset-metadata tool is not a failure** and SHALL be recorded at DEBUG, for the
reason the absent file-sharing tool is: a dataset server must name the tool, so only a deployment
with no dataset server can be configured that way, and such a channel cites no dataset — warning on
every report it delivers would report its configuration as a fault. The other five SHALL each be a
WARNING. A dataset whose record carries **no URL** is the one member of that list which is **not** a
fault of the server: whether a dataset has a portal page is the channel's own data, so it SHALL be
recorded at DEBUG and read from the gap between the requested and resolved dataset counts on the
step's own event (see **logging-policy**).

**A failure of the document-metadata read costs a label and a row's cells, never a pill**, so it is
graded one step lower throughout. On any of the following the app SHALL convert every citation it
otherwise would, labelling from the marker whatever it could not label from a title, and building
each affected References row from what is known about its source:

- no document server configured, and so no document-metadata resource;
- the read raises, times out, or reports an error;
- the answer cannot be read as an id-to-metadata object;
- a requested id is absent from the answer, or carries no usable value under a configured key.

**No configured resource is not a failure** and SHALL be recorded at DEBUG, for the same reason the
absent file-sharing tool is: a document server must name the resource, so only a deployment with no
document server can be configured that way, and it has no document citations to label. The read raising and an unreadable answer SHALL each be a
WARNING, both being misconfiguration or a server in breach of its contract. **A document that simply
has no title SHALL NOT warn**: a channel's metadata is its own, a missing key there is data variance
rather than a fault, and it costs a plainer label and an emptier row rather than anything the reader
loses. How many titles resolved is carried by the step's own event instead (see **logging-policy**).

**Every record the citation step emits carries counts and the failure kind, and nothing drawn from
a document.** The service's own call sites SHALL NOT log, at any level: a returned URL, any part of
one, a file name taken from one, a document title, or a cited document's id. The mapping is a tool
response body and the metadata object is a resource body, which the content allowlist keeps out of
log records, and the allowlist's permission for DIAL relative `files/...` paths covers URLs the
service handles itself elsewhere — a failed image download it reports — and does not reach into
either. What a record may carry about documents is therefore how many: how many were cited, how many
resolved, how many ids the response omitted, how many titles were found. The same holds of
datasets, and of everything a dataset record carries: a dataset's name, its portal URL and any part
of one, and a cited dataset's id SHALL NOT be logged at any level. A References row's cell values are
the same server-reported content and SHALL NOT be logged either. The one name a record may
carry is the configured tool's, which the allowlist allows as a tool name and which is what makes a
misconfiguration warning actionable.

The step SHALL NOT emit a marker tag it has no annotation for. A tag whose annotation never reaches
the reader — because the step could not emit the array, or because something downstream dropped it —
costs that citation entirely rather than degrading to a visible marker, which is why the two halves
are always produced together.

**A failure in the step's own work is not in the list above, and is handled by stage.** The three
alterations fail independently, and each keeps whatever the earlier ones finished:

- The **link pass** raising SHALL deliver the settled draft untouched, with no tag, no annotation and
  no References section. Such a delivery may still carry a hyperlink, which the
  **report-composition** capability's guarantee otherwise forbids. The two rules are ordered here
  rather than left to an implementer's judgement: a finished report reaches its reader, and the
  breach is in the logs.
- The **conversion** raising — marker parsing, block classification, tag replacement, payload
  building — SHALL deliver the text the link pass produced, so the hyperlink guarantee still holds,
  with no tag, no annotation and no References section.
- The **References build** raising SHALL deliver the converted text with every pill it earned and no
  References section, since the section is the only thing that pass produces. It SHALL NOT cost a
  citation its pill, the conversion having already finished.
- The **emission** failing after the text was appended leaves that text's tags unclaimed, and the
  client shows an unclaimed tag to the reader as text. The step SHALL NOT re-send the
  array and SHALL NOT edit the appended content, which DIAL's append-only content makes impossible.

Each of these SHALL be logged once as a WARNING naming the failure kind, and none SHALL fail the
turn.

#### Scenario: A failing tool call delivers the report unconverted

- **WHEN** the file-sharing tool call raises
- **THEN** the report SHALL be delivered with every marker as text, no marker tag and no annotation
  SHALL be emitted, the turn SHALL complete successfully, and one warning SHALL name the failure

#### Scenario: An unreadable response delivers the report unconverted

- **WHEN** the tool responds with something that is not an id-to-URL mapping
- **THEN** the report SHALL be delivered with every marker as text, the turn SHALL complete
  successfully, and one warning SHALL name the failure

#### Scenario: A configured tool the server does not advertise

- **WHEN** a server's configured file-sharing tool name is absent from the tools it advertises
- **THEN** the turn SHALL run normally, the report SHALL be delivered with every marker as text, and
  one warning SHALL name the missing tool

#### Scenario: A failing metadata read still delivers every pill

- **WHEN** the file-sharing tool resolved three documents and the document-metadata read then raises
- **THEN** every citation of those three documents SHALL still become a pill, every label SHALL read
  as the marker did, the References section SHALL still carry a row per cited document reading
  `doc <id>`, the turn SHALL complete successfully, and one WARNING SHALL name the failure

#### Scenario: An unreadable metadata answer still delivers every pill

- **WHEN** the metadata read answers with something that is not an id-to-metadata object
- **THEN** every convertible citation SHALL still become a pill labelled from its marker, and one
  WARNING SHALL name the failure

#### Scenario: A document without a title does not warn

- **WHEN** the metadata answer carries two of the three requested documents with a usable title and
  the third without one
- **THEN** two documents' citations SHALL be labelled with their titles, the third's with its marker
  text, and no WARNING SHALL be emitted for the missing title

#### Scenario: An exception in the link pass delivers the settled draft

- **WHEN** the link removal raises on the settled draft
- **THEN** that draft SHALL be delivered exactly as the review settled it, no annotation and no
  References section SHALL be emitted, the turn SHALL complete successfully, and one WARNING SHALL
  name the failure

#### Scenario: An exception in the conversion keeps the link removal

- **WHEN** the link pass completed and the marker parsing then raises
- **THEN** the link-free text SHALL be delivered with every citation marker in place, no annotation
  and no References section SHALL be emitted, and one WARNING SHALL name the failure

#### Scenario: An exception in the References build keeps the pills

- **WHEN** the conversion completed and the References build then raises
- **THEN** the converted text SHALL be delivered with every marker tag and every annotation it
  earned, no References section SHALL be appended, the turn SHALL complete successfully, and one
  WARNING SHALL name the failure

#### Scenario: A failed emission leaves its tags unclaimed

- **WHEN** the report text carrying marker tags has been appended and sending the annotations array
  then fails
- **THEN** the turn SHALL complete successfully, one WARNING SHALL name the failure, and the step
  SHALL NOT attempt to re-send the array or to alter the appended content

#### Scenario: A report with no citations gets no tag and no annotation

- **WHEN** the settled draft cites no document at all
- **THEN** no file-sharing call SHALL be made, no metadata read SHALL be made, no annotations SHALL
  be emitted, and the delivered text SHALL carry no marker tag — differing from the settled draft
  only where the link pass removed something and where the References section says that nothing was
  cited
