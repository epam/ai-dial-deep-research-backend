## ADDED Requirements

### Requirement: The app reports every emoji in a draft

The report SHALL carry no emoji (see **language-and-style**). The app SHALL check every draft for
emojis itself, as one of the rules it checks in Python, and SHALL add a violation that quotes each
emoji found, once, and asks for each to be removed, and for a word to be written where an emoji
stood for one, such as "yes" for a check mark. The writer SHALL be told the rule with the other
app-checked rules: no emoji in prose, headings, lists or tables, and that pictographic arrows and
symbols such as ↗, ⬆, ✔ and ⚠ count as emojis, since the definition below covers them.

An emoji is:

- a character with the Unicode property `Extended_Pictographic`, other than ©, ® and ™, which carry
  the property but can appear in a quoted name, together with the variation selectors, skin-tone
  modifiers and tag characters that follow it, and any zero-width-joined pictograph that follows,
  so that the violation quotes the emoji as it was written;
- a skin-tone modifier on its own;
- a flag: a pair of regional-indicator letters;
- a keycap: a digit, `#` or `*`, an optional variation selector, and the combining keycap.

Flags and keycaps are built from characters without the property, so they are named separately.
The check cannot tell a quotation from the report's own prose, so it reports an emoji wherever it
stands. The blind review SHALL be told, in its list of what it does not judge, that the app checks
emojis.

#### Scenario: An emoji is caught by the app

- **WHEN** a draft's Key Findings starts a bullet with "✅"
- **THEN** the app SHALL add a violation quoting "✅", whatever the reviews returned

#### Scenario: A flag and a keycap are emojis

- **WHEN** a draft writes "🇺🇸 United States" and "1️⃣ First"
- **THEN** the app SHALL report both

#### Scenario: A trademark sign is not an emoji

- **WHEN** a draft quotes a product name carrying "™" or "®"
- **THEN** the app SHALL NOT report it

#### Scenario: A skin-toned emoji is quoted whole

- **WHEN** a draft writes "👍🏽"
- **THEN** the app SHALL quote "👍🏽" in one violation item, modifier included

#### Scenario: A pictographic arrow is an emoji

- **WHEN** a draft's table marks a trend with "↗"
- **THEN** the app SHALL report it

#### Scenario: A draft without emojis passes

- **WHEN** a draft carries no emoji
- **THEN** the emoji check SHALL add no violation

## MODIFIED Requirements

### Requirement: The rules the app can check itself are checked in Python, not by a model

Some report rules are decidable from the draft text alone, or from the draft and what the app
itself captured during the turn. Those SHALL be owned by the app: the **section structure** (every
section the writer writes present, named exactly as configured, in the configured order, as a `##`
heading, and no other `##` heading), the **word ceiling**, the **absence of hyperlinks** (see the
requirement above), the **absence of emojis** (see "The app reports every emoji in a draft"), the
**data-query citations**, and the **dataset and document identifiers** (below). They SHALL be
checked in Python on
every reviewed draft, and their violations SHALL join the review model's violations as one list,
so a revision acts on all of them together.

**The data-query citation check.** Every distinct query id the draft cites as `[data_query <id>]`
SHALL be looked up, verbatim, among the data-query records the turn captured (**report-citations**
owns what is captured). The check reports one violation per offending id, and says what to do
rather than only what is wrong, because a bare "remove this citation" would cost a report the
citation of a fact it needs:

- **An id the turn never captured** is a mistyped or invented id. The violation SHALL name the id,
  say that no tool reported a query with it, and ask for it to be corrected to the id exactly as
  the tool reported it for the query the fact came from.
- **A captured id of a query that did not return data** — a query whose structured result carries
  no `seriesCount` greater than zero, which covers a candidate query, a query that did not run, and
  one that ran and returned nothing — SHALL name the id and say that only a data query that
  returned data may be cited. It SHALL then say what to do instead: where the statement is about
  the dataset itself — its last update, its structure, what it covers or does not cover — cite the
  dataset as `[dataset <urn>]` instead; otherwise drop the citation, or drop the statement when
  nothing else in the report supports it. A query that returned no data backs no value, so the only
  fact such a citation can stand for is a fact about the dataset.

