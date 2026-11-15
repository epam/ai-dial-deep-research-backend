"""The faithful-relay rules: the report relays what the sources say, and nothing else.

It invents, infers and computes nothing, keeps every figure as its source gives it, and states no
finding more firmly or more broadly than its source does. Each rule is one `QualityRule`, written
against what each step can do, as the source-selection rules are: the research agent only calls
tools, research review's gaps become the research agent's next plan, and the blind review sees the
draft and not the sources, so its checks judge only what the draft shows. Whether a cited claim is
faithful to its source is judged by the grounded review, which sees the research transcript and
judges the draft against the writer parts, so no rule here sets a grounded part.

The rules name no client, dataset, publication or tool.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

# The policy's terms, which open its block in every step. They are not a rule. The source-selection
# block renders before this one and defines "value" and "stated date", which these definitions use.
FAITHFUL_RELAY_TERMS = """\
These definitions say what the rules below mean. They are not a rule or a check of their own. The
source-selection terms above, such as value, stated date and described period, apply here too.

- **Source**: the result of a research tool call, or the data sources every prompt carries: the
  knowledge base's descriptions, and the list of datasets and their structures. The
  answer of a search tool that summarises pages, such as `rag_search`, is **not** a source: it is
  written by a model that follows none of these rules, and it can state a sum or a characterisation
  the pages do not. It only points at where the evidence lives. A page read as text or as an image,
  and a chunk a retrieval tool returns word for word, such as `retrieve_text_chunks`, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say, and
  adds nothing to them, such as "both sources expect growth to slow in 2026".
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic that produces a number no source gives: a growth rate derived from two
  levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as large",
  a share, a sum or an average. A comparison is not a calculation. Writing a value in the unit its
  source states for it, such as a fraction written as the percentage its series name states, is not
  a calculation either.
- **Inference**: a conclusion that no source states: a causal link, a forecast, an extrapolated
  trend, an implication, a recommendation, or a position attributed to an organisation.
- **Forecast**: a value that its source labels as a forecast, a projection or an outlook. A value
  for a period that ends on or after the stated date of its source is also a forecast, unless its
  source labels it as observed. Example: a publication dated 20 November 2025 that says
  exports "reached USD 250 billion in 2025" gives a forecast, because 2025 was not over. The past
  tense does not make the value observed.
- **Statement about the evidence**: a sentence that says what the research covered, as a section's
  description may ask, that the sources do not give some evidence, or that the report does not
  cover a topic. It states no fact from a source, so it needs no citation.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario."""

FAITHFUL_RELAY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Facts only from the sources",
        research_agent="""\
A search tool's answer summarises pages, and a summary can change, distort or invent what they say.
Use it only to find which pages to read, and read the page before you use anything the answer says.
Take every value, finding and characterisation the report may use from a page you read, as text or
as an image, or from a chunk a retrieval tool returns word for word.""",
        research_review="""\
A value, a finding or a characterisation that the findings hold only in a search tool's answer, on
no page that was read and in no chunk returned word for word, is a gap: ask for the page to be
read. A search tool's answer cites the page of each statement. When research has read the cited
page, the statement is not a gap. This holds also when the page text that you see does not contain
the statement: the page can give it only in its image, and you do not see the image.""",
        report_writer="""\
Everything the report states comes from a source. Never take a value, a finding or a
characterisation from a search tool's answer, because a summary can change, distort or invent what
the pages say: take it from the page that was read. Your own knowledge adds no fact, figure or
finding, and where it differs from a source, the source wins. The report carries no general
background, labelled or not, and no sentence that it labels as its own inference or synthesis.

Cite the source of every claim. A summary or a comparison carries the citations of the claims it
rests on, or stands directly after them; a summary elsewhere, such as in an opening overview or a
conclusion, repeats their citations. A sentence that can be neither cited nor built from cited
claims, and is not a statement about the evidence, is left out. A fact from the description of a
publication series, which has no citation form, names the series as its source in words. A cell of
a table that combines sources needs no citation when a passage next to the table cites its source,
as the rule "Every current value, with its own source" allows. A cell of a table that holds values
from one source needs no citation when the title of the table cites that source.""",
        report_review_blind="""\
A claim without a citation is a violation, unless it is a summary or a comparison of cited claims
beside it, a fact that names a publication series as its source, a statement about the evidence, or
a cell of a table whose source a passage right before or right after the table cites, or a cell of
a table that holds values from one source and cites that source in its title. A sentence
the draft labels as its own inference, synthesis or general background is a violation too.""",
    ),
    QualityRule(
        name="No conclusion that no source states",
        research_agent="""\
When the question asks why something happened or what it will lead to, look for sources that state
the cause or the effect. A movement in the data is not its own explanation.""",
        research_review="""\
A cause or an effect the question asks about, with no search in the findings for a source that
states it, is a gap. Never ask for a summary, a comparison or a conclusion: the research agent only
calls tools.""",
        report_writer="""\
The report may summarise and compare what the sources say, but it infers nothing. State no causal
link, forecast, extrapolated trend, implication, recommendation or position of an organisation
that the sources do not state. Give a cause, a driver or an effect only as a source states it, and
attribute it to that source. Where the question asks for an explanation the sources do not give,
say that they do not give it.""",
        report_review_blind="""\
A cause, a driver, an effect or a forecast stated without a citation is a violation. Whether a
cited claim goes beyond its source is not yours to judge: you cannot see the sources.""",
    ),
    QualityRule(
        name="Each figure with its source's value, unit and period",
        report_writer="""\
Keep every figure's value, unit, currency and period as its source gives them, and say whether it
is nominal or real where the source says so. Two changes are allowed, and neither of them is a
calculation:

