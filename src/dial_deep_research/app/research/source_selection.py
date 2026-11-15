"""The source-selection rules: which values research looks for, and which values the report gives.

Each rule is one `QualityRule`, whose parts are what the research agent, research review, the
report writer and the blind review are told for it. The parts are written against what each step
can do: the research agent only calls tools, so its parts ask for retrievals and never for a note or
a summary; research review's gaps become the research agent's next plan, so they name retrievals
too; the blind review sees the draft and not the sources, so its checks judge only what the draft
shows. The grounded review, which sees the sources, judges the draft against the writer parts, so
no rule here sets a grounded part.

The rules name no client, dataset, publication or tool. What a channel's sources contain, and a rule
that holds only for them, such as the order of a dataset value and a publication value, goes into
that channel's client rules.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

# The policy's terms, which open its block in every step. They are not a rule.
SOURCE_SELECTION_TERMS = """\
These definitions say what the rules below mean. They are not a rule or a check of their own.

- **Approved plan**: the research plan that the user approved before research started. A plan that
  research review writes is not the approved plan.
- **Requested fact**: one figure, or one finding in words, that the user asks for in the query or
  in the approved plan. Other statements in a source are not requested facts. A requested fact has
  the parts below. The list is not complete:
  - **Indicator**: what is measured. Examples are "total exports" and "the unemployment rate". A
    growth rate, a share or an index is a different indicator.
  - **Unit**: the currency, or the measure of the same quantity. A scale word, for example million
    or billion, is notation, not a different unit.
  - **Scope**: the group that the value is about, within everything that the indicator measures.
    Examples are one age group, one industry and one product. When the query and the approved plan
    name no group, the scope is all groups, for example all age groups. A value for one group is
    then a near match. Example: for the unemployment rate, the youth unemployment rate is a near
    match.
  - **Geography**: a country, a region or a group of countries.
  - **Period**: the year, quarter or month that the value is about. This is the described period.
    The length of the period, for example a year or a month, is its frequency. The query or the
    approved plan names a frequency only with a word such as "monthly", "quarterly" or "annual". A
    time span such as "in 2024" or "over 2024" names no frequency. When the query and the approved
    plan name no frequency, a value at any frequency within the time span matches. Choose the
    frequency that is most appropriate for the query, among the frequencies that the sources give.
    Example: for "how did inflation change over 2024?", one value for the year does not show the
    change, so choose the most appropriate of the shorter frequencies. When the query or the
    approved plan names a frequency, a value at another frequency is a near match.
    The preparation phase settles the period before research starts. It asks the user. When the
    user leaves the choice to it, it applies the last 10 years for past values, and the next 3 years
    for forecasts. Thus each requested fact has a period.
  - **Scenario**: the case that the source names for a hypothetical value, for example "baseline",
    "adverse scenario" or "no-policy-change scenario". A hypothetical value is a forecast, a
    projection, or a value for an event that did not occur. A preliminary estimate for a period
    that had ended when the source stated it is not a hypothetical value. It is a value for the same
    requested fact as the final value. An observed value has no scenario. The assumptions of a value
    are not its scenario. They are qualifying context.
    - A forecast that its source does not label has the same scenario as a baseline forecast. This
      applies when a value is compared with a requested fact, and when two values are compared.
    - For a period that has ended, the observed value is the exact match, also when the query and
      the approved plan name no scenario. A forecast for that period is a near match, so the report
      gives it only when no observed value exists. When the user asks for a forecast, the forecast
      is the exact match, and an observed value is at most a near match.

  The query or the approved plan can name another part. Example: a query that compares an
  institution's forecast with the consensus forecast names who states the forecast. The
  institution's forecast and the consensus forecast are then two requested facts. When the query
  and the approved plan do not name who states a value, the values of different sources are values
  for the same requested fact. Where the query or the approved plan says to find a value is not a
  part of the requested fact. It tells research where to look first.

  Example: "the unemployment rate, euro area, 2024" names the indicator, the geography and the
  period. The scope is the whole labour force. There is no scenario, because the 2024 rate is an
  observed value.