A cited id of a query that returned data raises nothing, **whether or not the query has an
explorer link**. A query that returned data is usable evidence, and the writer cannot see the link
in any case; a missing link costs the citation its pill at delivery and nothing else
(**report-citations** defines both terms). The check SHALL NOT judge whether a fact is supported by
the query it cites: that needs the tool results, and this rule reads only ids.

**The dataset and document identifier checks.** Every distinct URN the draft cites as
`[dataset <urn>]`, and every distinct document id it cites as `[doc <id>, page <ix>]`, SHALL be
checked against what its server knows, through the lookups **report-citations** shares with the
delivery:

- **A URN the dataset catalogue does not carry** SHALL raise one violation naming the URN, saying
  that no dataset with that identifier exists, and asking for the URN exactly as the dataset tool
  reported it — whole, with its punctuation and version.
- **A document id the document-metadata resource does not know** SHALL raise one violation naming
  the id, saying that no document with that id exists, and asking for the id exactly as the search
  tool reported it for the document the fact came from.

**Valid means available on the server, not seen in a tool response.** A URN is valid when it is
in the list of datasets the dataset server makes available, and a document id is valid when it is
among the documents the document server makes available. The check SHALL NOT ask whether the id
appeared in an earlier tool response of this turn. That would need the app to read attribution out
of tool results, and the citation contract deliberately does not require a server to report
attribution in any predefined format (**source-attribution**): the research agent reads each tool's
response, whatever its form, and writes the report's citations in this application's own format,
which the app then parses to build the annotations. The only surfaces the app reads by contract are
the servers' resolution surfaces, so those are what an id is checked against. An id that exists on
the server but that the research never retrieved therefore passes this check. A query id is checked
against tool results only because the data-query server resolves query ids nowhere else: the
structured result and the `_meta` payload it attaches to each result are contracted surfaces with a
fixed shape, not attribution text written in whatever form a server chooses (**report-citations**).

An id whose lookup failed, and every id on a channel that configures no server of its kind, SHALL
raise nothing: a check that cannot tell whether an id is valid stays silent. The cited page is not
checked; that is deferred.

Each such rule SHALL keep three things in one place: the instruction given to the report writer,
the check over the finished draft, and the wording of the violation a revision acts on. A rule is
configured once from the instance's configuration and used at both points, so the writer can never
be told something different from what its draft is judged against.

**The structure check and the writer see the same list.** The sections the writer is told to write,
the sections the check expects, and the sections the structure rule's violation names SHALL all be
the configured structure itself, with nothing added and nothing subtracted anywhere — the
References section is no part of it, so no derivation stands between the instruction and the check.