- **One notation.** Values from different sources may be brought to one notation: a scale word, a
  currency symbol or code, a thousands separator, or a fraction written as a percentage, such as
  "USD 0.5 million" beside "USD 2 million" for a source's "$500,000". A conversion that needs a
  rate, such as into another currency, is a calculation.
- **Usable precision.** Round a value given with more digits than a reader can use, such as
  `0.0473918265`, to a usable precision: the precision the publications use for the same
  indicator, or what the context needs, such as 4.74%.

Otherwise keep each figure's precision. Do this also when the research question or the plan asks
to round figures or to give a number of decimals.""",
        report_review_blind="""\
A figure without its unit or its currency is a violation, and so is a figure with more digits than
a reader can use. Whether a figure matches its source is not yours to judge.""",
    ),
    QualityRule(
        name="Forecasts named as such",
        report_writer="""\
Name a forecast as a forecast. When its source labels it, use the source's own word, such as "the
publication forecasts" or "projects".

When a source labels a value as observed or as a forecast, use its label. A label is an explicit
word, such as "actual", "historical", "forecast" or "projection", or an observation status of a
dataset value that says that the value is observed or a forecast. The tense of a sentence is not a
label, and the word "estimate" is not a label either.

The date test, for a value that its source does not label: the value is a forecast when its period
ends on or after the stated date of its source. When neither the findings nor the data sources give
a stated date for the source, use today's date in its place. Examples:
- A publication with the publication date 2026-06-15 gives a value for 2026 and no label. The
  value is a forecast, because 2026 ends after 2026-06-15.
- A publication with the publication date 2025-11-20 says that exports "reached USD 250 billion in
  2025". The past tense is not a label. The value is a forecast, because 2025 ends after
  2025-11-20.
- The last update of a dataset is 2026-06-15, and its values have no observation status. Its value
  for 2026 is a forecast, and its value for June 2026 is a forecast, because both periods end after
  2026-06-15.

Write a forecast so that it reads as a forecast, for example "the forecast for 2030", "is expected
to grow by 3% in 2030" or "the publication expected growth of 3% in 2025". Never write it as what
happened, such as "grew by 3% in 2030".

Name the type of a forecast, such as "baseline" or "scenario", only when a source names it. Do not
call a value the baseline when no source names it so. A table names its values as forecasts in its
title, the sentence that introduces it, a column label or a note; each cell then needs no label of
its own.""",
    ),
    QualityRule(
        name="No finding stated more firmly than its source",
        report_writer="""\
Keep the certainty a source gives a finding: its hedging, its conditions and its scenario. A view a
source states as its own, such as "in our view" or "we expect", stays attributed to that source. A
forecast, as the rule "Forecasts named as such" decides, is never written as what happened, also
when its source writes it in the past tense. "Inflation
will ease next year, in our view" is relayed as "the publication expected inflation to ease the
following year", never as "inflation eased". A hypothetical or conditional finding stays
hypothetical or conditional, and a scenario value names its scenario. Never state a finding more
firmly than its source does, and add no promissory or guarantee-style wording the source does not
use, such as "will certainly" or "is guaranteed". Relaying a source's own hedging, such as "the
publication expects", is not a certainty label.""",
        report_review_blind="""\
Wording that promises or guarantees an outcome is a violation, and so is a value the draft calls
conditional or a scenario in one place and states as an established fact in another. A source's
hedging relayed in prose, such as "the publication expects", is correct wording, and is neither
speculative wording nor a certainty label.""",
    ),
    # The blind review has no part: a distortion shows only against the source, which it does not
    # see. The grounded review judges the writer part against the transcript.
    QualityRule(
        name="No exaggeration or distortion of a source",
        report_writer="""\
Relay each finding with the weight and the scope its source gives it. Keep the direction of a
source's verdict: where a source calls something slight, low or limited, the report does not
describe it with a word that points the other way, such as "sharp", "high" or
"significant", with or without a qualifier. Do not strengthen a finding with an intensifier the
source does not use, such as "dramatic" or "unprecedented", and do not widen it beyond its scope,
such as a finding for one region stated for the whole country, or a figure for one sector or
product line stated for a whole industry.""",
    ),
    QualityRule(
        name="The limitation stated where evidence is missing",
        report_writer="""\
Where the source-selection rule "When to say that evidence is missing" requires a statement that
evidence is missing, also say what the reader therefore cannot conclude. Never fill the gap with
your own knowledge or with an inference.""",
        report_review_blind="""\
Each fact that the research question or the approved plan asks for must be answered or declared
unavailable. A fact that the draft does neither is a violation. A plan item that names a source is
answered when its fact is answered, from that source or from another. Exception: a fact that a rule
excludes from the report. Leaving it out without comment is correct.""",
    ),
    QualityRule(
        name="Qualifying context next to its value",
        report_writer="""\
- For each value you give, give the qualifying context that its source states. Write it short, and
  keep its figures and conditions exact. Leave out the qualifying context of values that the report
  does not give.
- Give the qualifying context of a value in the same sentence or table row as the value. When the
  same qualifying context applies to every row of a table, you can give it one time, in the table
  title or in a note under the table. Do not give qualifying context in a separate section, bullet
  or paragraph.
- Do not define a measure that the query names. Example: when the query asks for the current
  account balance, do not explain what the current account balance is. Exception: the query or the
  approved plan asks for its definition or methodology. Then give only what the sources say about
  it. When no source gives it, say so.
- Do not apply the methodology of one source to a value from a different source. Exception: the
  first source says that its methodology applies to that value.""",
    ),
)
