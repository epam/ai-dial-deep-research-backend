"""The language-and-style rules: a neutral register, no exclamation marks or slang, and names.

Only the report steps take part, because the rules govern the report's wording and nothing that
research retrieves. Emojis are checked by the app itself (`ReportEmojiRule`), so no part here asks a
review to judge them. "Codelist values by name" is judged by the grounded review, because only the
findings hold the name behind a code; its grounded part also flags a dataset id outside a citation
marker, which no app check catches yet. A channel's language, spelling and abbreviations are its
client rules.

The rules name no client, dataset, publication or tool.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

# The policy's terms, which open its block in every step that has a part of it. They are terms
# rather than a rule so that the grounded review receives them too: a rule with a blind part may
# not also set a grounded part.
LANGUAGE_AND_STYLE_TERMS = """\
- **Verbatim name**: a publication title, a dataset or series name, the name of an organisation,
  or a quotation from a source. The report writes it as its source does, so no rule
  of this policy applies inside it.

One exception: emojis. The application rejects an emoji everywhere, also inside a quotation."""

LANGUAGE_AND_STYLE_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Neutral register",
        report_writer="""\
Describe what the sources say in precise, neutral terms. Do not use informal wording. Do not use
wording that sells, persuades or dramatises, such as "remarkable", "game-changing" or "a must". Do
not speculate. A forecast that you name as a forecast, and a source's own hedging, such as "the
publication expects", are correct wording, not speculation.""",
        report_review_blind="""\
Informal, persuasive, promotional, dramatising or speculative wording is a violation. Name the
passage. These are correct wording, not speculation:
- a forecast that the draft names as a forecast;
- a source's own hedging, such as "the publication expects".""",
    ),
    QualityRule(
        name="No exclamation marks, emojis or slang",
        report_writer="""\
Do not write exclamation marks. Do not use slang. A verbatim name keeps its own punctuation.""",
        report_review_blind="""\
An exclamation mark outside a verbatim name is a violation. Slang is a violation.""",
    ),
    QualityRule(
        name="Codelist values by name",
        report_writer="""\
Refer to a codelist value, such as a country or an indicator, by its name, not by its
code: "United States", not `USA`; "Gross domestic product, constant prices, percent change", not
`NGDP_RPCH`. Do not write a code next to its name.""",
        report_review_grounded="""\
A codelist code in the draft is a violation. Name the code, and give its name
from the findings or the data sources.
A dataset id outside a citation marker is a violation too. Name the id, and give the dataset's name
from the data sources.""",
    ),
    QualityRule(
        name="Datasets by name, cited once",
        report_writer="""\
- Refer to a dataset by its name, not by its id: "World Economic Outlook", not `IMF:WEO(1.0.0)`.
  Use a dataset id only inside a citation marker.
- Name a dataset in the text only when the reader needs its name. Examples: the query asks which
  datasets cover a topic; one sentence gives values from two or more sources, so the
  source-selection rule "Every current value, with its own source" asks you to name the source of
  each value. In other cases, write "the dataset", and let the citation identify it.
- Cite a value from a dataset only with the `[data_query <id>]` marker of its query. The pill of
  that marker names the dataset. Do not add a `[dataset <urn>]` marker to the same statement.
- Use `[dataset <urn>]` only to cite a general statement about the dataset, or about its series,
  that no data query supports. Examples: when the dataset was last updated, which periods the
  dataset as a whole covers, or what the dataset gives for each part in which its series differs
  from a requested fact.
- Cite the periods that one series covers with the `[data_query <id>]` marker of the query that
  gave them. When no data query gave them, for example when an availability query showed
  them, cite the dataset.
- To name the dataset that a statement comes from, write its name in plain text, without a
  marker. Right: "The World Economic Outlook dataset reports inflation in the United States at 2%
  [data_query dq_0123abcd45]". Wrong: "[dataset IMF:WEO(1.0.0)] reports inflation in the United
  States at 2% [data_query dq_0123abcd45]".
- Put each citation marker after the statement that it supports.""",
        report_review_blind="""\
a figure that has no citation to a publication or a `[data_query <id>]` marker
is a violation. A `[dataset <urn>]` marker alone does not cite a figure.""",
    ),
)

# Rendered only on a channel that configures a glossary.
LANGUAGE_AND_STYLE_GLOSSARY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Glossary terms are verbatim names",
        report_writer="""\
A glossary term is also a verbatim name. Write it in one of the forms that the rule "Glossary terms"
allows.""",
        report_review_blind="""\
A glossary term is also a verbatim name. Its allowed forms are not violations: any one name of a
term that lists several names separated by a slash, the abbreviation after the full form's first
use, and a lower-case first letter in mid-sentence.""",
    ),
)
