## ADDED Requirements

### Requirement: A dataset citation is converted when its dataset resolves a web URL

A `[dataset <id>]` marker SHALL be converted — its marker replaced by a marker tag, one annotation
emitted for it — on one condition: **the cited dataset resolved a URL that a browser can open.**

**A dataset's identifier is called its URN throughout this capability**, and the marker's `<id>`
slot carries it: the report's citation form is `[dataset <id>]`, owned by **research-execution**, but
what fills it for every supported dataset server is a URN such as `IMF:WEO(1.0.0)`. The wire
field the dataset-metadata tool reports it under is `id`, which is the server's key and is not
renamed here; every user-visible mention of it — the card's body row, the fallback labels — reads
`URN`, because that is what the value is and what the dataset server's own documentation calls it.

The dataset-metadata tool must have reported a record for that URN carrying a URL, and that
URL must be **absolute and `http` or `https`**. The app SHALL decide this from the URL itself,
treating any other form — a storage-relative `files/…` path, a scheme it does not recognise, a value
that is not a URL at all — as not convertible. The direction is conservative for the same reason the
PDF check on a document is: a dataset pill exists to take the reader to a page, and a pill that
opens nothing is worse than a marker that at least names its source. A storage-relative URL in
particular would make the client offer a file download rather than a page.

The URN is matched **verbatim**, as **source-attribution** requires: the string the marker carries is
compared to the `id` of each record the tool reported, with no case change, no trimming, no
re-encoding and no version-stripping. A URN carries punctuation — a colon, and often a parenthesised
version — and every character of it is part of the URN.

A dataset citation whose URN the tool did not report, or reported without a usable URL, SHALL keep
its marker text exactly as the report writer wrote it and SHALL produce no annotation. Conversion
SHALL NOT be partial: a converted dataset citation has both its tag and its annotation, or neither.
The failure mode is a missing pill, never a lost citation.

**Neither a dataset's name nor its last-update date is part of the condition.** A dataset that
resolved a URL but no usable name is still converted, its labels reading `<urn> dataset` in place of
`<name> dataset`, the same shape with a different leading string; a dataset that resolved no date is still converted, its quote simply carrying one item
instead of two. This is the same shape of fallback an untitled document gets, for the same reason: a
plainer pill costs the reader less than a missing one.

**Where the marker stands is not a condition**, exactly as for a document citation: the step SHALL
convert a dataset citation in a paragraph, a list item, a table cell, a heading, a blockquote and an
emphasis span alike, and SHALL classify no Markdown block.

#### Scenario: A cited dataset with a portal URL becomes a pill

- **WHEN** a paragraph reads `…rose by 2.1% [dataset IMF:WEO(1.0.0)] over the period.` and the
  dataset-metadata tool reported that id with the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** the marker SHALL be replaced by a marker tag, and one annotation SHALL be emitted naming
  that tag and carrying the portal URL

#### Scenario: A reader reaches the dataset's page from the card

- **WHEN** a reader clicks a converted dataset citation's pill and then its open-in-browser action
- **THEN** the page at `body.source.attachment.url` SHALL open in a new browser tab, and that URL
  SHALL be the string the dataset-metadata tool reported, unchanged

#### Scenario: A dataset the catalogue does not report keeps its text

- **WHEN** the report cites `[dataset IMF:UNKNOWN(1.0.0)]` and the tool's answer carries no record
  with that id
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A dataset reported without a URL keeps its text

- **WHEN** the tool reports the cited dataset's record with a name but no URL
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A storage-relative URL is not convertible

- **WHEN** the tool reports the cited dataset with the URL `files/bucket/catalogue.pdf`
- **THEN** the citation SHALL NOT be converted, because the URL is not an absolute web URL and the
  client would offer a download rather than open a page

#### Scenario: A versioned identifier is matched exactly

- **WHEN** the report cites `[dataset IMF:WEO(1.0.0)]` and the tool reports both
  `IMF:WEO(1.0.0)` and `IMF:WEO(2.0.0)`