- **Exact match**: a value with the same indicator, unit, scope, geography, period and scenario as
  the requested fact. When the query or the approved plan names a definition or basis, an exact
  match also has that definition or basis. A unit, a scenario, a definition or a basis that the
  query and the approved plan do not name matches any value. A part that the source of the value
  does not state also matches. Exception: when the query and the approved plan ask for no
  forecast, a forecast for a period that has ended is a near match.

  Exception for the unit: when no source of one kind gives the requested fact in the unit that the
  query or the approved plan names, a value of that kind of source that differs from the
  requested fact only in its unit is an exact match. Example: the query asks for GDP in USD, and
  the datasets give GDP only in EUR. The value in EUR is an exact match.
- **Near match**: a value with the same indicator as the requested fact, but with one or more parts
  that differ, for example the scope, geography, period or scenario. A value with another definition
  or basis than the one that the query or the approved plan names is also a near match.
  A value whose source does not state a part is not a near match for that reason alone. The report
  says which part the source does not state. Example: the query asks for the annual average
  unemployment rate in the euro area in 2024. A source gives the euro-area rate for 2024, and does
  not say whether it is the annual average or the December value. This value is an exact match.
  Examples for "the unemployment rate in the euro area in 2024":
  - the rate in Germany in 2024 has a narrower geography;
  - the youth unemployment rate in the euro area in 2024 has a narrower scope;
  - the euro-area rate in 2023 has a different period.
- **Value for another indicator**: a value with a different indicator. It is not an exact match and
  not a near match. It is not a value for the requested fact. Example: a share of world exports,
  when the query asks for an export volume.
- **Matching series**: a dataset series whose dimensions match a requested fact, as the term
  "Exact match" says, and that has a value for the requested period. Its value for a period that
  has ended can be a forecast. The term "Scenario" decides whether that value is an exact match or a
  near match, and when the report gives it. Examples: for GDP with no currency named, a GDP series
  in USD is a matching series. For the unemployment rate with no age group named, only a series
  for all ages is a
  matching series. When no series is for all ages, no series is a matching series. Each
  requested period is its own requested fact, so a series can be a matching series for some
  requested periods and a near-match series for others. For an indicator that a query about an
  effect, a cause or a relation names, a matching series has the geography and the period that the
  query or the approved plan names.
- **Near-match series**: a dataset series of the same indicator as a requested fact that is not a
  matching series. One or more of its dimensions differ, or it has no value for the requested
  period. Examples for "the unemployment rate in Canada in 2025": a youth unemployment series, a
  series for the United States, and a Canada series that ends in 2023. A series of another
  indicator is not a near-match series.
- **Value**: a figure, or a finding in words, that a source gives.
- **Kind of source**: publications or datasets.
- **Values for the same requested fact**: two values that match the same requested fact and agree
  with each other on all their parts. When the query or the approved plan names a definition or
  basis, they also agree on it. Example: a baseline value and an adverse-scenario value for
  the same year are not values for the same requested fact.
- **Stated date**: the date when the source gave the value.
  - For a publication, the stated date is the publication date in the document metadata.
    An edition name, for example an issue number such as "No. 5/2025", is not a stated date.
  - For a dataset value, the stated date is the date of the last update of the dataset.
- **Described period**: the period that the value is about. Example: a GDP forecast for 2027 that a
  source gave in 2025 has the stated date 2025 and the described period 2027.
- **Earlier value**: a value for the same requested fact that a current value supersedes. Example:
  the 2027 GDP forecast of the May edition, when the June edition also gives a 2027 forecast. A
  value that a publication quotes as its own earlier value is an earlier value too. Example: the
  2.1% in "the forecast was revised from 2.1% to 1.8%".