**The review model SHALL NOT be asked to judge any of them.** It is told that the app checks the
headings, the length, the hyperlinks, the emojis and the cited query, dataset and document ids, and
its own checks are the ones that need a reader: a
padded section, a section that should admit it has nothing to say, the protected-section rules, the
prohibited annotations, valid Markdown, the citation format, a list of sources the draft
carries, and, on a turn whose glossary fetch listed at least one term or whose research agent
obtained a successful glossary tool result, the glossary terminology (see
**A report uses the glossary's terminology**). A model verdict SHALL NOT be able to pass a draft
that breaks an app-checked
rule, and a review call that fails SHALL NOT suppress one.

**A list of sources is the review model's to report, because the app cannot see every form of
one.** The structure check reads `##` headings, so it catches a references section written as one
and nothing else: the same list written under a `###` sub-heading, in bold standing in for a
heading, under a bold line standing in for a heading, or under no heading at all breaks the
writer's rule and reaches the reader unreported.

**What is forbidden is an enumeration, not a mention.** The rule given to the writer and to the
review model SHALL name a list carrying one entry per source — the bibliography an article ends
with — in whatever form it takes, and SHALL exclude the two things it is not: the inline citations,
and prose describing the evidence. A section whose description requires it to say what the research
drew on, to name the kinds of source it covered, or to characterise their coverage SHALL be correct
to do so. The Overview is exactly such a section in the default structure, so a rule worded against
*mentioning* sources would contradict the structure it is enforcing.

**Every check the review model is given SHALL be decidable from what that call receives.** It sees
the draft, the configured structure, the query and plan, the turn's data-sources string, and the
research agent's successful glossary tool results, and it deliberately sees neither the findings nor
any other tool result (**research-execution**). The glossary-terminology check is given only on a
turn whose glossary fetch listed at least one term or whose research agent obtained a successful
glossary tool result, for this reason. A check phrased against what a server
reported is therefore unanswerable, and a model asked one resolves it by guessing. The
citation-format check in particular SHALL be worded against the **shape** of a citation and SHALL
carry an example of a well-formed dataset URN and of a well-formed data-query citation, rather than
asking whether the identifier is the one the dataset tool returned — an identifier whose name reads
like ordinary words is otherwise reported as a display name, and an opaque query id is otherwise
reported as a malformed dataset citation. Whether a cited URN or query id matches a real record is
not this model's to decide: the app compares it to what the server reported character for
character (**source-attribution**) and simply draws no pill where nothing matches. For the same
reason the check SHALL NOT ask whether a fact that came from a data query is cited by its query id
rather than by its dataset: which tool a fact came from is in the tool results this call does not
see.

The review model SHALL therefore be asked to report such an enumeration wherever it appears. Its
never demanding one follows from the same check rather than from a second instruction: it is told
its job is the checks alone, so a section it asked a revision to add would break one it holds.
Reporting a `##` references section the structure check also reports is accepted — a duplicated
violation costs a revision nothing, while a missed one costs the reader.

The check is the reviewer's standing behaviour rather than anything about the draft in hand, so it
SHALL be stated in its **system prompt**. The per-turn request SHALL carry no copy of it, and SHALL
NOT need the section's configured name to render: the check does not turn on what the heading is
called, so naming it there would add a per-instance input to a call that does not use one.

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
- **THEN** its prompt SHALL state that the app checks the headings, the length, the hyperlinks and
  the emojis itself, and SHALL NOT ask it to verify any of them

#### Scenario: The expected headings are the configured structure itself

- **WHEN** the structure check runs on a draft written from a configured structure
- **THEN** the headings it expects SHALL be exactly that structure's sections, with nothing
  subtracted, and a draft carrying exactly those SHALL pass the check

#### Scenario: The review model never asks for a references section

- **WHEN** the report-review call is issued
- **THEN** its prompt SHALL state that the application appends the References section itself once
  the draft is settled and that an enumeration of the report's sources in the draft is a violation,
  whatever the research question or the approved plan asked for, so a revision it asks for SHALL
  NOT demand one

#### Scenario: The review model is told to report a references section the draft wrote

- **WHEN** the report-review call is issued
- **THEN** its prompt SHALL ask the model to report an enumeration of the report's sources wherever
  the draft carries one — under a heading, under a bold line standing in for one, or under none —
  and SHALL state that the inline citations and prose describing the evidence are not such an
  enumeration

#### Scenario: A readable dataset identifier is not reported as a display name

- **WHEN** a draft cites a dataset whose URN carries a legible name, such as
  `[dataset IMF:WEO(1.0.0)]`, and the review model cannot see what the dataset tool reported
- **THEN** the citation-format check SHALL NOT report it, the prompt having told the model to judge
  the citation's shape and shown it a well-formed URN

#### Scenario: A section naming its sources in prose is not a violation

- **WHEN** a draft's Overview names the kinds of source and the topics the research covered, as its
  configured description requires, and the draft carries no list with one entry per source
- **THEN** neither the app's own checks nor the review model's SHALL report it

#### Scenario: A data-query citation is a well-formed citation

- **WHEN** a draft cites `[data_query dq_0123abcd45]`, and the review model cannot see what the
  data-query tool reported
- **THEN** the citation-format check SHALL NOT report it, the prompt having shown the model a
  well-formed data-query citation beside the document and dataset forms

#### Scenario: A mistyped query id asks for the id to be fixed

- **WHEN** a reviewed draft cites `[data_query dq_0123abcd46]` and the turn captured no query with
  that id
- **THEN** the app SHALL report one violation naming `dq_0123abcd46`, stating that no tool reported
  a query with that id, and asking for the id the tool reported

#### Scenario: A query without data is not simply removed

- **WHEN** a reviewed draft cites a candidate query's id for a statement that a dataset carries no
  data for a country
- **THEN** the app SHALL report one violation naming the id, stating that only a query that returned
  data may be cited, and directing a statement about the dataset itself to a `[dataset <urn>]`
  citation, and any other statement to dropping the citation or the statement

#### Scenario: A query that returned data raises nothing

- **WHEN** a reviewed draft cites a query id whose captured structured element carries a
  `seriesCount` greater than zero
- **THEN** the data-query check SHALL report no violation for it

#### Scenario: A query that returned data but has no explorer link raises nothing

- **WHEN** a reviewed draft cites a query id whose structured element carries a `seriesCount` of
  `3`, and whose `_meta` element carries no data explorer URL
- **THEN** the data-query check SHALL report no violation for it, and the delivered citation SHALL
  stay as text (**report-citations**)

#### Scenario: A query that ran and returned nothing asks for a revision

- **WHEN** a reviewed draft cites a query id whose `_meta` element carries a data explorer URL and
  whose structured element carries no `seriesCount`
- **THEN** the app SHALL report one violation naming the id and stating that only a query that
  returned data may be cited

#### Scenario: An unknown dataset URN asks for the reported URN

- **WHEN** a reviewed draft cites `[dataset IMF:WEO(2.0.0)]` and the catalogue carries
  `IMF:WEO(1.0.0)` and no `IMF:WEO(2.0.0)`
- **THEN** the app SHALL report one violation naming `IMF:WEO(2.0.0)` and asking for the URN exactly
  as the dataset tool reported it

#### Scenario: An unknown document id asks for the reported id

- **WHEN** a reviewed draft cites `[doc 999, page 2]` and the document-metadata resource's answer
  omits `999`
- **THEN** the app SHALL report one violation naming document `999`, and SHALL say nothing about
  page `2`

#### Scenario: An available id that no tool response mentioned passes

- **WHEN** a reviewed draft cites `[dataset IMF:WEO(1.0.0)]`, the catalogue carries that URN, and no
  tool response of the turn mentioned it
- **THEN** the dataset check SHALL report no violation for it

#### Scenario: A failed lookup raises no identifier violation

- **WHEN** a reviewed draft cites documents and the document-metadata read fails
- **THEN** the document check SHALL report no violation for that draft

#### Scenario: The glossary check is given only with the glossary

- **WHEN** the report-review call is issued on a turn whose glossary listed terms
- **THEN** its system prompt SHALL list the glossary-terminology check among the review model's own
  checks and SHALL carry the glossary in its data-sources string, while on a turn without a
  glossary the check SHALL NOT appear

### Requirement: A review ↔ revise loop enforces the report rules before delivery

A finished draft SHALL be judged by an independent review step before it is delivered. That step's
first call, the **blind review**, SHALL read the draft, the configured report structure, the
protected sections, and the research question and plan — the last two because they are where a
user's formatting instruction lives, and without them the step cannot tell a legitimately-followed
instruction from an override of a protected rule. It SHALL judge the draft against the section
content rules, the protected sections and their rules, the prohibited meta-annotations, well-formed
Markdown, the citation format rules the **research-execution** capability defines, and the
blind-review part of every quality rule: the generic rules of every policy and the channel's client
rules (see **source-selection** and **faithful-relay**). These parts judge only
what the draft shows — how two values for one fact are presented, whether a value states its dates,
whether a near match says how it differs, whether a claim carries a citation — because the blind
review never sees the sources.

The review step SHALL make a second call beside it, the **grounded review**, which sees the
research transcript and judges the draft against the source-selection and faithful-relay rules'
writer parts, the writer's "No calculations" rule, and the grounded-review part of every other
quality rule, generic and client (see **faithful-relay**). The two calls SHALL run concurrently, and
the grounded review's items SHALL be appended to the blind review's violations, so the loop below
treats every item alike.

The section structure, the word ceiling, the absence of hyperlinks and the absence of emojis are not
the review step's to judge — the app checks those itself (see the
requirement above). The citation-format check becomes load-bearing with this change: the app parses
those markers out of the delivered report (see **report-citations**), so a draft that adopted
numbered footnotes would yield no pills at all, and this step is what pushes it back to the defined
form. It SHALL NOT be given the measured word
count or the ceiling: length needs no model — the app measures it and adds the length violation
itself (see the ceiling requirement).