- **THEN** the citation SHALL resolve against `IMF:WEO(1.0.0)` alone, the identifier being
  matched character for character

### Requirement: Cited datasets are named and linked through a contracted dataset-metadata tool

A dataset citation needs three things the app does not hold: the dataset's human name, which labels
the pill and the card; the address of its page, which no label shows and which the reader reaches
through the card's open-in-browser action; and
its last-update date, which the card's body carries when the server knows one. Both come from **one MCP tool**, the
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
  date the dataset was last updated. Any other field an element carries SHALL be ignored rather than
  refused, so a server may report a description, a provider or an indicator count without breaking
  the contract.

  The two optional fields are optional in different senses, and the difference is what each absence
  costs. An element whose **`url`** is absent is a dataset that cannot be cited as a pill at all,
  because the pill would open nothing. An element whose **`lastUpdated`** is absent is cited
  normally and simply carries one fewer fact on its card. Neither absence is a malformed answer.

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

The app SHALL select from the answer the records whose `id` equals a cited id, and SHALL ignore
every other record. That the answer is the whole catalogue is a property of the contract rather than
a cost the report pays per citation: one call carries however many datasets the report cites.

#### Scenario: One call serves every cited dataset

- **WHEN** the delivered report cites four datasets and research queried three more it did not cite
- **THEN** the app SHALL call the dataset-metadata tool exactly once, with no arguments, and SHALL
  read the four cited ids out of its answer

#### Scenario: A report citing no dataset makes no call

- **WHEN** the delivered report cites documents only
- **THEN** the app SHALL NOT call the dataset-metadata tool

#### Scenario: Extra fields in a record are ignored

- **WHEN** a reported record carries a description, a provider and a last-update date beside its
  `id`, `name` and `url`
- **THEN** the record SHALL be accepted and only the `id`, the `name` and the `url` SHALL be read
  from it

#### Scenario: A text-only answer is a failed call

- **WHEN** the named tool returns its catalogue as text content with no structured result
- **THEN** the call SHALL be treated as failed, every dataset citation SHALL keep its marker text,
  and the report SHALL be delivered

### Requirement: The dataset-metadata tool is called by the app and stays available to the agent

The app SHALL find the dataset-metadata tool in its server's **full advertised tool list**,
independently of that server's `tools_to_include` filter, because that filter states what the
research agent may call rather than what the app may call. A configuration whose filter omits the
tool SHALL still leave the app able to call it at the citation step.

The dataset-metadata tool SHALL, however, **remain available to the research agent** whenever that
server's filter would otherwise offer it. This is the one point on which it differs from the
file-sharing tool, which the app removes from every tool list bound to a model, and the difference
is deliberate: a catalogue listing is how a research agent discovers which datasets exist before it
queries one, so removing it would spend the research to buy the citation. Naming a tool here SHALL
change only who else calls it, never whether the agent still can.

#### Scenario: Naming the tool does not hide it from the agent

- **WHEN** a server names its dataset-metadata tool and that tool passes the server's
  `tools_to_include` filter
- **THEN** the tools bound to the research agent SHALL still include it

#### Scenario: A filter that omits it does not hide it from the app

- **WHEN** a server's `tools_to_include` names only its data-query tool, and its dataset-metadata
  tool is configured
- **THEN** the app SHALL still be able to call the dataset-metadata tool at the citation step, and
  the agent SHALL NOT be offered it

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

Once the hyperlinks are gone, every remaining marker of those forms is a citation. A **document**
citation is converted — its marker replaced by a marker tag, one annotation emitted for it — on one
condition: **the cited document has a URL the reader can open, and that file is a PDF.** What
converts a **dataset** citation is stated by its own requirement below; the condition there turns on
a page on the web rather than on a file.

The file-sharing tool must have returned a DIAL file URL for that document id. It returns none when
no configured server declares such a tool, when the call fails, or when the response omits that id.
A dataset citation never has one: no file-sharing call is made on a dataset's behalf, because a
dataset is not a file. It is made convertible by a different resolution entirely (see the dataset
requirement below).

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

