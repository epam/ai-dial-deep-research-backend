## ADDED Requirements

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
- It SHALL NOT preserve the URL anywhere — not in the delivered text, not as a footnote, not in the
  references section, and not in the persisted message.
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

## MODIFIED Requirements

### Requirement: The rules the app can check itself are checked in Python, not by a model

Some report rules are decidable from the draft text alone. Those SHALL be owned by the app: the
**section structure** (every configured section present, named exactly as configured, in the
configured order, as a `##` heading), the **word ceiling**, and the **absence of hyperlinks** (see
the requirement above). They SHALL be checked in Python on every reviewed draft, and their
violations SHALL join the review model's violations as one list, so a revision acts on all of them
together.

Each such rule SHALL keep three things in one place: the instruction given to the report writer,
the check over the finished draft, and the wording of the violation a revision acts on. A rule is
configured once from the instance's configuration and used at both points, so the writer can never
be told something different from what its draft is judged against.

**The review model SHALL NOT be asked to judge any of them.** It is told that the app checks the
headings, the length and the hyperlinks, and its own checks are the ones that need a reader: a
padded section, a section that should admit it has nothing to say, the protected-section rules, the
prohibited annotations, valid Markdown, and the citation format. A model verdict SHALL NOT be able to pass a draft that breaks an app-checked
rule, and a review call that fails SHALL NOT suppress one.

Because the structure check passes only when every heading matches the configuration exactly, the
references section is then found by the length measure by construction — a draft that renamed it,
omitted it, or wrote it at another level is reported by the structure rule rather than silently
losing its exemption. No separate signal for the exemption is therefore emitted, and the
correspondence between the two is covered by tests rather than at runtime.

#### Scenario: An approving verdict cannot pass a mis-headed draft

- **WHEN** the review model returns no violations for a draft whose `Conclusion` section is written
  as `# Conclusion`
- **THEN** the app's structure rule SHALL report it, a revision SHALL be required while the budget
  allows, and the violation SHALL name the section and the heading it must carry

#### Scenario: A failed review call still reports the app-checked rules

- **WHEN** the review call fails on a draft that is over the ceiling and missing a configured
  section
- **THEN** both violations SHALL still be reported, and the turn SHALL NOT fail

#### Scenario: The review model is not asked about headings, length or hyperlinks

- **WHEN** the report-review call is issued
- **THEN** its prompt SHALL state that the app checks the headings, the length and the hyperlinks
  itself, and SHALL NOT ask it to verify any of them

### Requirement: A review ↔ revise loop enforces the report rules before delivery

A finished draft SHALL be judged by an independent review step before it is delivered. That
step SHALL read the draft, the configured report structure, the protected sections, and the
research question and plan — the last two because they are where a user's formatting instruction
lives, and without them the step cannot tell a legitimately-followed instruction from an
override of a protected rule. It SHALL judge the draft against the section content rules, the
protected sections and their rules, the prohibited meta-annotations, well-formed Markdown, and the
citation format rules the **research-execution** capability defines. The section structure, the word
ceiling and the absence of hyperlinks are not its to judge — the app checks those itself (see the
requirement above). The citation-format check becomes load-bearing with this change: the app parses
those markers out of the delivered report (see **report-citations**), so a draft that adopted
numbered footnotes would yield no pills at all, and this step is what pushes it back to the defined
form. It SHALL NOT be given the measured word
count or the ceiling: length needs no model — the app measures it and adds the length violation
itself (see the ceiling requirement).

The review step's structured output SHALL be the violations alone, one entry per rule the draft
breaks and naming what to change. There SHALL be no separate approval field: an empty list SHALL
mean the draft is approved, so a remark that is not meant to block delivery cannot be expressed —
every returned violation forces a revision.

The step SHALL NOT receive the research findings: every criterion above is decidable from the
draft, the configuration, and the query and plan.

**A failing review SHALL NOT cost the report.** If the review call fails — an unparseable
structured response, a provider error, exhausted transient-drop retries — the turn SHALL NOT fail
and the failure SHALL be logged as a warning. This departs deliberately from research-review,
which is fail-loud because a broken verdict there means research of unknown completeness; here the
report already exists, and discarding a finished multi-minute run over a formatting check is the
worse outcome.

A failed review leaves the app with no verdict, so the two rules compose in one order, which SHALL
be: the measured count still applies. An over-ceiling draft whose review failed SHALL be revised on
the app-rendered length instruction alone; a draft within the ceiling SHALL be delivered as the
answer. A reviewed draft always has a rewrite in budget — the review is gated on the budget below —
so a failed review never has to reason about an exhausted budget.

**A swallowed revision failure ends the loop, overriding the count gate.** It is the third delivery
case beside "within the ceiling" and "budget exhausted": an over-ceiling draft MAY therefore ship with
version budget still remaining, and that unresolved length SHALL be recorded in the logs exactly as
an exhausted budget is. The count gate above applies while revisions are still being written
successfully, not after one has failed.