- **Value for another period**: a value with the same indicator, scope, geography and scenario as
  the requested fact, but for a different period, earlier or later. It is not a value for the
  requested fact. Example: when the query asks for 2025, the values for 2024 and 2026 are values
  for other periods.
- **Asks how a value was revised**: the query or the approved plan asks how the value for one period
  changed from one stated date to another. A query about a trend over several periods does not ask
  this. It asks for several requested facts, one for each period.
- **Methodology**: the information that a source gives about how it got a figure or an analysis.
  Examples are definitions, basis, coverage, sample, adjustments and calculation method.
- **Qualifying context**: what a source states about how it got a value and under which conditions
  the value holds. It includes:
  - what the value covers and excludes;
  - the definition and the basis of the value, for example a year-end value, or the upper bound of
    the target range of an interest rate;
  - the status and the caveats of the value, for example a preliminary value, or a warning that
    the risks to a forecast are on the downside;
  - the assumptions of a forecast or a scenario, for example an oil price, a policy path or the
    date of an event;
  - what a scenario stands for and its conditions, for example the scenario that the source calls
    the most likely one.

  Why a value changed, what drives it and what it means for something else are supporting context,
  not qualifying context. Qualifying context can be on the page of the value. It can also be in a
  methodology section, a box, a footnote, a note under a table or chart, or an appendix. When the
  query or the approved plan asks for a methodology, the methodology is a requested fact, not
  qualifying context.
- **Measured differently**: two values are measured differently when their two sources state a
  different definition, basis or calculation method. Example: an unemployment rate on a national
  definition and an unemployment rate on the ILO definition. A different basis or definition does
  not make a different indicator.
- **Supersede**: a newer value supersedes an older value for the same requested fact. The report
  does not give the superseded value, unless the query or the approved plan asks how the value was
  revised. The kinds of source decide which value supersedes which:
  - **Two publication values**: the value with the later stated date supersedes the other value.
    No age threshold applies.
  - **A dataset value and a publication value**: no value supersedes the other.
  - **Two dataset values**: no value supersedes the other.

  Exception: for a requested fact that is a figure, a finding in words never supersedes an older
  figure. A newer figure supersedes an older finding in words. Example: the April edition of a
  forecast publication gives a GDP growth forecast of 3.2% for 2026. The July edition says only
  that it revised the forecast up, and gives no figure. The 3.2% and the July finding in words are
  then both current values.

  When two values have the same stated date, no value supersedes the other. A superseded value
  can supersede a value that is older than it. Supersession applies in the same way between two
  near matches that agree with each other on all their parts. It also applies in the same way to
  supporting context about the same subject, the exception included.
- **Current value**: a value that no other retrieved value supersedes.
- **Supporting context**: content from the sources that does not answer a requested fact, but that
  helps the reader read the answer. It stands next to the answer and never replaces it. Research
  does not search for it. The writer can say in one clause how each item bears on the answer. That
  clause states only what a source states, or a comparison.
  Examples:
  - the values of other countries in a publication, for example the other entries of a ranking
    when the query asks for the top country;
  - a breakdown of a requested fact in a publication, for example the unemployment rate by age
    group when the query asks for the total rate;
  - a related indicator, for example a share when the query asks for a volume;
  - a driver of a value that a source states.

  The kind of a value does not decide if it is supporting context. The same value can be a near
  match and supporting context. When an exact match exists, a near match can stay only as
  supporting context. These are never supporting context:
  - a superseded value, also when it is a near match;
  - a value of a near-match series of a dataset;
  - an earlier value, or a value for another period, that the query or the approved plan does not
    ask for;
  - content about a different topic;
  - an account of the search;
  - a cause of a difference that no source states.
