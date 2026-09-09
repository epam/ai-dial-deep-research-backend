## Purpose

Turns the document citations of the delivered report into DIAL inline citation annotations, so a
reader can open the cited page of a cited document from the report itself. Owns which citations may
be converted and which stay as text, how citations supporting one statement share a pill, the
hyperlinks it removes on the way, the
contract the file-sharing tool must satisfy, the annotation payload, and what happens when any part
of it fails.

## ADDED Requirements

### Requirement: A citation step runs after the report loop settles and before delivery

The app SHALL run one citation step per turn, after the report review loop has settled on the draft
to deliver (see **report-composition**) and before that draft's text is appended to the assistant
message content. The step SHALL NOT run at all on a turn that delivers no report.

The step SHALL be the only thing that alters the settled draft, and it SHALL make exactly two kinds
of alteration, in this order:

1. **Remove everything that points the reader outward** — every hyperlink form the
   **report-composition** capability enumerates, each repaired the way that capability states: the
   label kept where the form has one, the construct deleted whole where it has none. That capability
   owns which forms count and how each is repaired; this step owns only that they go first.
2. **Replace each convertible citation marker** with that citation's marker tag.

The order is fixed so the outcome is deterministic, not because either pass repairs the other's
input: link removal runs first, and citation conversion then reads the text it produced, making no
distinction about where a marker came from. Nothing else about the draft SHALL be rewritten,
reordered, shortened or reformatted, and the step SHALL NOT call a model. What the link pass
deliberately leaves alone is stated by the **report-composition** capability.

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
- **THEN** the step SHALL still run on it: the URL SHALL be gone from the delivered text and the
  citation SHALL be converted, because the step is gated on a report being delivered and never on a
  review having judged it

#### Scenario: A turn with no report runs no citation step

- **WHEN** a turn ends without a delivered report — the preparation agent asked a clarifying
  question, or the turn failed
- **THEN** no citation step SHALL run and no annotations SHALL be emitted

#### Scenario: The delivered text is what gets persisted

- **WHEN** the citation step converts citations in the settled draft
- **THEN** the text appended to the assistant content and the text persisted as the report message
  SHALL be identical to each other, SHALL carry the marker tags of the converted citations, and
  SHALL be the post-processed text rather than the draft the review judged

### Requirement: A citation is converted when the document it names has a PDF URL

The report is written entirely in the inline citation forms the **research-execution** capability
defines: `[doc <id>, page <ix>]` for a document and `[dataset <id>]` for a dataset.

**What the step recognizes as a marker** is exactly those two forms, with a positive integer id and,
for the document form, a positive integer page; the keyword SHALL be matched without regard to case.
Anything resembling a marker without matching — a non-numeric id, a page range
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
- Within a run, two markers naming the same document **and** the same page SHALL produce one
  annotation, not two: they are one source cited once.
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

### Requirement: Dataset citations are never converted

`[dataset <id>]` markers SHALL be left in the delivered text exactly as written, and no annotation
SHALL be emitted for them. This is specified behavior, not an omission.

The reason is the condition: a dataset is not a file, so there is nothing to copy into the reader's
bucket and nothing for the document viewer to open, and no file-sharing tool call is made on a
dataset's behalf. What a dataset pill should link to, and where such a link should open, is undecided
and out of scope for this change. A report that cites datasets therefore delivers those citations as
text alongside its converted document citations.

#### Scenario: A dataset citation stays as text

- **WHEN** a paragraph of the settled draft reads `…grew by 2.1% [dataset ABC:DEF] over the period.`
- **THEN** the marker SHALL remain in the delivered text, no annotation SHALL be emitted for it, and
  no file-sharing call SHALL be made on its behalf

#### Scenario: Mixed citations in one report

- **WHEN** the settled draft cites both documents and datasets
- **THEN** the document citations SHALL be converted where the condition holds, and every
  dataset citation SHALL remain as text

#### Scenario: A dataset citation adjacent to a document citation

- **WHEN** a sentence ends `[doc 1, page 2], [dataset ABC:DEF]`
- **THEN** the document citation SHALL be converted into a tag and the dataset marker SHALL remain
  as text immediately after it, exactly as any other unconvertible citation in a run

### Requirement: Cited documents are made readable through a contracted file-sharing tool

A cited document lives in the retrieval server's own DIAL storage, which the person reading the
report cannot read: DIAL Core grants an ordinary user session access only to resources under that
user's own bucket. A citation SHALL therefore point at a copy of the document inside the **caller's
own** bucket, under the `appdata` folder DIAL Core reports for a per-request key — the one location
an application may write into another identity's bucket.

The app SHALL obtain those copies by calling one MCP tool, the **file-sharing tool**, and SHALL
depend on nothing about it beyond the contract stated here. What this capability owns is that
contract. Which server provides the tool, what that server names it, how it decides which file
answers a document id, and how it performs the copy are all outside the contract, and the app SHALL
behave identically for any server that satisfies it.

