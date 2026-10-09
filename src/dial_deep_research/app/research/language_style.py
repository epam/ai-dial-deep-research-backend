"""The language-and-style rules: a neutral register, no exclamation marks or slang, and names.

Only the report steps take part, because the rules govern the report's wording and nothing that
research retrieves. Emojis are checked by the app itself (`ReportEmojiRule`), so no part here asks a
review to judge them. "Names, not codes" is judged by the grounded review, because only the
findings hold the name behind a code. A channel's language, spelling and abbreviations are its
client rules.

The rules name no client, dataset, publication or tool.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

# The policy's terms, which open its block in every step that has a part of it. They are terms
# rather than a rule so that the grounded review receives them too: a rule with a blind part may
# not also set a grounded part.
LANGUAGE_AND_STYLE_TERMS = """\
A verbatim name is a publication title, a dataset or series name, an organisation's name, or a
quotation from a source. Write a verbatim name exactly as its source writes it. The rules of this
section do not apply inside a verbatim name. One exception: emojis. The application rejects an emoji
everywhere, also inside a quotation."""

LANGUAGE_AND_STYLE_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Neutral register",
        report_writer="""\
Describe what the sources say in precise, neutral terms. Do not use informal wording. Do not use
wording that sells, persuades or dramatises, such as "remarkable", "game-changing" or "a must". Do
not speculate.""",
        report_review_blind="""\
Informal, persuasive, promotional or speculative wording is a violation. Name the passage. These
are correct wording, not speculation:
- a forecast that the draft names as a forecast;
- a source's own hedging, such as "the publication expects".""",
    ),
    QualityRule(
        name="No exclamation marks or slang",
        report_writer="""\
Do not write exclamation marks. Do not use slang. A verbatim name keeps its own punctuation.""",
        report_review_blind="""\
An exclamation mark outside a verbatim name is a violation. Slang is a violation.""",
    ),
    QualityRule(
        name="Names, not codes",
        report_writer="""\
Refer to a codelist value, such as a country or an indicator, by its name, not by its code: "United
States", not `USA`; "Gross domestic product, constant prices, percent change", not `NGDP_RPCH`.
Refer to a dataset by its name, not by its id: "World Economic Outlook", not `IMF:WEO(1.0.0)`. Do
not write a code next to its name. Use a dataset id only inside a citation marker, such as
`[dataset IMF:WEO(1.0.0)]`.""",
        report_review_grounded="""\
A codelist code or a dataset id outside a citation marker is a violation. Name the code or the id,
and give its name from the findings or the data sources.""",
    ),
)

# Rendered only on a channel that configures a glossary.
LANGUAGE_AND_STYLE_GLOSSARY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Glossary terms are verbatim names",
        report_writer="""\
A glossary term is also a verbatim name. Write it in one of the forms that the glossary-terminology
rule allows.""",
        report_review_blind="""\
A glossary term is also a verbatim name. Its allowed forms are not violations: any one name of a
term that lists several names separated by a slash, the abbreviation after the full form's first
use, and a lower-case first letter in mid-sentence.""",
    ),
)
