## ADDED Requirements

### Requirement: A report uses the glossary's terminology

On a turn whose glossary listed at least one term (see **glossary-prefetch**), the report SHALL use
the glossary's terminology: where the report refers to a concept that a glossary term names, it
SHALL use that term, spelled as the glossary spells it, rather than a synonym or a paraphrase. A
glossary term that the report has no reason to mention is not required.

The rule SHALL be given to two calls, in the same wording of what it requires:

- **The report writer.** Its system prompt SHALL carry the rule next to the other report-wide
  rules. The glossary itself reaches the writer through its data-sources string (see
  **research-execution**).
- **The report reviewer.** Its system prompt SHALL carry the check as one of the review model's own
  checks. The glossary reaches the reviewer through its data-sources string (see
  **research-execution**). A draft that names a glossary concept by another word SHALL be reported
  as a violation naming the passage and the glossary term to use.

This is a check for the review model, not for Python: whether a phrase in the draft refers to the
concept a glossary term names needs a reader, so no app-owned rule decides it.

A term whose definition is `null` SHALL still count for the rule, judged by its name.

On a turn without a glossary, and on a turn whose list-terms call failed, neither call SHALL carry
the rule. Both still receive the data-sources string, which on a failed list ends in the failure
text.

#### Scenario: The writer is told to use the glossary's terms

- **WHEN** the report writer runs on a turn whose glossary listed terms
- **THEN** its system prompt SHALL carry the glossary-terminology rule, and its data-sources string
  SHALL carry the glossary

#### Scenario: The reviewer reports a synonym

- **WHEN** the glossary lists `Primary Commodity Prices`, and a draft refers to the same concept as
  "raw material price levels"
- **THEN** the review model SHALL report a violation that names the passage and the glossary term

#### Scenario: A failed list gives neither call the rule

- **WHEN** the list-terms call failed three times
- **THEN** neither the report writer's nor the report reviewer's prompt SHALL carry the
  glossary-terminology rule

## MODIFIED Requirements

### Requirement: The rules the app can check itself are checked in Python, not by a model

Some report rules are decidable from the draft text alone, or from the draft and what the app
itself captured during the turn. Those SHALL be owned by the app: the **section structure** (every
section the writer writes present, named exactly as configured, in the configured order, as a `##`
heading, and no other `##` heading), the **word ceiling**, the **absence of hyperlinks** (see the
requirement above), the **data-query citations**, and the **dataset and document identifiers**
(below). They SHALL be checked in Python on
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
headings, the length, the hyperlinks and the cited query, dataset and document ids, and its own checks are the ones that need a reader: a
padded section, a section that should admit it has nothing to say, the protected-section rules, the
prohibited annotations, valid Markdown, the citation format, a list of sources the draft
carries, and, on a turn whose glossary listed at least one term, the glossary terminology (see
**A report uses the glossary's terminology**). A model verdict SHALL NOT be able to pass a draft that breaks an app-checked
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
the draft, the configured structure, the query and plan, and the turn's data-sources string, and
it deliberately sees neither the findings nor any tool result (**research-execution**). The
glossary-terminology check is given only on a turn whose glossary listed at least one term, for
this reason. A check phrased against what a server
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
- **THEN** its prompt SHALL state that the app checks the headings, the length and the hyperlinks
  itself, and SHALL NOT ask it to verify any of them

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
