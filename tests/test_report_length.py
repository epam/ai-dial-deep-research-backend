"""The report length the word ceiling bounds.

What is protected here: the count measures the report's prose. Inline citations are left out
whichever form they take. The references section is left out only when the configuration declares
one and the draft wrote it as configured — a structure with no references section, a renamed
heading, or a heading at the wrong level all keep every word, so a structure violation never earns
length budget.
"""

from __future__ import annotations

import pytest

from dial_deep_research.app.research.report_length import (
    count_report_words,
    strip_inline_citations,
)
from dial_deep_research.app_properties import ReportSection
from dial_deep_research.utils.content import count_words

_WITH_REFERENCES = [
    ReportSection(name="Overview", description="The short answer.", protected=True),
    ReportSection(name="Detailed Analysis", description="The substance."),
    ReportSection(
        name="References",
        description="The sources.",
        protected=True,
        references_section=True,
    ),
]

_NO_REFERENCES = [
    ReportSection(name="Summary", description="The answer.", protected=True),
    ReportSection(name="Evidence", description="What the sources say."),
    ReportSection(name="Outlook", description="What follows from the findings."),
]


# --- citations ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "GDP rose [doc 150, page 3].",
        "GDP rose [dataset IMF:WEO].",
        "GDP rose [doc 150, page 1] [doc 150, page 3] [dataset IMF:WEO].",
        "GDP rose [DOC 150, PAGE 3].",
        "GDP rose [ doc 150, page 3 ].",
    ],
)
def test_every_citation_form_leaves_the_sentence_alone(text: str) -> None:
    assert strip_inline_citations(text) == "GDP rose."


def test_ordinary_brackets_are_kept() -> None:
    text = "The rate [as revised] rose, per the table [1] of the annex."

    assert strip_inline_citations(text) == text


def test_a_citation_costs_nothing_in_the_count() -> None:
    cited = "## Overview\n\nGDP rose 2.1% [doc 150, page 3] [dataset IMF:WEO].\n"
    plain = "## Overview\n\nGDP rose 2.1%.\n"

    assert count_words(cited) > count_words(plain)
    assert count_report_words(cited, _WITH_REFERENCES) == count_words(plain)


# --- the references section -----------------------------------------------------------------


def test_the_references_section_and_everything_under_it_is_left_out() -> None:
    draft = (
        "## Overview\n\nThe answer.\n\n"
        "## References\n\n### Documents\n\n| doc id | title |\n\n### Datasets\n\n| dataset id |\n"
    )

    assert count_report_words(draft, _WITH_REFERENCES) == count_words("## Overview\n\nThe answer.")


@pytest.mark.parametrize(
    "heading",
    ["## References", "## 3. References", "## **References**", "## References:"],
)
def test_the_heading_is_matched_through_its_decoration(heading: str) -> None:
    draft = f"## Overview\n\nThe answer.\n\n{heading}\n\nSources listed here.\n"

    assert count_report_words(draft, _WITH_REFERENCES) == count_words("## Overview\n\nThe answer.")


@pytest.mark.parametrize("heading", ["# References", "### References", "**References**"])
def test_a_references_heading_at_the_wrong_level_is_counted(heading: str) -> None:
    # Sections are `##` headings; anything else is a violation report-review reports, and a
    # violation must not also buy length budget.
    draft = f"## Overview\n\nThe answer.\n\n{heading}\n\nSources listed here.\n"

    assert count_report_words(draft, _WITH_REFERENCES) == count_words(draft)


def test_a_draft_that_renamed_the_references_section_is_counted_whole() -> None:
    draft = "## Overview\n\nThe answer.\n\n## Bibliography\n\nSources listed here.\n"

    assert count_report_words(draft, _WITH_REFERENCES) == count_words(draft)


def test_a_draft_without_a_references_section_is_counted_whole() -> None:
    draft = "## Overview\n\nThe answer.\n\n## Detailed Analysis\n\nThe substance.\n"

    assert count_report_words(draft, _WITH_REFERENCES) == count_words(draft)


def test_a_structure_declaring_no_references_section_exempts_nothing() -> None:
    # The closing section is prose here, so it counts like any other — the exemption follows the
    # configured flag, never the position alone.
    draft = (
        "## Summary\n\nThe answer.\n\n"
        "## Evidence\n\nWhat the sources say.\n\n"
        "## Outlook\n\nGrowth is expected to continue through the next two quarters.\n"
    )

    assert count_report_words(draft, _NO_REFERENCES) == count_words(draft)
