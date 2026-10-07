"""The faithful-relay rules: the report relays what the sources say, and nothing else.

It invents, infers and computes nothing, keeps every figure as its source gives it, and states no
finding more firmly or more broadly than its source does. Each rule is one `QualityRule`, written
against what each step can do, as the source-selection rules are: the research agent only calls
tools, research review's gaps become the research agent's next plan, and report review's own call
sees the draft and not the sources, so its checks judge only what the draft shows. Whether a cited
claim is faithful to its source is judged by report review's grounded review, which sees the
research transcript and judges the draft against the writer parts.

The rules name no client, dataset, publication or tool.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

# The source-selection block renders before this one and defines "value" and "stated date", which
# these definitions use.
_TERMS = """\
These definitions say what the rules below mean. They are not a rule or a check of their own. The
source-selection terms above, such as value, stated date and described period, apply here too.

- **Source**: the result of a research tool call, or the data sources this prompt carries, such as
  the knowledge base's descriptions and what the application fetched from the dataset server. A
  search tool's answer is not a source: it summarises pages, and a summary can change, distort or
  invent what the pages say, such as a value, a sum or a characterisation that no page states. It
  only points at where the evidence lives; read the page instead. A page read as text or as an
  image, and a chunk a retrieval tool returns word for word, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say, and
  adds nothing to them, such as "both sources expect growth to slow in 2026".
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic or modelling that produces a number no source gives: a growth rate
  derived from two levels, a difference or a gap in percentage points, a ratio, a multiple such as
  "twice as large", a share, a sum, an average, an elasticity or a regression estimate. A comparison
  is not a calculation. Writing a value in another notation, such as a fraction as a percentage, is
  not a calculation either, and neither is rounding a value given with more digits than a reader
  can use.
- **Inference**: a conclusion that no source states: a causal link, a forecast, an extrapolated
  trend, an implication, a recommendation, or a position attributed to an organisation.
- **Forecast** and **estimate**: a value that its source calls a forecast, a projection, an
  outlook, an estimate or a preliminary figure, or a value for a period that had not ended when the
  source stated it. A note of December 2023 giving a figure "for 2023" gives an estimate, because
  2023 was not over; a report of April 2026 giving growth "in 2026" gives a forecast.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario.
- **Statement about the evidence**: a sentence that says what the research covered, as a
  section's description may ask, that the sources do not give some evidence, or that the report
  does not cover a topic. It states no fact from a source, so it needs no citation."""

FAITHFUL_RELAY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Faithful-relay terms",
        research_agent=_TERMS,
        research_review=_TERMS,
        report_writer=_TERMS,
        report_review=_TERMS,
    ),
    QualityRule(
        name="Only the sources",
        research_agent="""\
A search tool's answer summarises pages, and a summary can change, distort or invent what they say.
Use it only to find which pages to read, and read the page before you use anything the answer says.
Take every value, finding and characterisation the report may use from a page you read, as text or
as an image, or from a chunk a retrieval tool returns word for word.""",
        research_review="""\
A value, a finding or a characterisation that the findings hold only in a search tool's answer, on
no page that was read and in no chunk returned word for word, is a gap: ask for the page to be
read.""",
        report_writer="""\
Everything the report states comes from a source. Never take a value, a finding or a
characterisation from a search tool's answer, because a summary can change, distort or invent what
the pages say: take it from the page that was read. Your own knowledge adds no fact, figure or
finding, and where it differs from a source, the source wins. The report carries no general
background, labelled or not.

Cite the source of every claim. A summary or a comparison carries the citations of the claims it
rests on, or stands directly after them; a summary elsewhere, such as in an opening overview or a
conclusion, repeats their citations. A sentence that can be neither cited nor built from cited
claims, and is not a statement about the evidence, is left out. A fact from the description of a
publication series, which has no citation form, names the series as its source in words.""",
        report_review="""\
