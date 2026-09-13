## ADDED Requirements

### Requirement: A cited document's title comes from a contracted metadata resource

A citation's labels name the publication the reader is about to open. The app holds no such name of
its own: the only human-readable string it has per cited document is the file name inside the shared
URL, which is a storage path segment. It SHALL obtain the name by reading one **MCP resource**, the
document-metadata resource, and SHALL depend on nothing about that resource beyond the contract
stated here.

**Both the resource and the key come from configuration.** An MCP server entry SHALL be able to name
the resource's URI template and the metadata key holding the human title, and the app SHALL read
exactly what that entry names (**application-config-schema** owns the two fields). There SHALL be no
default URI, no default key, and no discovery by convention: the app SHALL NOT infer either from what
a server advertises, from a key's name, or from any naming pattern. A channel's metadata schema is
its own, so which key carries the title is configuration rather than a constant.

**Naming them is optional**, which is what separates this contract from the file-sharing one. A
document server that names no resource delivers pills labelled from the marker, which is a plainer
label rather than a broken link, and a channel whose metadata genuinely carries no title has nothing
to name.

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
- **The title**: the configured key's value within a document's metadata object, when present and a
  non-empty string. Every other key SHALL be ignored. The app SHALL NOT fall back to another key, and
  SHALL NOT derive a title from the shared URL or from any part of it.
- **Partial answers**: an id the resource does not know MAY be absent from the object, and a document
  present but carrying no usable value under the configured key is equally permitted. Neither SHALL
  make the read fail, and neither SHALL invalidate the titles that did resolve.
- **No side effect**: the read SHALL change nothing on the server. This is why it is a resource
  rather than a tool, and why the app may read it for every turn that delivers a cited report.

The app SHALL read it **once per turn**, after the file-sharing call, and SHALL ask only for the
documents that resolved a URL. Those are exactly the documents whose citations become pills, so a
title for any other document would be read and never shown.

The resource SHALL NOT be offered to any LLM. It is read by application code at the citation step,
and an MCP resource does not appear in a tool listing, so nothing has to be filtered out of the
agent's tools for this to hold.

#### Scenario: One read carries the documents that became pills

- **WHEN** the settled draft cites five documents and the file-sharing tool returned URLs for three
  of them
- **THEN** the app SHALL make exactly one document-metadata read, asking for those three ids and no
  others

#### Scenario: The configured key decides which value is the title

- **WHEN** a document's metadata object carries several string values and the configuration names one
  key
- **THEN** the label SHALL be built from that key's value, and no other key SHALL be read as a title

#### Scenario: A document with no usable title keeps the marker label

- **WHEN** the answer omits one requested id, or carries it with the configured key absent, empty, or
  holding something that is not a string
- **THEN** that document's citations SHALL still become pills, labelled from the marker, and the other
  documents' titles SHALL be unaffected

#### Scenario: An instance naming no resource still converts its citations

- **WHEN** a configured document server names a file-sharing tool but no document-metadata resource
- **THEN** no metadata read SHALL be made, every convertible citation SHALL still become a pill, and
  every label SHALL read as the marker did

## MODIFIED Requirements

### Requirement: A citation is converted when the document it names has a PDF URL

The report is written entirely in the inline citation forms the **research-execution** capability
defines: `[doc <id>, page <ix>]` for a document and `[dataset <id>]` for a dataset.

**What the step recognizes as a marker** is exactly those two forms, with a positive integer id and,
for the document form, a positive integer page; the keyword SHALL be matched without regard to case.
The document keyword SHALL also be recognized written out in full, so `[document 12, page 3]` is a
citation exactly as `[doc 12, page 3]` is. That tolerance is not a second report format — the
writer's instructions and the review's format check name the short form alone — but a guard against
one predictable mistake. A retrieval server's own attribution may read `[Document 12, Page 1]` (see
**source-attribution**, which requires attribution to be self-describing and leaves its spelling to
the server), which is close enough to the report's form that a writer may copy it through instead of
translating it. Rejecting the copy would cost that citation its pill silently, while accepting it
converts something that is unambiguously a citation of a document and a page.

