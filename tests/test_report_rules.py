"""The report rules the app checks itself, without a model.

What is protected here: a rule states one thing to the writer and checks the same thing on the
draft. The structure rule reports every way a heading can fail to match the configuration —
missing, renamed, decorated, out of order, at the wrong level, or one section too many — and the
length rule fires on the measured count alone, and the hyperlink rule reports every form of
link the report may not carry.
"""

from __future__ import annotations

import pytest

from dial_deep_research.app.research.citations import remove_hyperlinks
from dial_deep_research.app.research.report_rules import (
    ReportHyperlinkRule,
    ReportLengthRule,
    ReportStructureRule,
    build_report_rules,
    render_writer_instructions,
)
from dial_deep_research.app_properties import ReportSection

_SECTIONS = [
    ReportSection(name="Overview", description="The short answer.", protected=True),
    ReportSection(name="Detailed Analysis", description="The substance."),
    ReportSection(
        name="References",
        description="The sources.",
        protected=True,
        references_section=True,
    ),
]

_CONFORMING = (
    "## Overview\n\nThe answer.\n\n"
    "## Detailed Analysis\n\n### Trade\n\nThe substance.\n\n"
    "## References\n\n| doc id | title |\n"
)


# --- the structure rule -------------------------------------------------------------------------


def test_a_conforming_draft_has_no_structure_violations() -> None:
    assert ReportStructureRule(sections=_SECTIONS).violations(_CONFORMING) == []


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        pytest.param(
            "## Overview\n\nThe answer.\n\n## References\n\n| doc id |\n",
            "a section is missing",
            id="missing",
        ),
        pytest.param(
            _CONFORMING.replace("## Detailed Analysis", "## Analysis In Detail"),
            "a section is renamed",
            id="renamed",
        ),
        pytest.param(
            _CONFORMING.replace("## References", "# References"),
            "a section is written at another level",
            id="wrong-level",
        ),
        pytest.param(
            _CONFORMING.replace("## References", "## **References**"),
            "a heading carries decoration the count tolerates",
            id="decorated",
        ),
        pytest.param(
            _CONFORMING.replace("## References", "## 3. References"),
            "a heading carries an ordinal",
            id="numbered",
        ),
        pytest.param(
            "## Detailed Analysis\n\nThe substance.\n\n"
            "## Overview\n\nThe answer.\n\n"
            "## References\n\n| doc id |\n",
            "the sections are out of order",
            id="reordered",
        ),
        pytest.param(
            _CONFORMING + "\n## Appendix\n\nExtra material.\n",
            "the draft added a section of its own",
            id="extra",
        ),
        pytest.param("Just prose, no headings at all.\n", "the draft has no sections", id="none"),
    ],
)
def test_any_departure_from_the_configured_sections_is_reported(draft: str, reason: str) -> None:
    """One comparison covers every kind of mismatch, and the message carries both lists."""
    [violation] = ReportStructureRule(sections=_SECTIONS).violations(draft)

    assert reason  # names the case under test
    for section in _SECTIONS:
        assert f"'{section.name}'" in violation


def test_the_violation_names_what_the_draft_carries() -> None:
    draft = _CONFORMING.replace("## References", "## Bibliography")

    [violation] = ReportStructureRule(sections=_SECTIONS).violations(draft)

    expected, found = violation.split("It carries:")
    assert "'References'" in expected
    assert "'Bibliography'" in found
    assert "'References'" not in found


def test_a_draft_with_no_sections_says_so() -> None:
    [violation] = ReportStructureRule(sections=_SECTIONS).violations("Just prose.\n")

    assert violation.endswith("It carries: [].")


def test_sub_headings_inside_a_section_are_not_violations() -> None:
    draft = _CONFORMING.replace("### Trade", "### Trade\n\nText.\n\n#### Exports")

    assert ReportStructureRule(sections=_SECTIONS).violations(draft) == []


# --- the length rule ----------------------------------------------------------------------------


def test_a_draft_within_the_ceiling_has_no_length_violation() -> None:
    assert ReportLengthRule(sections=_SECTIONS, max_words=100).violations(_CONFORMING) == []


