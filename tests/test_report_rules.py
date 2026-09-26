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
from dial_deep_research.app.research.data_queries import DataQueryRecord, DataQueryStore
from dial_deep_research.app.research.report_rules import (
    ReportDataQueryRule,
    ReportDatasetIdRule,
    ReportDocumentIdRule,
    ReportHyperlinkRule,
    ReportLengthRule,
    ReportStructureRule,
    build_report_rules,
    render_writer_instructions,
)
from dial_deep_research.app_properties import ReportSection
from tests.citation_fakes import no_lookups

_SECTIONS = [
    ReportSection(name="Overview", description="The short answer.", protected=True),
    ReportSection(name="Detailed Analysis", description="The substance."),
]

# What the app appends is named in the configuration, not in the structure.
_REFERENCES_NAME = "References"

_CONFORMING = "## Overview\n\nThe answer.\n\n## Detailed Analysis\n\n### Trade\n\nThe substance.\n"

# What the app appends after the loop settles, which no draft may carry itself.
_WRITTEN_REFERENCES = "\n## References\n\n| doc id | title |\n"


# --- the structure rule -------------------------------------------------------------------------


def test_a_conforming_draft_has_no_structure_violations() -> None:
    assert (
        ReportStructureRule(sections=_SECTIONS, references_name=_REFERENCES_NAME).violations(
            _CONFORMING
        )
        == []
    )


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        pytest.param(
            "## Overview\n\nThe answer.\n",
            "a section is missing",
            id="missing",
        ),
        pytest.param(
            _CONFORMING.replace("## Detailed Analysis", "## Analysis In Detail"),
            "a section is renamed",
            id="renamed",
        ),
        pytest.param(
            _CONFORMING.replace("## Overview", "# Overview"),
            "a section is written at another level",
            id="wrong-level",
        ),
        pytest.param(
            _CONFORMING.replace("## Overview", "## **Overview**"),
            "a heading carries decoration the lookup tolerates",
            id="decorated",
        ),
        pytest.param(
            _CONFORMING.replace("## Overview", "## 1. Overview"),
            "a heading carries an ordinal",
            id="numbered",
        ),
        pytest.param(
            "## Detailed Analysis\n\nThe substance.\n\n## Overview\n\nThe answer.\n",
            "the sections are out of order",
            id="reordered",
        ),
        pytest.param(
            _CONFORMING + "\n## Appendix\n\nExtra material.\n",
            "the draft added a section of its own",
            id="extra",
        ),
        pytest.param(
            _CONFORMING + _WRITTEN_REFERENCES,
            "the draft wrote the references section the app builds",
            id="references-written",
        ),
        pytest.param("Just prose, no headings at all.\n", "the draft has no sections", id="none"),
    ],
)
def test_any_departure_from_the_configured_sections_is_reported(draft: str, reason: str) -> None:
    """One comparison covers every kind of mismatch, and the message carries both lists."""
    [violation] = ReportStructureRule(
        sections=_SECTIONS, references_name=_REFERENCES_NAME
    ).violations(draft)

    assert reason  # names the case under test
    for section in _SECTIONS:
        assert f"'{section.name}'" in violation


def test_the_violation_names_what_the_draft_carries() -> None:
    draft = _CONFORMING.replace("## Detailed Analysis", "## Analysis In Detail")

    [violation] = ReportStructureRule(
        sections=_SECTIONS, references_name=_REFERENCES_NAME
    ).violations(draft)

    expected, found = violation.split("It carries:")
    assert "'Detailed Analysis'" in expected
    assert "'Analysis In Detail'" in found
    assert "'Detailed Analysis'" not in found


def test_the_expected_sections_do_not_name_the_references_section() -> None:
    """The app appends it, so the writer is neither asked for it nor judged on it."""
    [violation] = ReportStructureRule(
        sections=_SECTIONS, references_name=_REFERENCES_NAME
    ).violations("Just prose.\n")

    assert "'References'" not in violation


def test_a_draft_with_no_sections_says_so() -> None:
    [violation] = ReportStructureRule(
        sections=_SECTIONS, references_name=_REFERENCES_NAME
    ).violations("Just prose.\n")

    assert violation.endswith("It carries: [].")


def test_sub_headings_inside_a_section_are_not_violations() -> None:
    draft = _CONFORMING.replace("### Trade", "### Trade\n\nText.\n\n#### Exports")

    assert (
        ReportStructureRule(sections=_SECTIONS, references_name=_REFERENCES_NAME).violations(draft)
        == []
    )


# --- the length rule ----------------------------------------------------------------------------


def test_a_draft_within_the_ceiling_has_no_length_violation() -> None:
    assert ReportLengthRule(max_words=100).violations(_CONFORMING) == []


def test_a_draft_at_the_ceiling_is_within_it() -> None:
    draft = "## Overview\n\none two"  # four counted words

    assert ReportLengthRule(max_words=4).violations(draft) == []


def test_an_over_long_draft_is_reported_with_both_numbers() -> None:
    draft = "## Overview\n\none two three"

    [violation] = ReportLengthRule(max_words=4).violations(draft)

    assert "5 words" in violation
    assert "4-word ceiling" in violation
    assert "the inline citations" in violation


def test_the_length_rule_measures_the_report_count_not_the_raw_text() -> None:
    # The citation is outside the measure, so this draft fits a ceiling its raw count would break.
    draft = "## Overview\n\nThe rate rose [doc 150, page 3]."

    assert ReportLengthRule(max_words=5).violations(draft) == []