### Requirement: Citations standing next to each other become one pill

Report prose commonly supports one statement with several sources at once, written as consecutive
markers. Two or more citation markers separated only by spaces, commas or semicolons SHALL be
treated as one **run** and converted together:

- The run SHALL be replaced by **exactly one** marker tag. Emitting one tag per citation would draw
  one pill per citation at the same spot, and two tags carrying the same id would draw the same pill
  twice.
- Every citation in the run SHALL get its own annotation, and all of them SHALL carry **that one
  tag's id**. The client groups annotations by tag id, so one tag with several annotations renders a
  single pill whose popup steps through every source behind it.
- Each of those annotations SHALL still carry its own unique `index`. Two annotations that share a
  tag id and carry no `index` are treated by the client as one annotation, which would silently
  merge two sources into one.
- Within a run, two markers naming the same source SHALL produce one annotation, not two: they are
  one source cited once. For documents that means the same document **and** the same page, a
  document server attributing at page level; for datasets it means the same dataset id, there being
  no finer level to differ at.
- A run MAY hold both convertible and unconvertible citations, and each is still all-or-nothing on
  its own: the citations satisfying the condition fold into one tag placed where the run's first
  marker stood, and each citation failing it keeps its own marker text, in its original order,
  immediately after that tag.
- The separators **inside** a run — the spaces, commas or semicolons standing between its markers —
  SHALL be removed with the markers they joined. What the run leaves behind is the one tag followed
  by each surviving marker text in its original order, single-spaced, so a fold never delivers a
  stray comma or a double space. The characters before the run's first marker and after its last
  are not the run's and SHALL be left alone.

#### Scenario: Three adjacent citations render one pill

- **WHEN** a sentence ends `…as the outlook notes. [doc 1, page 2], [doc 2, page 2], [doc 1, page 2]`
  and both documents resolved
- **THEN** the whole run SHALL be replaced by one marker tag, and two annotations SHALL be emitted
  against that tag's id — document 1 page 2, and document 2 page 2 — so the reader sees one pill
  carrying both sources, with the repeated pair counted once

#### Scenario: Space-separated citations are one run

- **WHEN** a sentence ends `[doc 150, page 1] [doc 150, page 3] [doc 283, page 1]`, the form the
  report writer is told to use for a multi-source statement
- **THEN** the three citations SHALL be converted as one run into one pill carrying three
  annotations

#### Scenario: Citations in separate sentences are separate pills

- **WHEN** two citations are separated by any text other than spaces, commas or semicolons — a word,
  a full stop, a line break
- **THEN** they SHALL NOT form a run, and each SHALL be converted into its own tag and its own pill

#### Scenario: A run whose second document did not resolve

- **WHEN** a run reads `[doc 1, page 2], [doc 9, page 3]`, a URL resolved for document 1, and none
  resolved for document 9
- **THEN** one tag SHALL be emitted for document 1's citation, and document 9's marker SHALL remain
  as text immediately after that tag

#### Scenario: A document citation and a dataset citation in one run share a pill

- **WHEN** a sentence ends `[doc 1, page 2], [dataset IMF:WEO(1.0.0)]`, a URL resolved for
  document 1, and a portal URL resolved for that dataset
- **THEN** the run SHALL be replaced by one marker tag carrying two annotations — the document's and
  the dataset's — so the reader sees a single pill whose popup steps through both, and neither
  marker SHALL remain as text

#### Scenario: A run whose dataset did not resolve

- **WHEN** a run reads `[doc 1, page 2], [dataset IMF:WEO(1.0.0)]`, a URL resolved for document
  1, and the catalogue reported no URL for that dataset
