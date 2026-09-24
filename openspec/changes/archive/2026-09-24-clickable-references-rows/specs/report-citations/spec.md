## MODIFIED Requirements

### Requirement: A converted citation is a marker tag in the text and an annotation that names it

Conversion produces two halves that find each other by a shared id.

**In the report text**, one empty citation marker tag, `<cit data-id="…"></cit>`, stands where the
citation's marker stood. An id SHALL be opaque and SHALL appear on exactly one tag in the message:
one tag per converted position, whether that position held a single citation or a run of adjacent
ones. Two citations of the same document and page in **different** positions therefore carry
different ids and render as two pills. The tag SHALL be emitted empty — it anchors a pill at its own
position and does not enclose the cited sentence.

**In `custom_content.annotations`**, one entry per converted citation — so a run of three sources
behind one tag contributes three entries that share that tag's id — carrying the fields below. The
References section adds one entry per row it makes openable, after these; that entry's labels and
page are owned by the References requirement, and every other field is the one below. Each entry
carries:

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
  length — `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` is forty characters against a budget of
  twenty — so a fallback label must be shortened or it overflows, and shortening it without
  re-appending the word would leave a truncated string with nothing saying what it is. Applying the
  same rule to the resolved case costs one word of width and buys a pill whose structure does not
  betray whether the lookup succeeded.

  A **document** citation that resolved no title is the one label that is not shortened at all: its
  `doc <id>, page <ix>` is short by construction, and cutting it would lose the id or the page.

  No label SHALL carry a URL. A dataset's address reaches the reader only as the link the pill
  follows.

  The app shortens, where a channel sets a budget, because the client does not: a pill is a narrow
  inline element carrying the client's own count marker when it stands for a run, and a label that
  overflows is not trimmed for it. A channel that sets no budget gets every label whole, which is
  the default. The popup card has the room, which is why `body.title` keeps the title whole — a reader who
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
report cites**, in the order the servers are configured. Each table SHALL open with a `###`
sub-heading carrying that server's configured table title, and its header row SHALL be the columns
that server's `references_table` configures, in the configured order.

A server whose sources the report does not cite SHALL contribute no table at all. Where the report
cites no source of any kind, the section SHALL carry no table and SHALL carry
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
file-sharing tool returned a PDF URL for that document, and a dataset row when the dataset-metadata
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
carry the attachment type, the URL and, for a dataset, the `body.quote` that a converted citation of
the same source carries (the requirement "A converted citation is a marker tag in the text and an
annotation that names it"), and SHALL differ from it in two things:

- **The label is the row's name alone.** `body.title` SHALL carry the text the first cell would have
  carried: the value under the first column's key, rendered by the cell rules above, or the source's
  identifier where that key resolves nothing. The `|` escape SHALL NOT be applied, because the label
  is not table text and a reader would see the backslash; a line break still becomes a space. The
  label SHALL carry **no trailing part** — no `, page <ix>` and no ` dataset` — because the row
  already sits under a sub-heading naming its kind of source, and a References row names the
  source, never the cited location. `body.source.attachment.title` SHALL carry the same text,
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
produced — after the link-removal pass and after the conversion — and SHALL therefore reach both the
assistant message content and the persisted report message. It SHALL NOT be searched for citation
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

- **WHEN** a delivered report cites no document and no dataset
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

- **WHEN** a delivered report cites `IMF:WEO(1.0.0)`, and the dataset-metadata tool reported the name
  `World Economic Outlook` and the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** that row's first cell SHALL carry one marker tag, and its annotation SHALL carry type
  `text/html`, that URL unchanged, the `body.quote` a citation of that dataset carries, no selector,
  and both labels reading `World Economic Outlook` with no ` dataset`

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
- The **References build** raising SHALL deliver the converted text with every pill it earned, no
  References section and no row annotation, since the section and its row annotations are the only
  things that pass produces. It SHALL NOT cost a citation its pill, the conversion having already
  finished.
- The **emission** failing after the text was appended leaves that text's tags unclaimed, and the
  client shows an unclaimed tag to the reader as text. An openable References row then shows its
  tag and no name, because the tag stands in place of the name; the cost is accepted, since the
  same failure already costs every inline pill. The step SHALL NOT re-send the
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
  earned, no References section and no row annotation SHALL be emitted, the turn SHALL complete
  successfully, and one WARNING SHALL name the failure

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