def test_a_references_section_the_writer_wrote_counts_toward_the_ceiling() -> None:
    """A structure violation must not also earn the draft length budget."""
    draft = "## Overview\n\nThe rate rose.\n\n## References\n\n| doc id | title |\n"

    assert ReportLengthRule(max_words=5).violations(draft) != []


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
        build_report_rules(
            sections=_SECTIONS,
            max_words=2750,
            references_name=_REFERENCES_NAME,
            lookups=no_lookups(),
        )
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
    assert "the inline citations" in instructions
    # The references section is named only to forbid writing it, never as a heading to copy.
    assert "## References" not in instructions
    assert 'Do not write a "References" section' in instructions


# --- the data-query and identifier checks --------------------------------------------------------

_EXPLORER_URL = "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)"


def _record(query_id: str, *, series_count: int | None, url: str | None) -> DataQueryRecord:
    meta = {"queryId": query_id, **({"dataExplorerUrl": url} if url else {})}
    content = {
        "queryId": query_id,
        "datasetUrn": "IMF:WEO(1.0.0)",
        **({"seriesCount": series_count} if series_count is not None else {}),
    }
    return DataQueryRecord.model_validate({"_meta": meta, "structured_content": content})


def _data_query_violations(draft: str, **records: DataQueryRecord) -> list[str]:
    return ReportDataQueryRule(data_queries=DataQueryStore(records=dict(records))).violations(draft)


def test_the_writer_is_told_to_cite_only_queries_that_returned_data() -> None:
    instructions = render_writer_instructions(
        build_report_rules(
            sections=_SECTIONS,
            max_words=2750,
            references_name=_REFERENCES_NAME,
            lookups=no_lookups(),
        )
    )
    flat = " ".join(instructions.split())
    assert "Cite a data query only when it returned data" in flat
    for kind in ("did not execute", "candidate dataset", "result was empty"):
        assert kind in flat


def test_a_mistyped_query_id_asks_for_the_reported_id() -> None:
    [violation] = _data_query_violations(
        "Growth [data_query dq_0123abcd46].",
        dq_0123abcd45=_record("dq_0123abcd45", series_count=2, url=_EXPLORER_URL),
    )
    assert "dq_0123abcd46" in violation
    assert "no tool reported a query" in violation
    assert "exactly as the data-query tool reported it" in violation


def test_a_candidate_query_asks_for_a_dataset_citation_or_a_drop() -> None:
    candidate = DataQueryRecord(
        structured_content={"queryId": "dq_c", "datasetUrn": "IMF:WEO(1.0.0)"}
    )
    [violation] = _data_query_violations("No data for Germany [data_query dq_c].", dq_c=candidate)
    assert "dq_c" in violation
    assert "only a data query that returned data may be cited" in violation
    assert "`[dataset <urn>]`" in violation
    assert "drop the citation, or drop the statement" in violation


def test_a_query_that_ran_and_returned_nothing_asks_for_a_revision_despite_its_link() -> None:
    [violation] = _data_query_violations(
        "A value [data_query dq_1].", dq_1=_record("dq_1", series_count=None, url=_EXPLORER_URL)
    )
    assert "only a data query that returned data may be cited" in violation


def test_a_query_that_returned_data_raises_nothing() -> None:
    assert (
        _data_query_violations(
            "A value [data_query dq_1].", dq_1=_record("dq_1", series_count=3, url=_EXPLORER_URL)
        )
        == []
    )


def test_a_query_with_data_and_no_explorer_link_raises_nothing() -> None:
    assert (
        _data_query_violations(
            "A value [data_query dq_1].", dq_1=_record("dq_1", series_count=3, url=None)
        )
        == []
    )


class _Lookups:
    """Stands in for the turn's lookups: known ids, unknown ids, and the rest not looked up."""

    def __init__(
        self,
        *,
        datasets: dict[str, bool] | None = None,
        documents: dict[int, bool] | None = None,
    ) -> None:
        self._datasets = datasets or {}
        self._documents = documents or {}

    def dataset_known(self, urn: str) -> bool | None:
        return self._datasets.get(urn)

    def document_known(self, document_id: int) -> bool | None:
        return self._documents.get(document_id)


def test_an_unknown_dataset_urn_asks_for_the_reported_urn() -> None:
    lookups = _Lookups(datasets={"IMF:WEO(1.0.0)": True, "IMF:WEO(2.0.0)": False})
    [violation] = ReportDatasetIdRule(lookups=lookups).violations(  # type: ignore[arg-type]
        "A [dataset IMF:WEO(1.0.0)] and B [dataset IMF:WEO(2.0.0)]."
    )
    assert "IMF:WEO(2.0.0)" in violation
    assert "exactly as the dataset tool reported it" in violation


def test_an_unknown_document_id_is_reported_and_its_page_left_unchecked() -> None:
    lookups = _Lookups(documents={207: True, 999: False})
    [violation] = ReportDocumentIdRule(lookups=lookups).violations(  # type: ignore[arg-type]
        "A [doc 207, page 1] and B [doc 999, page 2]."
    )
    assert "document 999" in violation
    assert "page" not in violation


def test_an_available_id_no_tool_response_mentioned_passes() -> None:
    lookups = _Lookups(datasets={"IMF:WEO(1.0.0)": True})
    rule = ReportDatasetIdRule(lookups=lookups)  # type: ignore[arg-type]
    assert rule.violations("A [dataset IMF:WEO(1.0.0)].") == []


def test_an_id_not_looked_up_raises_nothing() -> None:
    """A failed lookup, or a channel without that server, leaves every id not looked up."""
    lookups = no_lookups()
    assert ReportDatasetIdRule(lookups=lookups).violations("A [dataset IMF:WEO(9.0.0)].") == []
    assert ReportDocumentIdRule(lookups=lookups).violations("A [doc 999, page 2].") == []
