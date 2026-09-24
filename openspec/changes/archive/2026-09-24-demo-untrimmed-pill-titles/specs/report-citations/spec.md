## MODIFIED Requirements

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

The permitted differences are **where the file URLs and the document titles come from**. A research
turn resolves URLs through the configured file-sharing tool and titles through the document-metadata
resource; the demo cites the PDFs the caller attached to the last message and feeds their URLs and
titles into the shared code. A demo has to be self-contained and to produce the same reply on every
environment, which a dependency on a live retrieval server and its document ids would prevent. An
attachment already lives in the caller's own storage, so the demo SHALL copy nothing anywhere: the
annotation points at the attachment's own URL, which the caller can open.

**Each document's title SHALL be the attachment's own title** — the name the chat shows for the
attached file — so the demo's labels read as a real report's do: `<title>, page <ix>`. The title
stored in the PDF's own metadata SHALL NOT be used, because it is often missing or holds a value the
authoring tool generated, while the attachment title is the name the caller already sees. An
attachment with no title, or a blank one, SHALL leave its citations labelled from the marker, as a
research turn labels a document no title resolved for. The demo SHALL NOT shorten a title on the
pill: the pill and the popup card SHALL both carry it whole, as they do in a channel that turns the
pill-title budget off, so a reader can tell from the pill alone which attached file it opens.

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

#### Scenario: The demo's labels carry the attachment titles

- **WHEN** a caller attaches two PDFs whose attachment titles are `Market Outlook 2025.pdf` and
  `World Economic Outlook.pdf`, and sends any message
- **THEN** every popup entry and every pill for those documents SHALL read the whole attachment
  title followed by the cited page, such as `Market Outlook 2025.pdf, page 2`, whatever title the
  PDFs' own metadata carries

#### Scenario: An attachment without a title is labelled from its marker

- **WHEN** one of the two attachments carries no title
- **THEN** that document's citations SHALL still become pills, labelled `doc <id>, page <ix>`, and
  the other document's citations SHALL carry its attachment title

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