The blind review's structured output SHALL be the violations alone, one entry per rule the draft
breaks and naming what to change; the grounded review answers with a numbered list of the same
kind. There SHALL be no separate approval field: an empty list SHALL
mean the draft is approved, so a remark that is not meant to block delivery cannot be expressed —
every returned violation forces a revision.

The blind review SHALL NOT receive the research findings: every criterion it judges is decidable
from the draft, the configuration, and the query and plan. Only the grounded review receives them.

**A failing review SHALL NOT cost the report.** If the blind review fails — an unparseable
structured response, a provider error, exhausted transient-drop retries — the turn SHALL NOT fail
and the failure SHALL be logged as a warning. The same holds for the grounded review: a failed
grounded review adds no item, and the blind review's violations still stand, as the grounded
review's items still stand when the blind review fails. This departs deliberately from
research-review, which is fail-loud because a broken verdict there means research of unknown
completeness; here the report already exists, and discarding a finished multi-minute run over a
formatting check is the worse outcome.

When both calls fail, the app has no verdict, so the two rules compose in one order, which SHALL
be: the measured count still applies. An over-ceiling draft whose review failed SHALL be revised on
the app-rendered length instruction alone; a draft within the ceiling SHALL be delivered as the
answer. A reviewed draft always has a rewrite in budget — the review is gated on the budget below —
so a failed review never has to reason about an exhausted budget.