A claim without a citation is a violation, unless it is a summary or a comparison standing directly
after the cited claims it rests on, a fact that names a publication series as its source, or a
statement about the evidence. A sentence the draft labels as its own inference, synthesis or
general background is a violation too.""",
    ),
    QualityRule(
        name="No inference",
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
        report_review="""\
A cause, a driver, an effect or a forecast stated without a citation is a violation. Whether a
cited claim goes beyond its source is not yours to judge: you cannot see the sources.""",
    ),
    QualityRule(
        name="Figures as the source gives them",
        report_writer="""\
Keep every figure's value, unit, currency and period as its source gives them, and say whether it
is nominal or real where the source says so. Three changes are allowed, and none of them is a
calculation:

- **One notation.** Values from different sources may be brought to one notation: a scale word, a
  currency symbol or code, a thousands separator, or a fraction written as a percentage, such as
  "USD 0.5 million" beside "USD 2 million" for a source's "$500,000". A conversion that needs a
  rate, such as into another currency, is a calculation.
- **Usable precision.** Round a value given with more digits than a reader can use, such as
  `0.0473918265`, to a usable precision: the precision the publications use for the same
  indicator, or what the context needs, such as 4.74%.
- **Requested rounding.** Round a figure as the research question or the plan asks.

Otherwise keep each figure's precision.""",
        report_review="""\
A figure without its unit or its currency is a violation, and so is a figure with more digits than
a reader can use, and a figure not rounded as the research question or the plan asks. Whether a
figure matches its source is not yours to judge.""",
    ),
    QualityRule(
        name="Forecasts and estimates",
        report_writer="""\
Name a forecast as a forecast and an estimate as an estimate, in the source's own terms, such as
"the publication forecasts" or "a preliminary estimate". Never present one as an observed value. A
dataset's stated date is its last update: its values for any later period are forecasts, and the
report names them so and writes them in the future or conditional tense, such as "the dataset's
forecast for 2030", never "grew by 3% in 2030".""",
        report_review="""\
A value for a period that had not ended by its stated date, or has not ended today, stated as
observed, such as "exports grew 3% in 2027", is a violation. Where the draft states a dataset's
last update, a value from that dataset for a later period is a forecast, and stating it as
observed is a violation. A forecast named as a forecast is correct wording, never speculative
wording. A table names its values as forecasts or estimates when its title, the sentence
introducing it, a column label or a note says so; each cell needs no label of its own.""",
    ),
    QualityRule(
        name="Certainty",
        report_writer="""\
Keep the certainty a source gives a finding: its hedging, its conditions and its scenario. A view a
source states as its own, such as "in our view" or "we expect", stays attributed to that source,
and keeps its tense: a view about what will happen is never written as what happened. "Inflation
will ease next year, in our view" is relayed as "the publication expected inflation to ease the
following year", never as "inflation eased". A hypothetical or conditional finding stays
hypothetical or conditional, and a scenario value names its scenario. Never state a finding more
firmly than its source does, and add no promissory or guarantee-style wording the source does not
use, such as "will certainly" or "is guaranteed". Relaying a source's own hedging, such as "the
publication expects", is not a certainty label.""",
        report_review="""\
Wording that promises or guarantees an outcome is a violation, and so is a value the draft calls
conditional or a scenario in one place and states as an established fact in another. A source's
hedging relayed in prose, such as "the publication expects", is correct wording, and is neither
speculative wording nor a certainty label.""",
    ),
    # Report review's own call has no part: a distortion shows only against the source, which it
    # does not see. The grounded review judges the writer part against the transcript.
    QualityRule(
        name="No distortion",
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
        name="Gaps in the evidence",
        report_writer="""\
Where the sources lack the evidence for part of the question, say what is missing and what
therefore cannot be concluded. Never fill the gap with your own knowledge or with an
inference.""",
        report_review="""\
A part of the research question that the draft neither answers nor declares unavailable is a
violation. A sentence saying that the report does not cover a topic declares it.""",
    ),
)
