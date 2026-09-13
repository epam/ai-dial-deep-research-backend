# source-attribution Specification

## Purpose

What a retrieval MCP server must report about where a fact came from, how the research agent turns
that report into the inline citation form the delivered report carries, and how the identifier in a
citation resolves back against the server that issued it. This capability owns the assumptions the
whole citation chain rests on and that no other capability could state: **report-citations** owns
what happens to a citation once it stands in the text, **research-execution** owns the report's
inline format, and neither owns what a server must say in the first place.

## Requirements

### Requirement: The attribution contract is semantic where a model reads it and syntactic where code reads it

The citation chain crosses four boundaries. A retrieval server reports where a fact came from; the
research agent reads that report and writes a citation marker; the app parses the markers out of the
delivered report; the app asks the server to resolve the identifier a marker carried.

At a boundary a **model** reads, the contract SHALL be semantic: it SHALL state what the attribution
has to convey and SHALL NOT fix the characters it is written in. A server MAY report attribution in
prose, as a bracketed label, or as named fields of a structured result. Fixing one spelling would
bind every server to one implementation's formatting, could not be enforced by anything the app
runs, and would buy a model nothing it does not already get from the semantic requirements below.

At a boundary **code** reads, the contract SHALL be syntactic and exact. The report's inline citation
form, and the argument and answer shapes of the resolution surfaces, are parsed and constructed by
code, so each is specified to the character by the capability that owns it — **research-execution**
for the inline form, **report-citations** for the resolution surfaces.

Each requirement in this capability SHALL say which of the two kinds it is, so a later reader can
tell a requirement that is unenforceable by design from one a test is expected to cover.

#### Scenario: A server changes how it spells its attribution

- **WHEN** a retrieval server changes the wording or punctuation of the attribution it reports, while
  still conveying the same document identifier and the same page
- **THEN** no change to this application SHALL be required, and its reports SHALL keep carrying
  correct citations

#### Scenario: A server changes the shape of a resolution answer

- **WHEN** a server changes the object its file-sharing tool returns, or the object its
  document-metadata resource answers with
- **THEN** that SHALL be a contract violation rather than a tolerated variation, because code and not
  a model reads that answer

### Requirement: Attribution is self-describing

Semantic requirement, and the one part of the semantic contract checkable by reading a server's
output rather than by running an evaluation.

A retrieval server's attribution SHALL be readable without out-of-band knowledge. Each part of it —
the identifier, and the page for a document server — SHALL be labelled, or otherwise unambiguous on
its own, so that a reader holding only the tool's output can tell which part is which.

A bare positional form SHALL NOT satisfy this. In `[(207, 1)]` the order alone decides whether `207`
is the document or the page, and that order can be known only from somewhere other than the output.
A labelled inline form such as `[Document 207, Page 1]`, and a structured result whose fields are
named `document_id` and `page_number`, both satisfy it with no further declaration.

This requirement is the one that matters most, because an ambiguous attribution does not degrade a
report visibly — it mis-cites it silently. A prompt naming the expected order SHALL NOT be treated as
satisfying it: that moves another implementation's formatting into this application, which is what
the prompt requirement below forbids.

#### Scenario: A positional attribution form is a contract violation

- **WHEN** a configured server reports attribution as a bare tuple whose parts are told apart only by
  their order
- **THEN** that server SHALL be treated as violating this contract, and the correction SHALL be made
  in the server rather than by describing the order in this application's prompts

#### Scenario: A labelled attribution form satisfies the contract

- **WHEN** a server reports `[Document 207, Page 1]`, or returns a structured result carrying named
  `document_id` and `page_number` fields
- **THEN** the attribution SHALL satisfy this requirement, with nothing further to declare

### Requirement: A document server attributes a fact to a document id and a physical page index

Semantic requirement on what attribution must convey; the page's meaning is exact.

A document server SHALL attribute every fact it reports to both a document identifier and a page.
An attribution naming only the document SHALL NOT be convertible into a citation pill, because the
pill's purpose is to open the cited page.

The page SHALL be a **1-based index into the physical pages of the file that this same server's
file-sharing tool returns for that same document identifier**. It SHALL NOT be the page number
printed on the page, and SHALL NOT be an index into any other rendition of the document.

The reason is that the app carries the cited page into the annotation's page selector, which scrolls
the reader's PDF viewer to that page of that file (see **report-citations**). A printed page number
differs from the physical index in any publication with front matter, so a server reporting printed
numbers produces pills that open the wrong page, with nothing in the chain able to detect it.

#### Scenario: Front matter does not shift the cited page

- **WHEN** a cited publication carries eight pages of front matter ahead of the page printed as 1,
  and a cited fact appears on the page printed as 3
- **THEN** the server SHALL report page 11, that page's physical index in the file its file-sharing
  tool returns, and the pill SHALL open the viewer at that page

#### Scenario: A document attribution names both halves

- **WHEN** a document server reports the source of a fact without naming a page
- **THEN** that fact's citation SHALL NOT be convertible into a pill, and it SHALL keep its marker
  text in the delivered report