def test_a_draft_at_the_ceiling_is_within_it() -> None:
    draft = "## Overview\n\none two"  # four counted words

    assert ReportLengthRule(sections=_SECTIONS, max_words=4).violations(draft) == []


def test_an_over_long_draft_is_reported_with_both_numbers() -> None:
    draft = "## Overview\n\none two three"

    [violation] = ReportLengthRule(sections=_SECTIONS, max_words=4).violations(draft)

    assert "5 words" in violation
    assert "4-word ceiling" in violation
    assert "the inline citations and the References section" in violation


def test_the_length_rule_measures_the_report_count_not_the_raw_text() -> None:
    # The citation and the references section are outside the measure, so this draft fits a
    # ceiling its raw word count would break.
    draft = (
        "## Overview\n\nThe rate rose [doc 150, page 3].\n\n## References\n\n| doc id | title |\n"
    )

    assert ReportLengthRule(sections=_SECTIONS, max_words=6).violations(draft) == []


# --- the hyperlink rule -------------------------------------------------------------------------


def test_a_draft_without_a_link_has_no_hyperlink_violations() -> None:
    draft = "The rate rose [doc 442, page 3], as the outlook noted [dataset IMF:WEO]."

    assert ReportHyperlinkRule().violations(draft) == []


def test_a_markdown_link_is_reported_as_a_rewrite_of_the_sentence() -> None:
    """The review loop is where a link is properly fixed, so the ask is a rewrite."""
    draft = "See the [latest outlook](https://example.org/outlook) for more."

    violations = ReportHyperlinkRule().violations(draft)

    assert len(violations) == 1
    assert "a Markdown link" in violations[0]
    assert "[latest outlook](https://example.org/outlook)" in violations[0]
    assert "rewrite the sentence" in violations[0]


@pytest.mark.parametrize(
    ("draft", "form"),
    [
        ("![chart](https://example.org/c.png)", "a Markdown image"),
        ("read <https://example.org/page> today", "an autolink"),
        ("published at https://example.org/outlook", "a bare URL"),
        ('see <a href="https://example.org">the note</a>', "a raw HTML anchor"),
        ('<img src="https://example.org/c.png">', "a raw HTML image tag"),
    ],
)
def test_every_hyperlink_form_is_a_violation(draft: str, form: str) -> None:
    violations = ReportHyperlinkRule().violations(draft)

    assert len(violations) == 1
    assert form in violations[0]


def test_a_reference_style_link_reports_its_use_and_its_definition() -> None:
    """Both halves are text pointing outward, and both have to leave the draft."""
    draft = "See the [outlook][ref] for more.\n\n[ref]: https://example.org/outlook\n"

    forms = [
        form
        for form in ("a reference-style link", "a link definition line")
        if any(form in violation for violation in ReportHyperlinkRule().violations(draft))
    ]

    assert forms == ["a reference-style link", "a link definition line"]


def test_every_link_in_a_draft_is_reported_separately() -> None:
    draft = "See the [outlook](https://example.org/a) and the [review](https://example.org/b)."

    assert len(ReportHyperlinkRule().violations(draft)) == 2


def test_the_rule_shares_its_detection_with_the_delivery_step() -> None:
    """One definition of a hyperlink backs the violation and the removal at delivery."""
    draft = "See the [outlook](https://example.org/a) and read https://example.org/b."

    assert len(ReportHyperlinkRule().violations(draft)) == len(remove_hyperlinks(draft).hyperlinks)


# --- what the writer is told --------------------------------------------------------------------


def test_the_writer_instructions_carry_every_rule_in_order() -> None:
    instructions = render_writer_instructions(
        build_report_rules(sections=_SECTIONS, max_words=2750)
    )

    assert (
        instructions.index("## Report structure")
        < instructions.index("## Length")
        < instructions.index("## No links")
    )
    # The structure is rendered as the template the writer copies, inside its tag.
    assert "<report_structure>\n## Overview" in instructions
    for section in _SECTIONS:
        assert section.description in instructions
    assert "2750 words" in instructions
    assert "the inline citations and the References section" in instructions