- **THEN** one tag SHALL be emitted for the document's citation, and the dataset marker SHALL remain
  as text immediately after that tag

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
  level: two pages of one publication are two sources and must read as two entries. A **dataset**
  citation's label SHALL read **`<name> dataset`** when the dataset-metadata tool reported a usable
  name, and **`<urn> dataset`** — the URN the marker carried — when it did not.

  The trailing word is not decoration: a dataset's name is often a bare noun phrase such as
  `World Economic Outlook`, which says nothing about what kind of source it is, and a URN alone says less
  still. It is present in **both** cases on purpose, so that a pill and a card read the same way
  whether or not a name resolved — the two differ in what fills the leading slot and in nothing else.
  A reader meeting one of each in the same report should not be able to tell that one of them fell
  back.

  The label SHALL carry **no URL**; the address the citation opens lives in
  `body.source.attachment.url`, which is the field the client follows, and showing it again would
  spend the card's most prominent line on a string the reader does not have to read. A dataset cited
  twice in one run is one source cited once, a dataset server attributing to the dataset rather than
  to a location inside it.
- **`body.source.attachment`** — `{type, url, title}`, nested under `source`: the URL this citation
  opens, carried verbatim, and the label the pill itself shows.

  **The type SHALL be stated explicitly and SHALL say what is cited**: `application/pdf` for a
  document citation, whose URL is the DIAL file URL the file-sharing tool returned, and `text/html`
  for a dataset citation, whose URL is the page the dataset-metadata tool returned. The type is
  load-bearing rather than decorative, because the client branches on it twice: it opens a citation
  into its document viewer only for `application/pdf`, and it offers the reader an open-in-browser
  action — the one action that reaches a page on the web — only for an HTML type. A dataset citation
  labelled `application/pdf` would therefore offer a download of a page that is not a file.

  **This field is the only place a dataset's address exists in the payload, and the only way a reader
  reaches it.** The reader's path is two clicks and both belong to the client: clicking the pill
  opens the citation card, and the card's open-in-browser action opens `url` in a new browser tab.
  The pill's own click does **not** follow the URL — it opens the card — and the app cannot change
  that, because what a pill does on click is the client's behaviour and no field of the annotation
  selects it. Where a run of citations shares one pill, that action applies to whichever source the
  card's switcher is showing, so a dataset cited beside a document is reached by stepping to its
  entry first.

  The app SHALL carry the URL into this field exactly as the dataset-metadata tool reported it,
  decoding nothing and re-encoding nothing, for the reason the file-sharing URL is carried verbatim:
  the client resolves it, and any rewriting risks an address that no longer names the page.

  **This label is what the pill itself shows, and it is not `body.title`.** For a **document**
  citation it carries the same two parts as `body.title` — the publication title and the cited page —
  differing only in that **the title is shortened to a configured budget**, the ellipsis counted
  within it, or carried whole where the channel names no budget (**application-config-schema** owns
  the field, its default and its null case); the cited page SHALL be appended **after** the
  shortening, so a long title never costs the reader the page. For a **dataset** citation it carries the
  same two parts its `body.title` carries — the name, or the URN when no name resolved, followed by
  `dataset` — with **`dataset` appended after the shortening**, exactly as a document's cited page is
  appended after its title's. So the pill reads **`<shortened name> dataset`** or
  **`<shortened urn> dataset`**, and never loses the word that says what the leading string names.

  Appending after the shortening is what makes the two cases the same shape. A URN has no bounded
  length — `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` is forty characters against a default budget
  of twenty — so a fallback label must be shortened or it overflows, and shortening it without
  re-appending the word would leave a truncated string with nothing saying what it is. Applying the
  same rule to the resolved case costs one word of width and buys a pill whose structure does not
  betray whether the lookup succeeded.

  A **document** citation that resolved no title is the one label that is not shortened at all: its
  `doc <id>, page <ix>` is short by construction, and cutting it would lose the id or the page.

  No label SHALL carry a URL. A dataset's address reaches the reader only as the link the pill
  follows.

  The app shortens because the client does not: a pill is a narrow inline element carrying the
  client's own count marker when it stands for a run, and a label that overflows is not trimmed for
  it. The popup card has the room, which is why `body.title` keeps the title whole — a reader who
  needs the full name opens the pill. The app SHALL derive no label from the URL and SHALL decode no
  part of one: the file name inside a shared URL is a storage path segment rather than a title, the
  trailing segment of a portal URL is a slug rather than a name, and the contracted metadata surfaces
  are the only source of a real one. No URL SHALL appear in any label, in whole or in part, on either
  the pill or the card. A pill behind a run takes its
  label from the run's first citation and marks how many further sources it carries, which the
  client does on its own. A flat source without the nested attachment is not a valid entry in this
  container and is discarded by the client before rendering.