- **Account of the search**: a statement about how research searched. Examples: which sources
  research checked, or that one publication does not give a requested fact that another publication
  gives.
  These statements are not an account of the search:
  - a statement that the rule "When to say that evidence is missing" requires;
  - a statement that the rule "Nearest matches when no exact match exists" requires;
  - the statement in the Overview that names the question and the kinds of source that research
    covered."""

# Only the two research steps search, and only they are told how a failed tool call is handled, so
# only they get this term.
_REASONABLE_ATTEMPT = """
- **Reasonable attempt**: two or more searches for the evidence that find no evidence. The searches
  differ in wording or in filters, for example a metadata filter. For context that a retrieved page
  refers to, a reasonable attempt is to read the page that it refers to."""

# The terms as the two research steps read them.
SOURCE_SELECTION_RESEARCH_TERMS = SOURCE_SELECTION_TERMS + _REASONABLE_ATTEMPT

_LATEST_VALUE = "The latest value in each kind of source"
_DATASET_SEARCH = "Searching the datasets"
_NEAREST_MATCHES = "Nearest matches when no exact match exists"
_SUPPORTING_CONTEXT = "Supporting context and omitted content"
_DATES = "Stated date and described period"
_MISSING_EVIDENCE = "When to say that evidence is missing"

SOURCE_SELECTION_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Every requested fact, each on its own",
        research_agent="""\
Find each requested fact that the query and the approved plan ask for. Two requested
facts are different when they differ in any part, as the term "Requested fact" says. Search for
each requested fact. The other rules apply to each requested fact separately: each requested fact
has its own latest values. Example: a query compares the IMF forecast of euro-area GDP growth for
2026 with the consensus forecast. Search for the latest IMF forecast and for the latest consensus
forecast. The two can come from sources with different stated dates.""",
        research_review="""\
Find each requested fact that the query and the approved plan ask for. A
requested fact that research did not search for is a gap. A value for one requested fact never
supersedes a value for another requested fact, so a value for one requested fact does not close
the gap of another.""",
        report_writer=f"""\
- Answer each requested fact that the query and the approved plan ask for. These are not requested
  facts:
  - the later plans of research review. They are the retrieval steps that research took;
  - the part of a plan item that says where or how to search, such as a source or a kind of source
    to check, or a phrase such as "stated forecasts or context on X". The values that the search
    found answer the plan item.
- The other rules apply to each requested fact separately. A value for one requested fact never
  supersedes a value for another requested fact. Example: a query compares the IMF forecast of
  euro-area GDP growth for 2026 with the consensus forecast. Give the latest IMF forecast and the
  latest consensus forecast, also when they have different stated dates.
- When research found no value for a requested fact, follow the rule "{_MISSING_EVIDENCE}".""",
    ),
    QualityRule(
        name="Every current value, with its own source",
        research_agent=f"""\
Search each kind of source, as the rules "{_LATEST_VALUE}" and "{_DATASET_SEARCH}" say.
After that, do not search for more sources that give the same requested fact. Do not search for
the cause of a difference between values, unless the query or the approved plan asks for it. The
qualifying context of each value (the rule "Finding the qualifying context of each value") shows
if the values are measured differently.""",
        research_review="""\
A difference between values is not a gap. A missing cause of a difference is
not a gap, unless the query or the approved plan asks for the cause. Do not plan a search for more
sources that can disagree, because such a search has no end.""",
        report_writer=f"""\
- Give all current values for a requested fact. They can come from different sources and can
  disagree. Example: a dataset and a publication both give the 2025 value. Give the two values,
  each with its own citation.
- Cite each value. The citation identifies its source, so do not name the source in the text.
  Exceptions: when one sentence or phrase gives values from two or more sources, name the source of
  each value, so that the reader can tell which value comes from which source. The title of a table
  of one source names its source.
- When two values are measured differently, give the qualifying context of each value next to
  it. Example: "on the national definition" and "on the ILO definition".
- A table gives values from one source. Never put values from two or more sources in one table,
  unless the query or the approved plan explicitly asks to present the answer as a table. Only
  that request allows a table that combines sources. In such a table, make clear which source
  gives each value:
  - Prefer a passage right before or right after the table. The passage says which values come
    from which source, and cites each source. The values in the table then need no citation of
    their own. Citations in many cells make a table hard to read.
  - Otherwise, cite the source in each cell.