**The name comes from configuration.** Each MCP server entry in the application properties SHALL
be able to name that server's file-sharing tool, and the app SHALL call exactly the tool that
entry names (**application-config-schema** owns the field). There SHALL be no default name and no
discovery by convention: the app SHALL NOT infer the tool from a server's advertised tool list,
from a tool's description, or from any naming pattern. An operator who has named no tool has
switched inline citations off, and a server whose tool is named differently is a configuration
entry away from working rather than a code change away. At most one configured server may name a
file-sharing tool, because a `[doc <id>]` marker names no server and ids coming from two servers
could not be told apart.

**The contract.** A tool named as a server's file-sharing tool SHALL satisfy all of the following.
These are requirements on the server, not observations of any one implementation: a named tool that
breaks any of them is a misconfiguration, and it SHALL fail the way the delivery-failure requirement
below prescribes rather than degrade the report.

- **Input**: exactly one argument, named `document_ids`, holding the ids of the documents to share.
  These are the ids the report's `[doc <id>, page <ix>]` markers carry, as the
  **research-execution** capability defines them. The app SHALL pass the ids and nothing else; the
  argument name is fixed by this contract so that the app needs no per-server mapping.
- **Effect**: by the time the tool returns, each document it reports SHALL already have a copy in
  the caller's `appdata` folder that the caller can read. The app SHALL NOT perform, complete or
  verify any copy of its own, and SHALL treat a reported URL as readable.
- **Output**: one JSON object at the top level, with no wrapper key, mapping each shared document id
  to the DIAL file URL of its copy. Keys MAY arrive as JSON strings rather than numbers, since JSON
  has no integer keys, and the app SHALL accept either. Each URL SHALL be in DIAL's storage form:
  relative to the storage root, beginning `files/`, carrying no scheme and no host, with
  percent-encoded segments — the form DIAL's own attachment `url` field takes. The app SHALL carry
  that URL into the annotation exactly as returned, decoding nothing and re-encoding nothing, since
  the client resolves it against the storage root and any rewriting risks a URL that no longer names
  the file.
- **Structured result**: the tool SHALL return that object as its MCP **structured result**, which
  means declaring the output schema MCP requires for one. The app reads the structured result and
  nothing else — a tool that answers with text content alone SHALL be treated as a failed call (see
  the delivery-failure requirement below). MCP carries the same object a second time as serialized
  text, which the app ignores; that copy exists for clients that predate structured results.
- **Partial answers**: an id the tool cannot resolve MAY be absent from the object, and its absence
  SHALL neither make the call fail nor invalidate the ids that are present.
- **Idempotent**: the app calls the tool once per turn with every cited id, and repeated calls for
  the same document across turns SHALL be safe and SHALL NOT require the document to be transferred
  again.

The app SHALL call the tool **once per turn**, with the distinct document ids the delivered report
cites. So: not once per citation, and not for a document retrieved during research but never cited
in the delivered report.

A server with no file-sharing tool configured SHALL contribute no annotations, and its documents'
citations SHALL keep their marker text.

Resolving the caller's `appdata` folder requires the per-request key, which reaches the MCP server
only when it is called through DIAL Core in deployment mode. DIAL Core reports an `appdata` path
only for such a key: asked with an ordinary api-key, `GET /v1/bucket` answers with the bucket alone
and no `appdata` field, so there is no destination to copy into. A file-sharing tool on a
directly-connected server authenticated with a static api-key SHALL therefore NOT be expected to
resolve the reader's bucket, and a deployment that wants inline citations SHALL reach its retrieval
server in deployment mode.

#### Scenario: One call carries every cited document id

- **WHEN** the settled draft cites nine passages drawn from three documents, and research read
  twenty more documents it did not cite
- **THEN** the app SHALL make exactly one file-sharing tool call, passing the three cited document
  ids and no others

#### Scenario: A partially resolved response converts what it can

- **WHEN** the response carries URLs for two of the three requested ids
- **THEN** the citations of those two documents SHALL be converted, and the third document's
  citations SHALL keep their marker text

#### Scenario: No configured tool leaves the report as written

- **WHEN** no configured MCP server declares a file-sharing tool
- **THEN** no file-sharing call SHALL be made, no annotations SHALL be emitted, and the delivered
  report SHALL carry every marker exactly as the writer wrote it

#### Scenario: The app calls the tool the configuration names and no other

- **WHEN** a server advertises several tools, one of which its configuration names as the
  file-sharing tool
- **THEN** the citation step SHALL call exactly the named tool, and SHALL call no other tool of that
  server — including one whose name or description suggests it shares files

#### Scenario: A server satisfying the contract under a different tool name works unchanged

- **WHEN** a retrieval server whose file-sharing tool has a different name from the previous
  deployment's is configured, and it satisfies the contract
- **THEN** the citation step SHALL work with no code change, the only difference being the name in
  that server's configuration entry

### Requirement: The file-sharing tool is called by the app and never offered to the agent

