"""The source-selection rules: which values research looks for, and how the report presents them.

Each rule is one `QualityRule`, whose four parts are what the research agent, research review, the
report writer and report review are told for it. The parts are written against what each step can
do: the research agent only calls tools, so its parts ask for retrievals and never for a note or a
summary; research review's gaps become the research agent's next plan, so they name retrievals too;
report review sees the draft and not the sources, so its checks judge only what the draft shows.

The rules name no client, dataset, publication or tool. What a channel's sources contain goes into
that channel's client rules.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

_TERMS = """\
These definitions say what the rules below mean. They are not a rule or a check of their own.

- **Fact**: what the question asks for, as a figure or a finding stated in words, with its
  indicator, scope, geography, period and scenario, such as "the unemployment rate, euro area,
  2024".
- **Value**: a figure or a finding that a source gives for a fact.
- **Exact match**: a value that agrees with the fact on all of these.
- **Near match**: a value that differs from the fact in one of them. For "the unemployment rate in
  the euro area", the rate in Germany has a narrower geography, and the youth unemployment rate in
  the euro area a narrower scope.
- **Stated date**: when the source stated the value. For a publication it is the publication date
  in the document's metadata; an edition name, such as a volume or issue number, is not a stated
  date. For a dataset value it is the dataset's last update.
- **Described period**: the period the value is about. A GDP forecast for 2027 made in 2025 has the
  stated date 2025 and the described period 2027.
- **Previous value**: the value for the previous period (year, quarter or month), or the value from
  the previous edition.
- **Methodology**: the details a source gives on how a figure or an analysis was obtained, such as
  its geography, time range, sectors and other splits, sample size, adjustments and definitions.
- **Supersede**: a newer value may supersede an older one for the same fact only when the two were
  obtained with a methodology that is obviously identical, or very likely so. Editions of one
  publication series usually share a methodology, but the series alone decides nothing. When the
  methodology differs or is unclear, such as a changed sample, model or coverage, neither value
  supersedes the other, and the report gives both. A dataset value is never superseded, because a
  dataset is an independent source.
- **Obviously outdated**: a value that meets all four conditions: a newer retrieved value for the
  same fact supersedes it; it is neither the latest nor the previous edition; the question does not
  ask how the value evolved; and it does not contribute meaningfully to answering the question.
  Never judge it from your own knowledge."""

# Only the two research steps search, and only they are told how a failed tool call is handled, so
# only they get this term.
_REASONABLE_ATTEMPT = """
- **Reasonable attempt**: at least two searches for the evidence that differ in wording or in
  scope, such as a metadata filter, neither of which found it. Evidence that only a failed tool
  could give counts as missing once that tool has failed for it and may not be called again for
  it."""

_PREVIOUS_VALUE_CONTEXT = """\
A previous value is added only where it gives context and makes sense. It does for a forecast,
whose previous edition shows how the view moved. A value for the previous period does not for a
one-off event, which has no previous period; a previous edition of an estimate of such an event,
recalculated as information arrived, is an earlier value for the same fact, which the rules on the
latest value and on other sources cover."""

SOURCE_SELECTION_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Terms",
        research_agent=_TERMS + _REASONABLE_ATTEMPT,
        research_review=_TERMS + _REASONABLE_ATTEMPT,
        report_writer=_TERMS,
        report_review=_TERMS,
    ),
    QualityRule(
        name="Missing evidence",
        research_agent="""\
Evidence these rules ask for, including a methodology or a date, may not exist. Make a reasonable
attempt to find it, then move on without it.""",
        research_review="""\
Evidence these rules ask for, including a methodology or a date, may not exist. Keep a gap for it
open until the findings show a reasonable attempt to find it. After that the evidence is missing,
and missing evidence is not a gap: do not plan another search for it.""",
        report_writer="""\
Evidence these rules ask for, including a methodology or a date, may not exist. Where the findings
show it was not found, say what is missing and what therefore cannot be concluded, as you do for
evidence that could not be retrieved.""",
        report_review="""\