**A swallowed revision failure ends the loop, overriding the count gate.** It is the third delivery
case beside "within the ceiling" and "budget exhausted": an over-ceiling draft MAY therefore ship
with
version budget still remaining, and that unresolved length SHALL be recorded in the logs exactly as
an exhausted budget is. The count gate above applies while revisions are still being written
successfully, not after one has failed.

**A failed revision SHALL NOT cost the report either.** Once a draft exists, no later failure in the
loop may discard it: if a revision's own model call fails — after its transient-drop retries, or on
a
non-retryable error such as an exceeded context length, which a revision is likelier to hit than the
first draft was because its request is strictly larger — the **previous** draft SHALL be delivered
and the failure logged as a warning. The turn SHALL NOT fail. Before this loop existed the report
was
written once and a failure had nothing to discard; adding revisions must not turn a finished report
into a failed turn.

When the review returns revision instructions, the report SHALL be rewritten against them and
judged again. The loop SHALL be bounded by a configured version budget (`max_report_versions`,
default 3, counting the first draft and every rewrite as one version each): a draft SHALL be
reviewed only while another version may still be written, so the last permitted version is
delivered as the answer without a further review. That final review is deliberately not run
because its verdict would be non-actionable — no rewrite may follow it — so the review would spend
a review's time and cost only to log problems the loop can no longer fix. An imperfect report is
delivered, the turn is never failed and the work is never discarded over a formatting verdict,
and the unreviewed delivery SHALL be announced (see the stage requirement above). A budget of one
SHALL mean the first draft is delivered with no review at all.

