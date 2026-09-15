"""The report length the word ceiling bounds, and finding a section by its configured name.

What is protected here: the count measures the report's prose, leaving out the inline citations
whichever form they take and nothing else. A references section is no part of a draft — the app
writes it after the loop settles — so a draft that wrote one keeps every one of its words, a
structure violation never earning length budget.

`find_section_heading_line` is the lookup the delivery step removes such a section with. It is
lenient about the decoration a writer may add around a name and strict about the heading level,
which is what keeps a renamed or mis-levelled section reported rather than silently swallowed.
"""

from __future__ import annotations

import pytest

from dial_deep_research.app.research.report_length import (
    count_report_words,
    find_section_heading_line,
    strip_inline_citations,
)
from dial_deep_research.utils.content import count_words

# --- citations ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "GDP rose [doc 150, page 3].",
        "GDP rose [dataset IMF:WEO].",
        "GDP rose [doc 150, page 1] [doc 150, page 3] [dataset IMF:WEO].",
        "GDP rose [DOC 150, PAGE 3].",
        "GDP rose [ doc 150, page 3 ].",
        "GDP rose [document 150, page 3].",
        "GDP rose [Document 150, Page 3].",
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
    assert count_report_words(cited) == count_words(plain)


# --- a references section the writer wrote ----------------------------------------------------


def test_a_references_section_the_writer_wrote_is_counted_whole() -> None:
    """The app writes that section, so a draft carrying one is in violation, not under budget."""
    draft = (
        "## Overview\n\nThe answer.\n\n" "## References\n\n### Documents\n\n| doc id | title |\n"
    )

    assert count_report_words(draft) == count_words(draft)


# --- finding a section by its configured name --------------------------------------------------


def test_the_section_heading_is_found_by_its_line() -> None:
    draft = "## Overview\n\nThe answer.\n\n## References\n\nSources listed here.\n"

    assert find_section_heading_line(draft, name="References") == 4


@pytest.mark.parametrize(
    "heading",
    ["## References", "## 3. References", "## **References**", "## References:"],
)
def test_the_heading_is_matched_through_its_decoration(heading: str) -> None:
    draft = f"## Overview\n\nThe answer.\n\n{heading}\n\nSources listed here.\n"

    assert find_section_heading_line(draft, name="References") == 4


@pytest.mark.parametrize("heading", ["# References", "### References", "**References**"])
def test_a_heading_at_another_level_is_not_the_section(heading: str) -> None:
    # Sections are `##` headings; anything else is a violation report-review reports, and the
    # delivery step must not quietly treat it as the section it was told to write.
    draft = f"## Overview\n\nThe answer.\n\n{heading}\n\nSources listed here.\n"

    assert find_section_heading_line(draft, name="References") is None


def test_a_renamed_section_is_not_found() -> None:
    draft = "## Overview\n\nThe answer.\n\n## Bibliography\n\nSources listed here.\n"

    assert find_section_heading_line(draft, name="References") is None


def test_a_draft_without_the_section_is_not_found() -> None:
    draft = "## Overview\n\nThe answer.\n\n## Detailed Analysis\n\nThe substance.\n"

    assert find_section_heading_line(draft, name="References") is None