### Requirement: A dataset server attributes a fact to at least a dataset

Semantic requirement.

A dataset server SHALL attribute every fact it reports to at least the dataset the fact was drawn
from, identified as that server reports it. Attribution to an individual series within a dataset is
**deferred**: a server MAY report it, and the app ignores it today.

A dataset citation is not converted into a pill by this application as it stands (see
**report-citations**), so this requirement bounds what the report may claim about a dataset-sourced
fact rather than what a reader can click.

#### Scenario: A dataset-sourced fact names its dataset

- **WHEN** a dataset server reports a fact drawn from a dataset
- **THEN** the attribution SHALL carry that dataset's identifier, and the report SHALL cite the fact
  with that identifier rather than with a document-and-page citation

### Requirement: Finer attribution detail is ignored rather than refused

Semantic requirement.

A server MAY report more than this contract requires — a quotation of the cited passage, a figure or
table index, a chunk identifier, a bounding box. The app SHALL ignore what it does not use, and a
server SHALL NOT be considered in violation for sending it.

"Ignored" rather than "SHALL NOT be sent" is deliberate and forward-looking. The DIAL annotation
model carries a quote field that the app leaves unset today only because it holds no source text
(see **report-citations**), so a server already reporting the cited passage is sending something this
application may later use rather than noise to be designed out.

#### Scenario: Extra detail changes nothing about the citation

- **WHEN** a server reports a quotation and a figure index alongside the document identifier and the
  page
- **THEN** the citation SHALL be converted exactly as it would be without them, and none of the extra
  detail SHALL be carried into the annotation

### Requirement: A cited identifier resolves against its server verbatim

Syntactic requirement.

The identifier a citation marker carries SHALL be the identifier that server's resolution surfaces
accept, unchanged. Between reading an identifier out of the delivered report and sending it back to
the server, the app SHALL NOT change its case, trim it, re-encode it, renumber it, or transform it in
any other way.

A document identifier is a positive integer, and it is the same integer for every surface of one
server: the attribution that reported it, the file-sharing tool, and the document-metadata resource.
A dataset identifier is an opaque string that may carry punctuation, such as the colon in
`IMF:WEO`.

A citation marker names no server, so nothing in the report says which server an identifier belongs
to. What decides it is the configuration rule that at most one server of each supported type may be
configured (see **application-config-schema**); without that rule, two servers each numbering their
own documents would make an identifier ambiguous and a pill could open the wrong document.

#### Scenario: A document identifier is sent back as written

- **WHEN** the delivered report cites `[doc 207, page 12]`
- **THEN** the app SHALL ask the server about document `207`, the integer the marker carried

#### Scenario: A dataset identifier survives the round trip

- **WHEN** a dataset identifier carries punctuation, such as `IMF:WEO`
- **THEN** whatever the app later sends back to that server SHALL carry the identifier exactly as the
  marker wrote it, with its punctuation and its case intact

### Requirement: The report writer translates attribution into the report's citation form

Semantic requirement, and the only one in this capability that constrains this application rather
than a server.

The report writer reads the accumulated tool messages and writes the report's fixed inline citation
form, which **research-execution** owns. Its instructions SHALL describe what a tool's attribution
conveys — which part names the document or dataset, and which part names the page — and SHALL offer
concrete spellings only as examples, presented as examples among others.

The instructions SHALL NOT present one server's spelling as the form the tools use. Doing so makes
that server's formatting load-bearing for this application: a change to it breaks no test, fails no
validation and logs no warning, and the reports quietly start losing citations. A server whose exact
attribution shape the writer has never been shown must still be translated correctly, which is what
the self-describing requirement above makes possible.

#### Scenario: The instructions name no single form as the form

- **WHEN** the report writer's citation instructions are read
- **THEN** any concrete attribution spelling they carry SHALL be introduced as one example among
  others, and no sentence SHALL state that the tools report attribution in one particular form

#### Scenario: A server's new attribution spelling needs no prompt change

- **WHEN** a configured server begins reporting attribution in a spelling these instructions never
  named, which still satisfies the self-describing requirement
- **THEN** the writer SHALL keep producing correct citation markers, and no prompt edit SHALL be
  required

### Requirement: A violated attribution contract costs a citation, never the turn

Whatever a server reports, the turn SHALL complete and the report SHALL be delivered. A violation of
any requirement in this capability SHALL cost at most the affected citations: an attribution the
agent could not read yields a fact cited in a form the parser does not accept, and such a marker is
delivered as the writer wrote it rather than becoming a pill.

No requirement here SHALL be enforced by failing a turn, rejecting a tool result, or refusing to
deliver a report. This is the same failure direction **report-citations** states for the citation
step, applied to the layers above it.

#### Scenario: Unreadable attribution still delivers the report

- **WHEN** a configured server reports attribution in a form the agent cannot resolve into a document
  identifier and a page
- **THEN** the turn SHALL complete, the report SHALL be delivered, and the affected facts SHALL carry
  whatever the writer wrote rather than a pill