- Give a cause for a difference only when a source says that this cause explains the difference
  between these values. If not, do not say why the values are different. Do not write that the
  sources do not explain the difference, unless the query or the approved plan asks for the cause
  (the rule "{_MISSING_EVIDENCE}").
- Do not average or merge values, and do not give a range that includes them.
- Under this policy, omit a value only in these four cases. Other policies can also remove
  content.
  - the value is superseded, and the query or the approved plan does not ask how the value was
    revised;
  - the value is a near match, an exact match exists, and the value is not supporting context (the
    rules "{_NEAREST_MATCHES}" and "{_SUPPORTING_CONTEXT}");
  - the value is not for a requested fact. Exceptions: a near match that the rule
    "{_NEAREST_MATCHES}" requires or allows, and supporting context (the rule
    "{_SUPPORTING_CONTEXT}");
  - the query or the approved plan asks to omit it (the rule "{_SUPPORTING_CONTEXT}").
- Give each value that you keep with its own citation. Do this also when two values are the same
  figure. Do not put two or more citations on one figure. Exceptions: a value in a table that a
  passage next to the table attributes to its source, and a value in a table that holds values from
  one source and cites that source in its title.""",
        report_review_blind="""\
Check each pair of values that the draft gives for the same requested fact:
- Each value has its own citation. Exceptions: a value in a table that a passage right before or
  right after the table attributes to its source, with a citation, and a value in a table that holds
  values from one source and cites that source in its title.
- The draft does not average the two values.
- The draft does not give a range that includes the two values.

One figure with two or more citations is a violation. Do not ask for a cause of the difference,
unless the query or the approved plan asks for it. A figure computed from values for different
requested facts, for example the difference between two growth rates, merges no values. This
check does not cover it.""",
    ),
    QualityRule(
        name=_LATEST_VALUE,
        research_agent=f"""\
For each requested fact, search each kind of source of the channel for the
value with the latest stated date. For a requested fact that is a finding in words, search only the
publications, because a dataset series never gives a finding in words. A query about an effect, a
cause or a relation can name indicators. For such a query, search the publications for the effect,
the cause or the relation, and also search the datasets for the series of each indicator that it
names. Example: for "why did inflation rise in 2024?", search the publications for the cause, and
the datasets for the inflation series. For a requested fact that is a figure, search each kind of
source for two values:
- the latest figure;
- the latest value. It can be a finding in words, for example a statement that a forecast was
  revised.