- **`body.selector`** — for a **document** citation, a `pdf_bbox` carrying the cited page, with a
  zero-size box
  (`x1 = y1 = x2 = y2 = 0`). The page is carried here and nowhere else: the tag in the text carries
  no page, and the page SHALL NOT be appended to the URL as a `#page=N` fragment, which the client's
  citation preview does not strip and which therefore breaks opening the file. For a **dataset**
  citation the field SHALL be **omitted** entirely: a dataset citation names no location inside what
  it cites, and a page selector on a source that is not a PDF would name a page of a file that does
  not exist.

**A citation's labels have the same shape whether or not its metadata resolved.** This holds for
documents and datasets alike, and it is a requirement rather than a consequence.

Every label is a **leading part** naming the source, followed by a **fixed trailing part** saying
what kind of source it is and, for a document, which page of it:

| Citation | Resolved | Not resolved |
|---|---|---|
| document | `<title>, page <ix>` | `doc <id>, page <ix>` |
| dataset | `<name> dataset` | `<urn> dataset` |

What a failed lookup changes is **only what fills the leading slot** — the server's name for the
source, or the identifier the report's marker carried. It SHALL NOT change the shape, SHALL NOT drop
the trailing part, and SHALL NOT mark the citation as degraded in any way a reader can see: no
"unknown", no "untitled", no bracket, no icon. A reader meeting a resolved and an unresolved citation
in the same report SHALL NOT be able to tell which is which from the label's structure. Whether the
app reached a metadata surface is the app's problem, and a reader who is shown it learns nothing they
can act on while being invited to trust one citation less than another that is equally real.

The trailing part is **appended after any shortening**, so it survives a leading part of any length.
The one label that is not shortened at all is an **unresolved document's**: `doc <id>, page <ix>` is
short by construction, and at the minimum configurable budget shortening it could eat the id. An
unresolved dataset's is shortened, because a URN has no bounded length.

**A document citation SHALL send no `body.quote`**: the app does not have the cited passage's source
text, and an empty quote reserves blank space in the popup.

**A dataset citation SHALL send a `body.quote`** carrying what the reader needs in order to judge the
source, which for a dataset is not a passage but the dataset's own identity and currency. It SHALL be
a Markdown list of up to two items, in this order:

- `* URN: <urn>` — the URN the marker carried, always present.
- `* Last update: <date>` — the date the dataset-metadata tool reported for that dataset, **omitted
  entirely** when the tool reported none. A missing date SHALL NOT produce an empty item, a `null`,
  or a placeholder such as "unknown": the reader learns nothing from a line that says the app knows
  nothing, and an absent date is ordinary rather than a fault.

The date SHALL be carried **exactly as the tool reported it**, with no reformatting, no locale
rendering and no relative phrasing ("3 months ago"), for the reason **source-attribution** gives for
identifiers: the app is not the authority on what the server's value means.

The field is Markdown rather than plain text because the client renders this one through its Markdown
renderer, unlike `body.title`, and the list is what makes two facts read as two facts in a narrow
card.

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

#### Scenario: A titled and an untitled document produce the same label shape

- **WHEN** one report converts a document citation whose title resolved and another whose title did
  not
- **THEN** both labels SHALL end `, page <ix>` and both SHALL differ only in whether the leading part
  is the publication title or `doc <id>`, and neither SHALL carry any marker of having fallen back

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

#### Scenario: A dataset citation carries a web source and no page

