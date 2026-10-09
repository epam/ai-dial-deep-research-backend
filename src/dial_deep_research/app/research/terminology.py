"""The terminology rules: a glossary concept is searched under both of its phrasings, and the report
uses each term with its source's meaning and one term per concept.

The glossary-terminology rule the writer and the blind review follow is `GLOSSARY_TERMINOLOGY_RULE`
in `prompts.py`. These rules add the research agent's search under glossary terms and the boundary
between a glossary term and a source's term, both rendered only on a channel that configures a
glossary, and the rule on accurate and consistent terms, which every channel gets. That rule is
judged by the grounded review, because whether a term keeps its source's meaning shows only against
the source.

The rules name no client, dataset, publication or tool, and none refers to a client rule: a client
rule that overrides one says so itself.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

TERMINOLOGY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Accurate and consistent terms",
        report_writer="""\
Use each technical term with the meaning that its source gives it. Keep the source's term. Do not
replace it with a synonym that changes the meaning, such as "exports" for "net exports", or
"unemployment" for "the unemployment rate". Use one term for one concept in all sections. Where
two sources use different terms for one concept, use one of them in all sections. A full form and
the abbreviation it introduces, such as "gross domestic product (GDP)", are one term.""",
        report_review_grounded="""\
These are violations:
- a term used with another meaning than its source gives it;
- a synonym that changes the source's meaning, such as "exports" for "net exports";
- two different terms for one concept.
Name the term and the source's term. These are not violations: one source's term used for a concept
that another source names differently, a full form with the abbreviation it introduces, and a term
inside a verbatim name, such as a publication title or a quotation.""",
    ),
)

# Rendered only on a channel that configures a glossary. The search rule says nothing about calling
# a glossary tool: whether the agent calls one is the data-sources instruction's, which depends on
# what the app's fetch of the glossary obtained.
TERMINOLOGY_GLOSSARY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Glossary terms in searches",
        research_agent="""\
A glossary term has a name and a definition. A question or a source can use either one. So when a
plan item refers to a concept that a glossary term names, search for it in two ways:
- by the term's name;
- by a short phrase of a few words from its definition.
For example, the glossary defines "real GDP" as "GDP adjusted for inflation". Then also search a
question about GDP adjusted for inflation as "real GDP", and the other way round. Do not search
with the whole definition: a long query matches too many unrelated pages. The glossary is the
`Glossary terms:` part of the data sources below, plus the terms that the glossary tools
returned.""",
    ),
    QualityRule(
        name="Glossary terms and source terms",
        report_writer="""\
Use a glossary term in place of a source's term only when both name exactly the same concept. If
you are not sure, keep the source's term.""",
    ),
)