The file-sharing tool SHALL NOT be part of the tool list bound to any LLM: not the research agent's,
not the report writer's, not the playground's. It is invoked by application code at the citation
step and at no other point in the turn.

The app SHALL find it in the server's full advertised tool list, independently of that server's
`tools_to_include` filter, because that filter states what the research agent may call rather than
what the app may call. A configuration that lists the file-sharing tool in `tools_to_include` SHALL
still not result in the agent being offered it.

#### Scenario: The agent's tool list excludes it

- **WHEN** a server declares a file-sharing tool and the research graph starts
- **THEN** the tools bound to the research agent SHALL NOT include it, and the agent SHALL have no
  way to call it

#### Scenario: A filter that omits it does not hide it from the app

- **WHEN** a server's `tools_to_include` names only its search tools, and its file-sharing tool is
  configured
- **THEN** the app SHALL still be able to call the file-sharing tool at the citation step

#### Scenario: A filter that names it does not expose it to the agent

- **WHEN** a server's `tools_to_include` names the file-sharing tool alongside its search tools
- **THEN** the agent's bound tools SHALL still exclude it

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
- **`body.title`** — the label of this citation's entry inside the pill's popup, reading
  `doc <id>, page <ix>` for the cited document and page, so a reader can tie the entry to the
  report's references section now that the inline marker is gone. In a run's popup these labels are
  what tells the sources apart.
- **`body.source.attachment`** — `{type, url, title}`, nested under `source`: the DIAL file URL
  from the file-sharing tool, carried verbatim; the type `application/pdf` stated explicitly — the
  client opens a citation only for exactly that type, and only PDFs are converted at all — and the
  label the pill itself shows, which SHALL read `doc <id>, page <ix>`, the same string as this
  citation's `body.title`. The app has no document title to show: the only human-readable text it
  holds is the file name inside the shared URL, which is a storage path segment rather than the
  document's title, and the document-metadata contract this change leaves out is what would supply
  a real one. So the app SHALL derive no label from the URL, and SHALL decode no part of it. Both
  fields carry the same string deliberately, because the client uses one to label the pill and the
  other to label the entry inside its popup. A flat source without the nested attachment
  is not a valid entry in this container and is discarded by the client before rendering. A pill
  behind a run takes its label from the run's first citation and marks how many further sources it
  carries, which the client does on its own.
- **`body.selector`** — a `pdf_bbox` carrying the cited page, with a zero-size box
  (`x1 = y1 = x2 = y2 = 0`). The page is carried here and nowhere else: the tag in the text carries
  no page, and the page SHALL NOT be appended to the URL as a `#page=N` fragment, which the client's
  citation preview does not strip and which therefore breaks opening the file.

No `body.quote` SHALL be sent: the app does not have the cited passage's source text, and an empty
quote reserves blank space in the popup.

The array SHALL be emitted **once**, after the report text has been appended to the choice, as a
single streamed delta on the same choice while it is still open. Annotations SHALL NOT be emitted
through the attachment API, which assigns its own indices and would renumber them.

#### Scenario: A converted citation's two halves agree

- **WHEN** the step converts a lone citation of document 442, page 3
- **THEN** the delivered text SHALL carry `<cit data-id="X"></cit>` where the marker stood, and the
  annotations array SHALL carry exactly one entry whose `target.selector` names tag `cit` and id `X`

#### Scenario: The pill and its popup entry are labelled from the marker

- **WHEN** the step converts a citation of document 12, page 13
- **THEN** the annotation's `body.title` and its `body.source.attachment.title` SHALL both read
  `doc 12, page 13`, and no part of the shared URL SHALL appear in either

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

Dataset citations SHALL NOT appear: they are outside this capability, and a demo that showed one
would invite the reader to judge behaviour that is not yet designed.

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
capability's level semantics give it. **No configured file-sharing tool is not a failure**: an
instance that names none has switched inline citations off, so this is a routine expected outcome of
every turn it serves and SHALL be recorded at DEBUG rather than warning on each report. The other
five SHALL each be a WARNING — an id missing from an otherwise valid response included, since it
costs the reader a pill the report was written to offer.

**Every record the citation step emits carries counts and the failure kind, and nothing drawn from
a document.** The service's own call sites SHALL NOT log, at any level: a returned URL, any part of
one, a file name taken from one, a document title, or a cited document's id. The mapping is a tool
response body, which the content allowlist keeps out of log records, and the allowlist's permission
for DIAL relative `files/...` paths covers URLs the service handles itself elsewhere — a failed
image download it reports — and does not reach into this response. What a record may carry about
documents is therefore how many: how many were cited, how many resolved, how many ids the response
omitted. The one name a record may carry is the configured tool's, which the allowlist allows as a
tool name and which is what makes a misconfiguration warning actionable.

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
- **THEN** no file-sharing call SHALL be made, no annotations SHALL be emitted, and the delivered
  text SHALL carry no marker tag — differing from the settled draft only where the link pass
  removed something