A check below that asks for some evidence, such as a stated date or the reason for a difference, is
satisfied by a statement that the sources do not give it. Do not report such a statement as a
violation.""",
    ),
    QualityRule(
        name="The latest value",
        research_agent="""\
For every fact, look for its latest value in each kind of source this channel has, as stated above.
Where it has both publications and datasets, a dataset value does not make the search of the
publications unnecessary.

- A dataset's entry in the data sources was fetched at the start of this turn and is its latest
  release, so a dataset value needs no check for a later release.
- A search's first results are not necessarily a publication's latest edition. Check for a later
  edition, for example with a search scoped to recent publication dates, or with the document
  listing. This matters most for forecasts, for estimates of past events that are recalculated as
  information arrives, such as the turnout of a past election, estimated before the final count,
  and for figures revised later.
- A later value for the same fact can come from another publication type or series than the one
  first found, such as an interim update that revises a forecast an annual report gave. Scope the
  check for a later value by publication date, not by the type or series of the first result.
- A listing shows titles and dates, not the values a document gives. For a later document whose
  title or topic could cover the fact, search or read it: its title alone does not show that it
  lacks the value.
- The latest edition may not give the value. Then check the edition before it, and so on, until an
  edition gives it: the latest value is the one from the most recent edition that states it.""",
        research_review="""\
Where the channel has publications, every fact the question asks about needs a search of them for
its latest value, even when a dataset gives its value: a fact with no such search in the findings
is a gap. A value taken from a publication, with no check in the findings for a later edition, is
also a gap. A dataset value needs no check for a later release: the data sources show the
dataset's latest release.

A check for a later value covers only what it searched. It leaves a gap when it was confined to
the publication type or series of the value found, or when it is only a listing: a later listed
document whose title or topic could cover the fact, and that was never searched or read, is a
gap. When the latest edition read does not give the value, the editions before it that were never
searched or read are a gap, until one gives the value.""",
        report_writer="""\
For every fact, lead with its most recent exact match.""",
    ),
    QualityRule(
        name="Previous values",
        research_agent=f"""\
Retrieve every value the question asks for, including every edition when the question asks how
the value evolved. Also retrieve the previous value where it gives context.

For a forecast taken from a publication, read the previous edition too: find it in the document
listing and read its forecast for the same fact. A later edition's quote of the previous value,
such as "down from 1.5%", does not replace that read, because the quote does not carry the previous
value's stated date.

{_PREVIOUS_VALUE_CONTEXT}""",
        research_review="""\
A value the question asks for that is not in the findings is a gap.

For a forecast taken from a publication, the previous edition's forecast for the same fact is a gap
too, until the findings show that edition read. A later edition's quote of the previous value, such
as "down from 1.5%", does not close the gap, because the quote does not carry its stated date. A
dataset forecast's previous release is a gap only where a client-specific rule says the datasets
keep earlier releases. No other previous value is a gap.""",
        report_writer=f"""\
Give every value the question asks for, and a previous value where it gives context. For a question
about the current forecast, the latest forecast is required and the previous edition is added
context. For a question about how a forecast evolved, every edition is required.

{_PREVIOUS_VALUE_CONTEXT}""",
    ),
    QualityRule(
        name="The dataset value",
        research_agent="""\
When a dataset holds the indicator of a fact, query it, even when a publication gives a value.""",
        research_review="""\
An indicator of a fact the question asks about, held by a dataset that was never queried for it,
is a gap.""",
        report_writer="""\
Cite the data query that returned a dataset value, even when a newer publication gives a different
value: a dataset is an independent source, and its value is never superseded. When a publication
gives the same figure as the dataset, the dataset is primary, and a publication that only repeats
it may be left out.""",
    ),
    QualityRule(
        name="Methodology",
        research_agent="""\
For every value the report may use, retrieve the methodology that affects how it is read, wherever
the sources document one: methodology pages, boxes, footnotes, and notes under tables and charts.
Without it, a superseded forecast cannot be told from a disagreement.""",
        research_review="""\
For a value of a fact the question asks about, a methodology that the findings show is documented,
because a page that was read or a search result points to it, and that was not read, is a gap.""",
        report_writer="""\