Anything else resembling a marker without matching — a non-numeric id, a page range
(`[doc 12, pages 3-4]`), a document citation with no page (`[doc 12]`), a nested bracket — SHALL NOT
be treated as a citation: it keeps its text, produces no annotation, and contributes no id to the
file-sharing call. The bias is deliberately conservative, and the layer that pushes a malformed
citation back into the defined form is the report review, whose criteria include the citation format
(see **report-composition**).

Once the hyperlinks are gone, every remaining marker of those forms is a citation, and the step
converts one — replacing its marker with a marker tag and emitting one annotation for it — on one
condition: **the cited document has a URL the reader can open, and that file is a PDF.**

The file-sharing tool must have returned a DIAL file URL for that document id. It returns none when
no configured server declares such a tool, when the call fails, or when the response omits that id.
A dataset citation never has one, because a dataset is not a file (see the dataset requirement
below).

The file must also be a PDF, because that is the only kind the client opens from a citation and
because the page a citation names is expressed as a PDF page. The contract returns a URL and nothing
else, so the step SHALL decide this from the URL's own path, treating a path ending in `.pdf` as a
PDF and anything else as not one. A PDF stored under a name without that extension is therefore
treated as a non-PDF and keeps its marker — the conservative direction, since the alternative is a
pill that opens nothing.

**Where the marker stands is not a condition.** The client parses a marker tag wherever its
Markdown renderer parses raw inline HTML and draws the pill there, so the step SHALL convert a
citation in a table cell, a heading of either Markdown form, a blockquote and an emphasis span
exactly as it converts one in a paragraph or a list item, and SHALL classify no Markdown block. The
one place a tag does not become a pill is code — a fenced block, an indented block or an inline code
span — where Markdown parses no raw HTML and the reader sees the tag as text; a citation there is
converted like any other, because a report cites its sources in prose and tables rather than inside
code, and a rule that read the Markdown to find those places would cost more than the case is worth.

A citation that fails the condition SHALL keep its marker text exactly as the report writer wrote
it, and SHALL produce no annotation. The step SHALL NOT convert a citation partially — a converted
citation has both its tag and its annotation, or neither.

The failure mode is therefore always a **missing pill**, never a lost or corrupted citation: a
citation the step declines to convert stays as readable as it is today.

Both intended readers — DIAL Chat and the DIAL overlay — run the same renderer, the overlay
embedding the chat application rather than reimplementing it. What the client renders is therefore
one behaviour, not one per reader, and the step SHALL NOT be configurable per consumer.

#### Scenario: A cited sentence in a paragraph is converted

- **WHEN** a paragraph of the settled draft ends `…defaults rise. [doc 442, page 3]` and a URL
  resolves for document 442
- **THEN** that marker SHALL be replaced by a marker tag carrying a unique id, and one annotation
  naming that id SHALL be emitted

#### Scenario: The document keyword written out in full is still a citation

- **WHEN** the settled draft carries `[document 12, page 3]` or `[Document 12, Page 3]`, copied
  through from a tool's own attribution, and a URL resolves for document 12
- **THEN** each SHALL be converted exactly as `[doc 12, page 3]` is, so the copy costs the reader no
  pill

#### Scenario: A cited bullet is converted

- **WHEN** a list item of the settled draft carries a document citation and a URL resolves for it
- **THEN** that citation SHALL be converted exactly as in a paragraph

#### Scenario: A document cited inside a table is converted

- **WHEN** a table row of the settled draft carries `| 2.4% | [doc 446, page 12] |` and a URL
  resolves for document 446
- **THEN** that citation SHALL be converted exactly as in a paragraph

#### Scenario: A citation in a heading or a blockquote is converted

- **WHEN** a document citation appears in a `##`/`###` heading, a setext heading's text line or a
  blockquote, and a URL resolves for its document
- **THEN** each SHALL be converted exactly as in a paragraph

#### Scenario: A malformed marker is not a citation

- **WHEN** a paragraph of the settled draft carries `[doc 12, pages 3-4]`, `[doc twelve, page 3]` or
  `[doc 12]`, and a URL would have resolved for document 12