- **WHEN** the step converts `[dataset IMF:WEO(1.0.0)]`, the dataset-metadata tool reported the
  name `World Economic Outlook` and the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** the annotation's `body.source.attachment.type` SHALL be `text/html`, its `url` SHALL be
  that portal URL unchanged, `body.title` SHALL read `World Economic Outlook dataset`,
  `body.source.attachment.title` SHALL read `World Economic Outlook` shortened to the channel's budget,
  `body.quote` SHALL carry the URN item and, when a date was reported, the last-update item,
  `body.selector` SHALL be absent, and no label SHALL carry the URL

#### Scenario: An unnamed dataset falls back to the marker's own text

- **WHEN** the step converts a citation of dataset `IMF:WEO(1.0.0)`, a portal URL resolved for
  it and the catalogue reported no usable name
- **THEN** `body.title` SHALL read `IMF:WEO(1.0.0) dataset`,
  `body.source.attachment.title` SHALL read the URN shortened to the channel's budget with `dataset`
  appended after the shortening, and the citation SHALL still become a pill

#### Scenario: A named and an unnamed dataset produce the same label shape

- **WHEN** one report converts a dataset citation whose name resolved and another whose name did not
- **THEN** both pills SHALL read `<leading string, shortened> dataset` and both cards SHALL read
  `<leading string> dataset`, the two differing only in whether the leading string is the name or the
  URN

#### Scenario: The pill and the card say different things about one dataset

- **WHEN** a dataset citation resolves the name `Primary Commodity Prices` and a portal URL, and the
  channel's pill budget is 20 characters
- **THEN** the pill SHALL read that name shortened to 20 characters followed by ` dataset`, the word
  appended after the shortening, and the card SHALL read `Primary Commodity Prices dataset`, the whole
  name with the same trailing word

#### Scenario: A dataset whose last-update date is unknown carries one quote item

- **WHEN** the dataset-metadata tool reports the cited dataset with an id and a URL but no
  last-update date
- **THEN** `body.quote` SHALL carry the `URN` item alone, that row dropped from the list entirely,
  with no empty item and no placeholder text

#### Scenario: The last-update date is carried as the tool reported it

- **WHEN** the tool reports the cited dataset's last-update date as `2025-04-30`
- **THEN** `body.quote` SHALL carry `* Last update: 2025-04-30`, that string unchanged, and the app
  SHALL NOT reformat it into another date format or into a relative phrase

### Requirement: A flag-gated demo completion exercises the citation mechanism

The app SHALL register a second chat completion whose only purpose is to demonstrate and verify
inline citations, on a deployment id of its own, **only** when its environment flag is set. The flag
SHALL default to off, so an ordinary deployment registers only the product completions. The demo
SHALL read no application properties, run no research, and call no model: it answers with a fixed
report.

**It SHALL build its annotations with the same code the research turn uses** — the same marker
parsing, run folding, hyperlink removal, tag replacement, payload building and emission. That code
SHALL live where both callers reach it, so no change can make the demo and the delivered report
disagree about the mechanism. A behaviour that holds in the demo therefore holds in a real report,
which is what makes the demo evidence rather than an illustration.

The one permitted difference is **where the file URLs come from**. A research turn resolves them
through the configured file-sharing tool; the demo cites the PDFs the caller attached to the last
message and feeds their URLs into the shared code. A demo has to be self-contained and to produce
the same reply on every environment, which a dependency on a live retrieval server and its document
ids would prevent. An attachment already lives in the caller's own storage, so the demo SHALL copy
nothing anywhere: the annotation points at the attachment's own URL, which the caller can open.

The demo SHALL take one attachment per document it cites an attachment for, in the order they
arrive, and which attachment becomes which document SHALL NOT change what any case demonstrates. It
SHALL refuse an attachment that is not a PDF, one carrying no URL, and one whose URL the shared
PDF-URL rule would reject — a URL that rule rejects draws no pill, so accepting it would show a
broken case as if the mechanism were at fault.