**A failed revision SHALL NOT cost the report either.** Once a draft exists, no later failure in the
loop may discard it: if a revision's own model call fails — after its transient-drop retries, or on a
non-retryable error such as an exceeded context length, which a revision is likelier to hit than the
first draft was because its request is strictly larger — the **previous** draft SHALL be delivered
and the failure logged as a warning. The turn SHALL NOT fail. Before this loop existed the report was
written once and a failure had nothing to discard; adding revisions must not turn a finished report
into a failed turn.

When the review returns revision instructions, the report SHALL be rewritten against them and
judged again. The loop SHALL be bounded by a configured version budget (`max_report_versions`,
default 3, counting the first draft and every rewrite as one version each): a draft SHALL be
reviewed only while another version may still be written, so the last permitted version is
delivered as the answer without a further review call. That final review is deliberately not run
because its verdict would be non-actionable — no rewrite may follow it — so the call would spend
a review's time and cost only to log problems the loop can no longer fix. An imperfect report is
delivered, the turn is never failed and the work is never discarded over a formatting verdict,
and the unreviewed delivery SHALL be announced (see the stage requirement above). A budget of one
SHALL mean the first draft is delivered with no review at all.

The review step SHALL judge the report as written. It SHALL NOT re-open evidence coverage or
request further research — that judgement belongs to research-review — and it SHALL NOT be able to
route control back to research-agent.

Once the loop has settled on the draft to deliver, that draft's wording is final: no later step may
rewrite, shorten, reorder, or reformat it. The one permitted exception is the citation step, which
replaces each citation marker it converts into an inline citation annotation with that citation's
marker tag and changes nothing else (see the **report-citations** capability). The review step judges
the draft with its markers in place, which is the form the citation rules are written against.

#### Scenario: Approved first draft is delivered as judged

- **WHEN** the review step approves the first draft
- **THEN** that draft SHALL be delivered as the answer with no revision written and no rewording,
  its only permitted difference from the judged text being the citation markers the citation step
  replaced with marker tags

#### Scenario: Rejected draft is revised and judged again

- **WHEN** the review step returns revision instructions for the first draft and the version
  budget is 3
- **THEN** a revision SHALL be written against those instructions and SHALL itself be judged by
  the review step before delivery

#### Scenario: A violation always forces a revision, with no way to leave it merely informative

- **WHEN** the review step returns one violation on a draft it would otherwise consider fine to
  ship
- **THEN** the draft SHALL still be treated as not approved and a revision SHALL be written
  against that violation, because the schema has no field to mark a violation non-actionable

#### Scenario: Exhausted budget delivers the latest draft

- **WHEN** every review demanded a rewrite and the last permitted version has been written
- **THEN** the latest draft SHALL be delivered as the answer without a further review call, the
  turn SHALL complete successfully, and the unreviewed delivery SHALL be recorded in the logs

#### Scenario: A failed review call delivers a draft that is within the ceiling

- **WHEN** the review call raises, or returns output that cannot be parsed into its verdict schema,
  after its transient-drop retries are exhausted, and the draft is within the word ceiling
- **THEN** the current draft SHALL be delivered as the answer, the turn SHALL complete
  successfully, and the failure SHALL be logged as a warning

#### Scenario: A failed review call still shortens an over-long draft

- **WHEN** the review call fails on a draft measuring 3,900 words against a ceiling of 2,750 and the
  version budget is not exhausted
- **THEN** a revision SHALL be written against the app-rendered length instruction alone, and the
  failure SHALL be logged as a warning

#### Scenario: A failed revision call delivers the previous draft

- **WHEN** a revision's model call fails — its transient-drop retries exhausted, or a non-retryable
  error such as an exceeded context length — after a first draft was already written
- **THEN** the previous draft SHALL be delivered as the answer, the turn SHALL complete successfully,
  and the failure SHALL be logged as a warning

#### Scenario: An over-long draft ships when the budget runs out

- **WHEN** the version budget is exhausted and the latest draft still measures above the ceiling
- **THEN** that draft SHALL be delivered as the answer, the turn SHALL complete successfully, and the
  unresolved length SHALL be recorded in the logs

#### Scenario: A forced revision carries an instruction even with nothing from the model

- **WHEN** the review step approves an over-long draft, so Python forces the revision
- **THEN** the report node SHALL receive the previous draft, its measured count, the ceiling, and a
  direction to shorten by rewriting, and SHALL NOT be invoked as if writing a first draft

#### Scenario: Version budget of one skips the review

- **WHEN** an instance configures a version budget of one
- **THEN** the first draft SHALL be delivered as the answer and no review call SHALL be made

#### Scenario: Review cannot reopen research

- **WHEN** the review step judges a draft whose Detailed Analysis rests on thin evidence
- **THEN** it SHALL confine its instructions to the report text and SHALL NOT cause another
  research iteration