- **THEN** none of them SHALL be converted, each SHALL keep its text, and none SHALL contribute a
  document id to the file-sharing call

#### Scenario: A cited document that is not a PDF keeps its text

- **WHEN** the file-sharing tool returned a URL whose path does not end in `.pdf`
- **THEN** the condition fails, the marker SHALL remain in the delivered text, and no annotation
  SHALL be emitted for it

#### Scenario: An unresolved document's citation keeps its text

- **WHEN** the file-sharing tool returned no URL for a cited document
- **THEN** the condition fails, its marker SHALL remain in the delivered text, and no annotation
  SHALL be emitted for it

#### Scenario: A link leaves only its label

- **WHEN** a paragraph contains `see the [latest outlook](https://example.org/outlook)`
- **THEN** the delivered text SHALL read `see the latest outlook`, and no annotation SHALL be
  emitted for it — it named no retrieved source to cite

#### Scenario: The same document cited in several places

- **WHEN** the settled draft cites one document in four different paragraphs
- **THEN** all four citations SHALL be converted, each carrying its own tag id and its own
  annotation with its own page

### Requirement: A converted citation is a marker tag in the text and an annotation that names it

Conversion produces two halves that find each other by a shared id.

**In the report text**, one empty citation marker tag, `<cit data-id="…"></cit>`, stands where the
citation's marker stood. An id SHALL be opaque and SHALL appear on exactly one tag in the message:
one tag per converted position, whether that position held a single citation or a run of adjacent
ones. Two citations of the same document and page in **different** positions therefore carry
different ids and render as two pills. The tag SHALL be emitted empty — it anchors a pill at its own
position and does not enclose the cited sentence.

**In `custom_content.annotations`**, one entry per converted citation — so a run of three sources
behind one tag contributes three entries that share that tag's id — carrying:

- **`index`** — the entry's 0-based position in the array, unique across it. The array is an indexed
  list: the DIAL SDK treats a list whose elements carry an `index` as a streaming delta and merges
  by it, and the client uses it both to merge those deltas and to identify the region it scrolls to.
  Uniqueness is load-bearing for a run: the client treats two annotations that share a tag id and
  carry no `index` as one annotation. A caller that asks for a non-streamed response is served by
  the SDK's block path, which strips `index` from every list element of the assembled message, so a
  run's sources may reach such a caller merged into one entry. The field SHALL be emitted regardless
  — the streaming readers this feature is written for keep it — and nothing in the app may depend on
  it surviving to a non-streaming caller.
- **`target.selector`** — type `html_tag`, naming the tag (`cit`) and, in its `id` field, the value
  of that tag's `data-id` attribute. The two SHALL match exactly; an annotation naming a value no tag
  carries renders nothing, and a tag no annotation names is shown to the reader as text. The
  selector's field is `id` while the tag's attribute is `data-id` — an asymmetry of the client's
  contract, not a choice open to this app.
- **`body.title`** — the label of this citation's entry inside the pill's popup. It SHALL read
  **`<title>, page <ix>`**, naming the cited document's publication title and the cited page, when a
  title resolved for that document through the document-metadata resource; and **`doc <id>, page
  <ix>`**, the text the marker carried, when none did. In a run's popup these labels are what tells
  the sources apart, and the page belongs in the label because a document server attributes at page
  level: two pages of one publication are two sources and must read as two entries.
- **`body.source.attachment`** — `{type, url, title}`, nested under `source`: the DIAL file URL
  from the file-sharing tool, carried verbatim; the type `application/pdf` stated explicitly — the
  client opens a citation only for exactly that type, and only PDFs are converted at all — and the
  label the pill itself shows. It SHALL carry the same two parts as `body.title` — the title and
  the cited page — differing only in that **the title is shortened to a configured budget**, the
  ellipsis counted within it, or carried whole where the channel names no budget
  (**application-config-schema** owns the field, its default and its null case). The
  page SHALL be appended after the shortening, so a long title never costs the reader the page. A
  citation no title resolved for SHALL NOT be shortened at all: its `doc <id>, page <ix>` is short
  by construction, and cutting it would lose the id or the page.

  The app shortens because the client does not: a pill is a narrow inline element carrying the
  client's own count marker when it stands for a run, and a label that overflows is not trimmed for
  it. The popup card has the room, which is why `body.title` keeps the title whole — a reader who
  needs the full name opens the pill. The app SHALL derive no label from the URL and SHALL decode no
  part of it: the file name inside a shared URL is a storage path segment rather than a title, and
  the document-metadata resource is the only source of a real one. A pill behind a run takes its
  label from the run's first citation and marks how many further sources it carries, which the
  client does on its own. A flat source without the nested attachment is not a valid entry in this
  container and is discarded by the client before rendering.