The review step SHALL judge the report as written. It SHALL NOT re-open evidence coverage or
request further research — that judgement belongs to research-review — and it SHALL NOT be able to
route control back to research-agent. The blind review's prompt SHALL still list, among what it does
not judge, whether a claim is true and whether the research was thorough, and SHALL NOT list whether
a source was the right one to use: how the draft presents the values of several sources is a
source-selection check it does judge. The grounded review's instructions SHALL list whether
the research was thorough among what it does not judge, and SHALL NOT list whether a claim is true
to its source, which is what it judges.

Once the loop has settled on the draft to deliver, that draft's wording is final: no later step may
rewrite, shorten, reorder, or reformat it. The one permitted exception is the citation step, which
replaces each citation marker it converts into an inline citation annotation with that citation's
marker tag and changes nothing else (see the **report-citations** capability). The review step
judges
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
- **THEN** the latest draft SHALL be delivered as the answer without a further review, the
  turn SHALL complete successfully, and the unreviewed delivery SHALL be recorded in the logs

#### Scenario: A failed blind review delivers a draft that is within the ceiling

- **WHEN** the blind review raises, or returns output that cannot be parsed into its verdict schema,
  after its transient-drop retries are exhausted, the draft is within the word ceiling, and the
  grounded review reports no item or fails too
- **THEN** the current draft SHALL be delivered as the answer, the turn SHALL complete
  successfully, and the failure SHALL be logged as a warning

#### Scenario: A failed blind review still shortens an over-long draft

- **WHEN** the blind review fails on a draft measuring 3,900 words against a ceiling of 2,750 and
  the version budget is not exhausted
- **THEN** a revision SHALL be written against the app-rendered length instruction, together with
  any item the grounded review reports, and the failure SHALL be logged as a warning

#### Scenario: A failed revision call delivers the previous draft

- **WHEN** a revision's model call fails — its transient-drop retries exhausted, or a non-retryable
  error such as an exceeded context length — after a first draft was already written
- **THEN** the previous draft SHALL be delivered as the answer, the turn SHALL complete
  successfully,
  and the failure SHALL be logged as a warning

#### Scenario: An over-long draft ships when the budget runs out

- **WHEN** the version budget is exhausted and the latest draft still measures above the ceiling
- **THEN** that draft SHALL be delivered as the answer, the turn SHALL complete successfully, and
  the
  unresolved length SHALL be recorded in the logs

#### Scenario: A forced revision carries an instruction even with nothing from the model

- **WHEN** the review step approves an over-long draft, so Python forces the revision
- **THEN** the report node SHALL receive the previous draft, its measured count, the ceiling, and a
  direction to shorten by rewriting, and SHALL NOT be invoked as if writing a first draft

#### Scenario: Version budget of one skips the review

- **WHEN** an instance configures a version budget of one
- **THEN** the first draft SHALL be delivered as the answer and no review SHALL be made

#### Scenario: Review cannot reopen research

- **WHEN** the review step judges a draft whose Detailed Analysis rests on thin evidence
- **THEN** it SHALL confine its instructions to the report text and SHALL NOT cause another
  research iteration

#### Scenario: Review reports two differing values merged into a range

- **WHEN** a draft states "global GDP is forecast to grow by 3.3% to 3.5% in 2026" and cites two
  sources, each of which gives one end of the range
- **THEN** the review step SHALL report a violation asking for each value to be stated on its own,
  with its citation, its stated date and the reason for the difference, or the statement that the
  sources do not explain it

#### Scenario: A failed blind review leaves the grounded review's items standing

- **WHEN** the blind review fails and the grounded review reports two violations
- **THEN** the draft SHALL be revised against those two violations, and the blind review's failure
  SHALL be logged as a warning

#### Scenario: The grounded review's item forces a revision the blind review would not

- **WHEN** the blind review approves a draft and the grounded review reports that a figure is
  not on the page cited for it
- **THEN** the draft SHALL be revised against that item