**It SHALL check that each attachment is deep enough** to hold every page the report cites, and the
page it checks against SHALL be read out of the report rather than written down beside it, so a case
citing a new page cannot disagree with the number checked. The report SHALL cite only the first few
pages of a document, so an ordinary short PDF is usable.

**Its fixed report SHALL exercise every behaviour of the mechanism**, so that a reader of the
rendered reply can see each one and a client change that breaks one is caught:

- a lone citation in a paragraph;
- a run of adjacent citations, which folds into one pill carrying several sources;
- the same document cited in several separate places, each rendering its own pill;
- a citation in a list item;
- two pages of one document, so page navigation can be compared between pills;
- a citation in a table cell, which renders a pill there as it does in prose;
- a citation in a heading, which renders a pill there as it does in prose;
- a citation whose document has no URL, which keeps its marker text;
- a Markdown link, which is delivered as its label alone;
- a bare URL, which is deleted from the delivered text.

Dataset citations SHALL NOT appear. The demo cites the caller's own attachments and holds no portal
URL for any dataset, so the only dataset citation it could show is one that fails to convert — which
demonstrates nothing the unresolved-document case does not already demonstrate.

**The demo's reply SHALL consist of the case descriptions and nothing else.** Each demonstrated
behaviour SHALL be introduced by a sentence saying what it is and what should appear — in the shape
of "Here is a citation in a list item: it becomes a pill, as in a paragraph" — so a reader can look
at that spot and tell a correct rendering from a broken one without reading this specification. The exact wording is the implementation's, but no case may be left for the reader to
infer from position.

Beyond those descriptions the reply SHALL carry only the Markdown a case needs in order to exist at
all: a one-row table for the table-cell case, a heading for the heading case, a list item for the
list-item case. It SHALL NOT carry research prose, invented findings, or report sections that no case
requires. Every sentence in the reply is there to be checked, so filler would dilute what the
verifier is looking at, and content that reads like a report would invite judging the findings
instead of the rendering.

The deployment SHALL also be documented for that audience: how to enable it, which deployment id to
call, and what to look for in the reply.

#### Scenario: The demo is absent unless its flag is set

- **WHEN** the app starts with the demo flag unset
- **THEN** only the product completions SHALL be registered, and a request to the demo's deployment
  id SHALL NOT be served

#### Scenario: The demo and a real report cannot diverge

- **WHEN** the citation mechanism changes — how a run folds, what the payload carries, how a tag is
  written
- **THEN** the demo SHALL exhibit the changed behaviour without an edit of its own, because it calls
  the same code, and no requirement above SHALL be satisfiable in one and not the other

#### Scenario: The demo's pills open for the person clicking them

- **WHEN** a caller attaches two PDFs, sends any message, and clicks a pill in the reply
- **THEN** the cited file SHALL open at the cited page, because the annotation points at the
  caller's own attachment rather than at a file in another bucket

#### Scenario: Every mechanism behaviour is visible in one reply

- **WHEN** the demo answers
- **THEN** its single reply SHALL contain each case listed above, each introduced by a sentence
  naming that case and the rendering to expect from it, and SHALL contain nothing else beyond the
  Markdown constructs those cases need

#### Scenario: A verifier can judge a case without outside knowledge

- **WHEN** someone outside this project opens the demo's reply and looks at the citation inside a
  table cell
- **THEN** the text at that spot SHALL have told them what to expect there, so they can tell the
  intended rendering from a broken one on the spot

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

**A failure of the document-metadata read costs a label and never a pill**, so it is graded one step
lower throughout. On any of the following the app SHALL convert every citation it otherwise would,
labelling from the marker whatever it could not label from a title:

- no document server configured, and so no document-metadata resource;
- the read raises, times out, or reports an error;
- the answer cannot be read as an id-to-metadata object;
- a requested id is absent from the answer, or carries no usable value under the configured key.