- **`body.selector`** — a `pdf_bbox` carrying the cited page, with a zero-size box
  (`x1 = y1 = x2 = y2 = 0`). The page is carried here and nowhere else: the tag in the text carries
  no page, and the page SHALL NOT be appended to the URL as a `#page=N` fragment, which the client's
  citation preview does not strip and which therefore breaks opening the file.

No `body.quote` SHALL be sent: the app does not have the cited passage's source text, and an empty
quote reserves blank space in the popup.

The array SHALL be emitted **once**, after the report text has been appended to the choice, as a
single streamed delta on the same choice while it is still open. Annotations SHALL NOT be emitted
through the attachment API, which assigns its own indices and would renumber them.

Emitting after the content costs no pill. The client hides a supported marker tag while the message
is still streaming and resolves no annotations until the message completes, so every pill appears
when the message finishes rather than as the report streams.

#### Scenario: A converted citation's two halves agree

- **WHEN** the step converts a lone citation of document 442, page 3
- **THEN** the delivered text SHALL carry `<cit data-id="X"></cit>` where the marker stood, and the
  annotations array SHALL carry exactly one entry whose `target.selector` names tag `cit` and id `X`

#### Scenario: A titled document labels both halves with its publication title

- **WHEN** the step converts a citation of document 12, page 13, and the document-metadata resource
  reported that document's title as `Market Outlook 2025`
- **THEN** the annotation's `body.title` and its `body.source.attachment.title` SHALL both read
  `Market Outlook 2025, page 13`, and no part of the shared URL SHALL appear in
  either

#### Scenario: An untitled document falls back to the marker's own text

- **WHEN** the step converts a citation of document 12, page 13, and no title resolved for that
  document
- **THEN** both labels SHALL read `doc 12, page 13`, and the citation SHALL still become a pill

#### Scenario: A long title is shortened on the pill and whole on the card

- **WHEN** a resolved publication title is longer than the configured pill budget
- **THEN** `body.source.attachment.title` SHALL carry the title shortened to that budget with an
  ellipsis, followed by the cited page, and `body.title` SHALL carry the whole title with the page

#### Scenario: A title within the budget is untouched

- **WHEN** a resolved title is no longer than the configured budget
- **THEN** both labels SHALL read identically, with no ellipsis

#### Scenario: The pill keeps the page however long the title

- **WHEN** a resolved title is many times the budget
- **THEN** the pill's label SHALL still end with the cited page, because the page is appended after
  the shortening

#### Scenario: Two pages of one publication are two entries

- **WHEN** two adjacent citations name pages 4 and 9 of one titled document and fold into one pill
- **THEN** the pill's popup SHALL carry two entries, their labels differing only in the page, so the
  reader can tell the two cited pages apart

#### Scenario: A run's annotations share one tag id and keep separate indices

- **WHEN** the step converts a run of two citations behind one tag
- **THEN** both annotations SHALL name that tag's id, and they SHALL carry different `index` values,
  so the client keeps them as two sources behind one pill rather than merging them into one

#### Scenario: The same page cited in two places gets two pills

- **WHEN** the same document and page are cited in two different paragraphs
- **THEN** the two positions SHALL carry different tag ids and SHALL produce two annotations, so the
  reader sees a pill at each position rather than one shared between them

#### Scenario: Indices are sequential and unique

- **WHEN** the step emits seven annotations, however many tags they are spread across
- **THEN** the emitted array SHALL carry indices 0 through 6, each used once, in report order

#### Scenario: The page travels in the selector, not the URL