When the latest value is a figure, the two values are the same value. A finding in words that is
newer than the latest figure does not end the search for the latest figure. The entry of a
dataset in the data sources is its latest release, so a dataset value needs no check for a later
release. This search is most important for
forecasts, for estimates that the source recalculates when information arrives, and for figures
that the source revises. When the query or the approved plan names a source, start with it. Then
search the other sources, as this rule and the rule "{_DATASET_SEARCH}"
say. Exception: the user explicitly limits research to the named sources. Example: "give the data
series from the datasets" names a source. "Use only the datasets" limits research to it.""",
        research_review="""\
When the channel has publications, a requested fact without a search of the
publications for its latest value is a gap. This applies also when a dataset gives a value. For
a requested fact that is a figure, a missing search for the latest figure is a gap. This applies
also when research found a newer finding in words. A dataset value needs no check for a later
release. A source that the query or the approved plan names does not close these gaps.
Exception: the user explicitly limits research to the named sources.""",
        report_writer="""\
Give the current exact matches for each requested fact. For a requested fact that is a figure,
when a finding in words is newer than the latest figure, give both values: the latest figure and
the newer finding in words.""",
    ),
    QualityRule(
        name=_DATASET_SEARCH,
        research_agent="""\
This applies to each requested fact that is a figure, and to each indicator that a query about an
effect, a cause or a relation names. Example: for the effect of inflation on GDP growth in the euro
area, this applies to the euro-area series of inflation and of GDP growth. A dataset series never
gives a finding in words.

- Find which dataset series match each requested fact. Start from the dataset structures in the
  data-source descriptions. For each dimension, a structure gives the number of codes and a sample
  of them. When the sample lists all codes of a dimension, the structure shows which codes exist.
- A series exists only when the dataset has every code that the series needs. When the structures
  show that a code is missing, the series does not exist. Make no availability query for that
  series. When
  the data-source descriptions show that no dataset can hold the indicator, call no dataset tool
  for this requested fact.
- A structure lists the codes of each dimension, not which combinations of codes have a series.
  So when the structures do not show that a code is missing, check with an availability query
  whether the series exists. This also covers a code that a sample does not list.
- Do not use a data query to find a series. A data query returns the data points of every series
  that it finds, and a broad query can find many series.
- Query the matching series for the requested period. When several matching series differ only
  in parts that the query and the approved plan do not name, such as the unit, the frequency or
  the basis, query only the ones that are most appropriate for the query. Example: for GDP with no
  currency named, query the GDP series in one currency, not in every currency that the dataset
  gives.
- Query the dataset also when a publication gives a value. Do this also when the query or the
  approved plan names a source that is not this
  dataset, for example "according to the World Economic Outlook". Exception: the user explicitly
  limits research to the sources that they name, for example "use only the World Economic
  Outlook".
- When no dataset has a matching series, check with availability queries what each dataset that
  has the indicator gives for each part that differs, for example which countries or which
  periods. Do not query the data of a near-match series.""",
        research_review="""\
These are gaps, unless the user explicitly limits research to other sources:
- a requested fact that is a figure, in a dataset that can hold its indicator, where the dataset
  structures do not show that a code that it needs is missing, and research made no availability
  query for its series;
- a requested fact with a matching series, where research queried no matching series for the
  requested period;
- a requested fact with no matching series, where research did not check with availability queries
  what a dataset that has the indicator gives for each part that differs.

The same applies to each indicator of a query about an effect, a cause or a relation. Never ask for
a data query of a near-match series.""",
    ),
    QualityRule(
        name="Other periods and earlier values only when asked",
        research_agent=f"""\
Get each value that the query or the approved plan asks for. When the query or
the approved plan asks how a value was revised, get each earlier value in the date range that it
gives. Do not get an earlier value, or a value for another period, that the query or the approved
plan does not ask for. This limit does not apply to a near match that the rule
"{_NEAREST_MATCHES}" requires or allows.""",
        research_review=f"""\
A value that the query or the approved plan asks for, and that is not in the
findings, is a gap until research makes a reasonable attempt (the rule "{_MISSING_EVIDENCE}"). An earlier value, or a value for another period, that the query or the approved plan
does not ask for is never a gap.""",
        report_writer=f"""\
Give each value that the query or the approved plan asks for. For a question about the
current forecast, give the current forecasts and no earlier forecast. For a question about how a
forecast was revised, give each earlier value with its stated date. Do not give an earlier value,
or a value for another period, that the query or the approved plan does not ask for. This does
not apply to a near match that the rule "{_NEAREST_MATCHES}" requires or allows.""",
    ),
    QualityRule(
        name=_SUPPORTING_CONTEXT,
        research_agent=f"""\
Search for the requested facts. Do not do searches only for supporting
context. Exception: the stated date, the described period and the qualifying context of a value in
the findings, which the rules "{_DATES}" and "Finding the qualifying
context of each value" require. Exception also: the dataset series of each indicator that a query
about an effect, a cause or a relation names, which the rule "{_DATASET_SEARCH}" requires.""",
        research_review=f"""\
Missing supporting context is never a gap. The stated date, the described
period and the qualifying context of a value of supporting context are not supporting context.
The rules "{_DATES}" and "Finding the qualifying context of each value"
decide if they are a gap. The dataset series of each indicator that a query about an effect, a
cause or a relation names are not supporting context. The rule "{_DATASET_SEARCH}" decides if
they are a gap.""",
        report_writer="""\
- Include supporting context. Include an item only when you can say in one clause how it bears
  on the answer. That clause states only what a source states, or a comparison.
- Omit the content that the term "Supporting context" excludes.
- When the query or the approved plan asks to omit some content, omit it. Keep what another rule
  requires next to a value, for example its described period. Do not say that you omitted part of
  the request.""",
        report_review_blind="""\
- An account of the search, as the term defines it, is a violation.
- Content that the query or the approved plan asks to omit is a violation. Exception: content
  that another rule requires next to a value.""",
    ),
    QualityRule(
        name="Finding the qualifying context of each value",
        research_agent="""\
For each value that the report can use, including the values of supporting
context, get its qualifying context from the sources. Without it, you cannot know if two values
are for the same requested fact, or if they are measured differently. When a retrieved page refers
to qualifying context, for example a methodology section or an appendix, read that context.""",
        research_review="""\
A retrieved page can refer to qualifying context, for example a footnote or a
methodology section. When research did not read that context, this is a gap. Qualifying context
that no source gives is not a gap.""",
    ),
    QualityRule(
        name=_DATES,
        research_agent="""\
Get the stated date and the described period of each value that the report can
use, including the values of supporting context, from the tool results. Get the stated date of a
publication from the document metadata that a tool gives. Do not get it from the page text,
because the page text can have an old template date.""",
        research_review=f"""\
A value that the report can use, without its stated date, is a gap until
research gets the date. A value that the report can use, without its described period, is a gap
until research makes a reasonable attempt (the rule "{_MISSING_EVIDENCE}").""",
        report_writer="""\
- Give the described period of each value.
- The citation popup of each source shows its stated date. So do not write the stated date in the
  text, unless the answer needs it. Example: the query or the approved plan asks how a value was
  revised. Exception: the title of a table of one source gives the stated date of its source.
- When you write a stated date in the text, take it only from the metadata of the source: the
  publication date of a publication in the findings, or the last update of a dataset in the
  findings or the data sources. Never take a
  date from the page text or a page image, and never infer one.
- Example: a dataset and a publication both give a forecast for 2027. Cite the two values, each
  with its own citation, and give the period 2027 in the text.""",
        report_review_blind="""\
- A value without its described period is a violation.
- Do not ask for the stated date of a value. Its citation shows it. A stated date in the title of a
  table of one source is not a violation.
- A year column or a row label in a table gives the described period of each value in it. Do not
  ask to mark such values as historical or actual.""",
    ),
    QualityRule(
        name=_NEAREST_MATCHES,
        research_agent="""\
When you find no exact match for a requested fact, search the same sources for
its nearest matches. For each part that can differ, the nearest match is:
- for a period, the nearest periods before and after it;
- for a geography, the smallest region or group of countries that contains it, then a wider
  region, then the world. Stop at the first geography that gives a value. Example: North America,
  when the query asks for the United States;
- for a group of countries that no source aggregates, a few key member countries. Do not get
  every member;
- for a scope, the smallest scope that contains it;
- for a frequency that the query or the approved plan names, the other frequencies that the
  sources give;
- for a scenario, or for a definition or basis, the other values that the sources give.

Search the nearest periods in the same geography before you search a wider geography. Do not
search for other near matches.

For a near-match series of a dataset, the list of nearest matches above does not apply. Check with
availability queries what the dataset gives for each part that differs. Do not query the data of
a near-match series.""",
        research_review="""\
A requested fact without an exact match is a gap until research has searched
its nearest periods in the same geography, and the next wider geography. Ask only for the nearest
matches. There are few of them, so this search has an end. For the datasets, availability queries
that show what a dataset gives for each part that differs close this gap. Never ask for a data
query of a near-match series.""",
        report_writer=f"""\
- When the findings hold no exact match for a requested fact, say that the sources give no exact
  match. Then give only its nearest matches:
  - the nearest periods;
  - the smallest geography that gives a value;
  - a few key members of a group of countries that no source aggregates;
  - the smallest scope that contains the requested scope;
  - the values for other frequencies, when the query or the approved plan names a frequency;
  - the values for other scenarios, or for another definition or basis.
- A near match that differs in fewer parts is nearer. A near match for a different period is
  nearer than a near match for a wider geography.
- When none of these nearest matches exists, you can give the other near matches in the findings.
- Say how each near match is different from the requested fact.
- When the findings hold no exact match for a requested fact, the list of nearest matches above
  does not apply to a near-match series of a dataset. Do not give a value of a near-match
  series. Say what the dataset gives for each part that differs, and cite the dataset. Examples:
  "The dataset
  gives the unemployment rate of the United States and Mexico, not of Canada." "The dataset gives
  the unemployment rate for each age group, but not for all ages." "The dataset series of the
  unemployment rate of Canada ends in 2023."
- When an exact match exists for a requested fact, give no near match for it. This applies also
  when the near match agrees with the exact match. Exception: a near match that is supporting
  context (the rule "{_SUPPORTING_CONTEXT}").""",
        report_review_blind="""\
- A near match without a statement of how it is different from the requested fact is a violation.
- A near match that the draft gives as an answer next to an exact match for the same requested
  fact is a violation. When an exact match exists, a near match in Additional context is
  supporting context, not a violation.
- The draft says that a dataset series differs from a requested fact, and also gives a value of
  that series for that requested fact. This is a violation. A value of the same series for another
  requested period that the series covers is not a violation. Example: the draft says that the
  dataset has the unemployment rate of the United States, not of Canada, and gives the United
  States rate for 2025. It is not a violation when the draft names such a series, says how it
  differs and cites the dataset, but gives no value from it. It is also not a violation when the
  series differs from the requested fact only in its unit and the draft states the unit. Such a
  value can be an exact match. It is also not a violation when the value is a forecast for a
  period that has ended and the draft says that it is a forecast.""",
    ),
    QualityRule(
        name=_MISSING_EVIDENCE,
        research_agent="""\
Make a reasonable attempt to find each item of evidence that a rule asks for,
including qualifying context and dates. When the attempt finds nothing, continue without that
item.""",
        research_review="""\
A gap for an item of evidence stays open until the findings show a
reasonable attempt to find that item. After that attempt, the item is missing. A missing item is
not a gap.""",
        report_writer=f"""\
- Say that evidence is missing when no retrieved source gives an item that the user asked for.
  The user asks in the query or in the approved plan. Name that item.
- When the query or the approved plan asks for a figure that needs the missing item, for example a
  change over time, say that the report cannot give that figure.
  - Do not say that other evidence is missing. Do not say that a stated date is missing.
- When the datasets give a value for a requested fact and the publications give none, say that
  the publications give no value for it. Example: "The publications give no value for 2025." Say
  this only when the findings show two or more searches in the publications that found no value.
- Never name the datasets as sources that do not give a requested fact, a figure or a finding in
  words. A statement about all the sources together is allowed, for example "No source gives the
  2025 value". Exception: a statement of what a dataset gives for each part that differs from a
  requested fact, with the dataset cited. The rule "{_NEAREST_MATCHES}" decides when to give it.
- When one source gives a requested fact, do not say that another source of the same kind does
  not give it.""",
        report_review_blind="""\
- When the draft says that the sources do not give an item, accept this statement for each check
  that asks for that item. Do not report it as a violation.
- A statement that names the datasets as sources that do not give a requested fact is a violation.
  A statement about all the sources together is not. Exception: a statement of what a dataset
  gives for each part that differs from a requested fact, with the dataset cited.""",
    ),
)