**No configured resource is not a failure** and SHALL be recorded at DEBUG, for the same reason the
absent file-sharing tool is: a document server must name the resource, so only a deployment with no
document server can be configured that way, and it has no document citations to label. The read raising and an unreadable answer SHALL each be a
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
resolved, how many ids the response omitted, how many titles were found. The same holds of
datasets, and of everything a dataset record carries: a dataset's name, its portal URL and any part
of one, and a cited dataset's id SHALL NOT be logged at any level. The one name a record may
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

**A document server must name both**, as it must name its file-sharing tool
(**application-config-schema** owns that rule and what it costs): a document id is internal to the
server that issued it, so a channel with no metadata resource labels every pill with a number the
reader cannot place. What stays optional is the **answer** — an id the resource does not know, or a
document carrying nothing usable under the configured key, costs that citation its title and
nothing else.

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

The app SHALL read it **once per turn**, asking for **every document id the delivered report
cites**. A title SHALL NOT label a citation that was not converted, and SHALL NOT be counted among
the titles resolved (see **logging-policy**).

Asking for every cited id rather than only the resolved ones is what frees this read from the
file-sharing call's answer, so the two run **together** rather than one after the other and the step
costs one round trip instead of two.

The constraint on the surplus is deliberately about **use** rather than about disposal. What must be
observably true is that no title reaches a label or a count it has not earned — not that the app
forgets the value. The distinction is not pedantry: a title read for a document that resolved no URL
is still a fact the server reported about a source the report genuinely cites, and the report's
References section, which this capability does not yet own, must list every source the report cites
whether or not its metadata resolved. A rule phrased as "discard it" would have to be unwritten to
build that. The surplus itself is cheap — a few more ids in one URI, a few more entries in one answer
— and it is paid only on turns where the file-sharing call did not resolve everything.

The resource SHALL NOT be offered to any LLM. It is read by application code at the citation step,
and an MCP resource does not appear in a tool listing, so nothing has to be filtered out of the
agent's tools for this to hold.

#### Scenario: One read covers every cited document and its surplus is discarded

- **WHEN** the settled draft cites five documents and the file-sharing tool returned URLs for three
  of them
- **THEN** the app SHALL make exactly one document-metadata read, asking for all five ids, and SHALL
  label citations from the titles of the three that resolved a URL and from no others

#### Scenario: The metadata read does not wait for the file-sharing call

- **WHEN** a turn's citation step resolves documents and datasets
- **THEN** the document-metadata read SHALL be issued without waiting for the file-sharing call's
  answer, the ids it asks for being known from the report text alone

#### Scenario: A title for a document that resolved no URL is not shown

- **WHEN** the answer carries a usable title for a document the file-sharing tool returned no URL for
- **THEN** that document's citations SHALL keep their marker text, no annotation SHALL be emitted for
  them, and that title SHALL NOT be counted among the titles resolved

#### Scenario: The configured key decides which value is the title

- **WHEN** a document's metadata object carries several string values and the configuration names one
  key
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

## REMOVED Requirements

### Requirement: Dataset citations are never converted

**Reason**: The requirement rested on a premise that no longer holds. It stated that a dataset is
not a file, so there is nothing for the reader's viewer to open and nothing to copy into their
bucket — which is still true — and concluded that a dataset citation therefore cannot become a pill.
The conclusion does not follow, because a citation does not have to open a file: an annotation's
attachment URL may be an absolute web URL, and the client opens such a URL in a new browser tab.
The dataset server reports a page per dataset, so the address exists, and nothing has to be copied
anywhere for the reader to reach it. The requirement's own closing sentence named what was missing —
"what a dataset pill should link to, and where such a link should open, is undecided" — and both are
now decided.

**Migration**: Replaced by three requirements above: *A dataset citation is converted when its
dataset resolves a web URL* states the condition and the failure modes, *Cited datasets are named
and linked through a contracted dataset-metadata tool* states where the name and the URL come from,
and *The dataset-metadata tool is called by the app and stays available to the agent* states how
that tool is resolved. A deployment that has not configured a dataset-metadata tool keeps exactly
the old behaviour — every dataset marker delivered as text — so no configuration change is required
of anyone who does not want dataset pills.