- **WHEN** two citations name page 3 and page 9 of the same document
- **THEN** both annotations SHALL carry the same attachment URL with no fragment, and SHALL differ
  only in the page their `pdf_bbox` selector names

#### Scenario: Annotations follow the content

- **WHEN** the citation step has annotations to emit
- **THEN** the report text SHALL be appended to the assistant content first and the annotations
  SHALL be emitted after it, on the same open choice

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

**A failure of the document-metadata read costs a label and never a pill**, so it is graded one step
lower throughout. On any of the following the app SHALL convert every citation it otherwise would,
labelling from the marker whatever it could not label from a title:

- no configured document-metadata resource, or no configured title key;
- the read raises, times out, or reports an error;
- the answer cannot be read as an id-to-metadata object;
- a requested id is absent from the answer, or carries no usable value under the configured key.

**No configured resource is not a failure** and SHALL be recorded at DEBUG, for the same reason the
absent file-sharing tool is: naming the resource is optional, so an instance that names none would
otherwise warn on every report it delivers. The read raising and an unreadable answer SHALL each be a
WARNING, both being misconfiguration or a server in breach of its contract. **A document that simply
has no title SHALL NOT warn**: a channel's metadata is its own, a missing key there is data variance
rather than a fault, and it costs a plainer label rather than anything the reader loses. How many
titles resolved is carried by the step's own event instead (see **logging-policy**).

**Every record the citation step emits carries counts and the failure kind, and nothing drawn from
a document.** The service's own call sites SHALL NOT log, at any level: a returned URL, any part of
one, a file name taken from one, a document title, or a cited document's id. The mapping is a tool
response body and the metadata object is a resource body, which the content allowlist keeps out of
log records, and the allowlist's permission for DIAL relative `files/...` paths covers URLs the
service handles itself elsewhere — a failed image download it reports — and does not reach into
either. What a record may carry about documents is therefore how many: how many were cited, how many
resolved, how many ids the response omitted, how many titles were found. The one name a record may
carry is the configured tool's, which the allowlist allows as a tool name and which is what makes a
misconfiguration warning actionable.

The step SHALL NOT emit a marker tag it has no annotation for. A tag whose annotation never reaches
the reader — because the step could not emit the array, or because something downstream dropped it —
costs that citation entirely rather than degrading to a visible marker, which is why the two halves
are always produced together.

**A failure in the step's own work is not in the list above, and is handled by stage.** The two
alterations fail independently, and each keeps whatever the earlier one finished:

- The **link pass** raising SHALL deliver the settled draft untouched, with no tag and no
  annotation. Such a delivery may still carry a hyperlink, which the **report-composition**
  capability's guarantee otherwise forbids. The two rules are ordered here rather than left to an
  implementer's judgement: a finished report reaches its reader, and the breach is in the logs.
- The **conversion** raising — marker parsing, block classification, tag replacement, payload
  building — SHALL deliver the text the link pass produced, so the hyperlink guarantee still holds,
  with no tag and no annotation.
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
  as the marker did, the turn SHALL complete successfully, and one WARNING SHALL name the failure

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
- **THEN** that draft SHALL be delivered exactly as the review settled it, no annotation SHALL be
  emitted, the turn SHALL complete successfully, and one WARNING SHALL name the failure

#### Scenario: An exception in the conversion keeps the link removal

- **WHEN** the link pass completed and the marker parsing then raises
- **THEN** the link-free text SHALL be delivered with every citation marker in place, no annotation
  SHALL be emitted, and one WARNING SHALL name the failure

#### Scenario: A failed emission leaves its tags unclaimed

- **WHEN** the report text carrying marker tags has been appended and sending the annotations array
  then fails
- **THEN** the turn SHALL complete successfully, one WARNING SHALL name the failure, and the step
  SHALL NOT attempt to re-send the array or to alter the appended content

#### Scenario: A report with no citations gets no tag and no annotation

- **WHEN** the settled draft cites no document at all
- **THEN** no file-sharing call SHALL be made, no metadata read SHALL be made, no annotations SHALL
  be emitted, and the delivered text SHALL carry no marker tag — differing from the settled draft
  only where the link pass removed something
