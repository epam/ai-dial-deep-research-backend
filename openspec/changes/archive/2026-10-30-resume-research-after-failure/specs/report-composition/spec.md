## MODIFIED Requirements

### Requirement: A report cites only the retrieved sources, and carries no hyperlinks

The report SHALL reference a source in exactly one way: the inline citation forms the
**research-execution** capability defines. It SHALL contain no hyperlink of any kind — no Markdown
link (`[text](url)`), no Markdown image (`![alt](url)`), no autolink (`<https://…>`), no
reference-style link (`[text][ref]` together with its `[ref]: url` definition), no raw HTML anchor
or image tag, and no bare URL. A hyperlink is a citation of something the research did not retrieve,
which is what this rule exists to prevent; a report that needs to name a source names it in words
and cites it inline.

This list is the rule's own enumeration and the one place it is written out: every other capability
that acts on it — the delivery step in **report-citations**, the citation forms in
**research-execution** — refers here rather than repeating the forms, so a form added to the rule is
added once.

This rule is enforced in three layers, and they carry **different** responsibilities — that split is
the point, not an accident (see the app-checked-rules requirement below):

1. **The report writer is told.** Its instructions state that only the inline citation forms may
   reference a source, and that links, images, autolinks and bare URLs are never written.
2. **The review loop is where a link is properly fixed, and it owes the reader good prose.** Every
   reviewed draft SHALL be checked for hyperlinks and each occurrence reported as a violation, which
   joins the review model's own list and is visible in the review's DIAL stage like any other. The
   violation SHALL ask for the sentence to be **rewritten** so that it no longer refers the reader
   to anything outside the retrieved sources — not merely for the URL to be deleted. A rewrite is
   the only repair that can keep the sentence reading well, and the report writer, which acts on the
   violation, is the only participant that can produce one.
3. **The delivery step is the guarantee, and owes only that.** It SHALL leave no hyperlink and no
   external URL in the delivered text, even in a draft the review never got to revise (see the
   **report-citations** capability, which owns that step). It SHALL NOT try to make the result read
   well: a draft reaching delivery with a URL has already had its revision chance, so the guarantee
   that nothing points the reader outward matters more than the wording left behind.

Removing the link markup is not by itself enough at either layer: a URL left as text still tells the
reader where else to look, and a Markdown renderer turns a bare URL into a link of its own.

How each form is repaired:

- A **Markdown link** SHALL keep its label and lose its URL: `see the [latest
  outlook](https://example.org/outlook)` becomes `see the latest outlook`. The sentence survives and
  nothing points outward.
- A **Markdown image** SHALL be dropped whole, alt text included, so no client fetches a remote
  resource on the reader's behalf.
- A **reference-style link** SHALL keep its label and lose both bracket pairs, and its `[ref]: url`
  definition line SHALL be deleted whole. A bracketed token is a reference-style link only when a
  matching definition exists, so an inline citation marker is never treated as one — the citation
  forms are not hyperlinks, as the last scenario of this requirement states.
- A **raw HTML anchor** (`<a href="…">text</a>`) SHALL keep its text and lose its tags, and a raw
  HTML image tag SHALL be dropped whole, each for the same reason as its Markdown counterpart.
- An **autolink or a bare URL** has no label to keep — the URL is the text — so the delivery step
  SHALL delete it. That can leave a sentence ending mid-thought (`published at`), and that cost is
  accepted deliberately: the layer that owes readable prose is the review loop, which had its chance
  to demand a rewrite, and a mechanical pass cannot reword a sentence. Neither rendering the URL as
  inline code nor replacing it with a placeholder is used: both keep telling the reader where else
  to look, which is the thing the rule forbids.

**What the app deliberately does not do with a link the report should not have carried.** The repair
is mechanical and stops at removal:

- It SHALL NOT interpret the link. No attempt is made to work out which source it meant, to match
  its target against the retrieved documents, or to turn it into a citation.
- It SHALL NOT preserve the URL anywhere the user reads — not in the delivered text, not as a
  footnote, and not in the references section. The research record keeps each draft as the writer
  wrote it, links included, for observability (**research-resume**): the removal applies to what is
  delivered, not to the writer's output.
- It SHALL NOT rewrite the prose around the removal. The wording stays as the writer wrote it and
  may read worse for the loss; only the link's own characters go. Rewriting is the review loop's
  business, one layer earlier.
- It SHALL NOT distinguish one URL from another. Internal or external, reachable or broken, every
  link is repaired the same way.
- It SHALL NOT announce the removal in the report. A reader sees ordinary prose; the violation is
  what the review stage and the logs carry.
- It SHALL NOT fail the turn or withhold the report over a link.

#### Scenario: A reviewed draft carrying a link is rewritten, not just stripped

- **WHEN** a reviewed draft contains `see the [latest outlook](https://example.org/outlook)`
- **THEN** the app SHALL report a violation naming that link, it SHALL join the review model's
  violations as one list, and the revision SHALL be asked to rewrite the sentence so it refers to no
  source outside the retrieved ones — so the delivered sentence reads correctly rather than merely
  losing its URL

#### Scenario: A link that survives to delivery is removed from the text

- **WHEN** the version budget is exhausted and the delivered draft still contains
  `see the [latest outlook](https://example.org/outlook)`
- **THEN** the delivered text SHALL read `see the latest outlook`, with the link removed and its
  label kept, and the turn SHALL complete successfully

#### Scenario: An image is dropped rather than delivered

- **WHEN** a delivered draft contains `![chart](https://example.org/chart.png)`
- **THEN** that image SHALL NOT appear in the delivered text, so no client fetches a remote
  resource on the reader's behalf

#### Scenario: A bare URL is a violation, and does not reach the reader either

- **WHEN** a reviewed draft contains `published at https://example.org/outlook`
- **THEN** the app SHALL report a violation asking for the sentence to be rewritten, and a revision
  SHALL be written while the budget allows; if it survives to delivery the URL SHALL be deleted, even
  though that leaves the sentence ending in `published at`

#### Scenario: The inline citation forms are not hyperlinks

- **WHEN** a draft cites `[doc 442, page 3]` and `[dataset ABC:DEF]`
- **THEN** neither SHALL be reported as a hyperlink violation, and neither SHALL be altered by the
  hyperlink removal