Give a value's methodology with the value where it materially affects how the value is read.""",
    ),
    QualityRule(
        name="Other sources and disagreements",
        research_agent="""\
Look for other sources that give a value for the same fact, and for what explains any difference
between them.""",
        research_review="""\
This rule's only gap is a difference already found in the findings whose explanation was not looked
for. Never plan a search for further sources that might disagree: such a search has no natural end.
This limit applies to this rule alone: the gaps the other rules define still stand.""",
        report_writer="""\
Give every differing value for a fact, name its source in the text and cite it, and say why the
values differ or that the sources do not explain it. "The forecast was updated between the two
dates" is a valid reason, and so is a methodology change between two editions, which leaves neither
value superseded. Never average or merge values. Leave a value out only when it is obviously
outdated or irrelevant: omitting a relevant value costs more than including one.""",
        report_review="""\
Judge only what the draft shows. Report a violation for:

- a range or an average spanning two sources' values for the same fact;
- two values for the same fact that the draft presents as differing, unless each carries its own
  citation and a reason for the difference, or the statement that the sources do not explain it.

A figure computed from values of different facts, such as the difference between two indicators'
growth rates, merges no values for one fact, and this check does not cover it. Whether a figure
carrying two citations hides a disagreement is not yours to judge: you cannot see the sources.""",
    ),
    QualityRule(
        name="Dates",
        research_agent="""\
Make sure the findings carry the stated date and the described period of every value you may use.

- A dataset value's stated date is the dataset's last update, which the data sources or the
  data-query result give.
- A publication's stated date is the publication date in the document metadata a tool returns.
  Never take it from the page text, which can carry a stale template date, and never from an
  edition name.
- The document listing returns documents with their metadata, but it may return one page of
  results at a time, and it may not look a document up by id. When you use a publication, list the
  documents once per research, narrowed by a publication-date filter where the plan allows rather
  than by publication type, which would hide a later value of another type, with a limit that
  covers every matching document or by paging through them, and read the date of each document
  you use from that list. List again, without the filter or with the next page, only for a
  document the list does not include.
- One listing entry settles a document's stated date: when the entry carries no date, the date is
  missing.""",
        research_review="""\
A value for a fact the question asks about, given in the findings without its stated date or its
described period, is a gap. A listing entry for a document settles that document's stated date,
whether it carries a date or not. A publication's stated date is its publication date: never ask
for a separate forecast vintage, data cut-off or as-of date.""",
        report_writer="""\
State every value's described period. State its stated date where it makes a difference: for a
forecast, for an estimate, and for a value shown beside a value for the same fact stated on another
date. Write the stated date as a date, such as a month and year, never as an edition name alone.
For example, a dataset last updated in 2025 and a publication from 2026 may both give a forecast
for 2027: cite both, each with its stated date.

Take a publication's stated date from the document metadata in the findings, such as its entry in
a document listing. Never take it from a date printed on the publication's pages: that date can
differ from the publication date.""",
        report_review="""\
Report a violation for a value without its described period, and for a forecast or an estimate
without its stated date. This includes a previous forecast that the draft gives only as the
starting point of a revision, such as "revised down from 1.5%". An edition name alone is not a
stated date. A table's year column or row label states the described period of every value in
it; do not ask to mark such values as historical or actual.""",
    ),
    QualityRule(
        name="No exact match",
        research_agent="""\
When no exact match exists for a fact, look for its nearest matches by scope, geography and
period: for a country, the smallest region or grouping that contains it; for a year, the nearest
years. Search for them in the same sources as for the exact match.""",
        research_review="""\
A fact the question asks about with no exact match in the findings, and no search for its nearest
matches by scope, geography or period, is a gap. The nearest matches are few, such as the smallest
region that contains a country or the nearest years, so ask only for those.""",
        report_writer="""\
When no exact match was found for a fact, present the near matches found, label each with how it
differs from what was asked, and state the limitation.""",
        report_review="""\
Report a violation for a near match presented without how it differs from what the question
asks.""",
    ),
)
