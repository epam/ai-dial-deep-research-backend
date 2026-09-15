"""Building the report's References section from what the servers reported about its sources.

What is protected here: every source the report cites gets a row, whether or not its metadata
resolved; the first column names the source and is the one that falls back to its identifier;
a cell carries what the channel stored, escaped so it cannot break the table; a server with
nothing cited contributes no table; and a report that cited nothing says so.

The section is text the app writes, so these are string rules over data — no server, no model.
"""

from __future__ import annotations

import pytest

from dial_deep_research.app.research.references import (
    ReferenceRow,
    ReferencesTableContent,
    build_references_section,
    dataset_rows,
    document_rows,
    strip_references_section,
)
from dial_deep_research.app_properties import ReferenceColumn

_URN = "IMF:WEO(1.0.0)"
_TITLE = "Market Outlook 2025"


def _columns(*pairs: tuple[str, str]) -> tuple[ReferenceColumn, ...]:
    return tuple(ReferenceColumn(heading=heading, key=key) for heading, key in pairs)


_DOCUMENT_COLUMNS = _columns(
    ("Publication", "publication_title"), ("Published", "publication_date")
)


def _documents(*rows: ReferenceRow) -> ReferencesTableContent:
    return ReferencesTableContent(title="Documents", columns=_DOCUMENT_COLUMNS, rows=list(rows))


def _section(*tables: ReferencesTableContent) -> str:
    return build_references_section(
        heading="References", empty_text="This report cites no source.", tables=list(tables)
    )


# --- the section ---------------------------------------------------------------------------------


def test_the_section_carries_its_heading_and_one_table_per_server() -> None:
    datasets = ReferencesTableContent(
        title="Datasets",
        columns=_columns(("Dataset", "name")),
        rows=[ReferenceRow(identifier=_URN, fields={"name": "World Economic Outlook"})],
    )
    documents = _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": _TITLE}))

    section = _section(documents, datasets)

    assert section.startswith("## References\n\n")
    assert "### Documents" in section
    assert "### Datasets" in section
    # The tables are written in the order they were given, which is the order of the servers.
    assert section.index("### Documents") < section.index("### Datasets")


def test_a_server_with_nothing_cited_contributes_no_table() -> None:
    empty = ReferencesTableContent(title="Datasets", columns=_columns(("Dataset", "name")), rows=[])
    documents = _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": _TITLE}))

    section = _section(documents, empty)

    assert "### Datasets" not in section
    assert "### Documents" in section


def test_a_report_citing_nothing_carries_the_configured_text() -> None:
    section = _section(
        _documents(),
        ReferencesTableContent(title="Datasets", columns=_columns(("Dataset", "name")), rows=[]),
    )

    assert section == "## References\n\nThis report cites no source."


def test_the_header_row_follows_the_configured_columns_in_order() -> None:
    section = _section(
        _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": _TITLE}))
    )

    assert "| Publication | Published |" in section
    assert "| --- | --- |" in section


# --- a row ---------------------------------------------------------------------------------------


def test_a_row_carries_what_the_server_reported() -> None:
    section = _section(
        _documents(
            ReferenceRow(
                identifier="doc 207",
                fields={"publication_title": _TITLE, "publication_date": "2025-03-01"},
            )
        )
    )

    assert f"| {_TITLE} | 2025-03-01 |" in section


def test_the_first_column_falls_back_to_the_identifier() -> None:
    """A source whose metadata did not resolve is listed, not dropped."""
    section = _section(_documents(ReferenceRow(identifier="doc 207", fields={})))

    assert "| doc 207 |  |" in section


def test_only_the_first_column_falls_back() -> None:
    section = _section(
        _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": _TITLE}))
    )

    assert f"| {_TITLE} |  |" in section


def test_a_dataset_row_falls_back_to_its_urn() -> None:
    datasets = ReferencesTableContent(
        title="Datasets",
        columns=_columns(("Dataset", "name"), ("Last update", "lastUpdated")),
        rows=[ReferenceRow(identifier=_URN, fields={})],
    )

    assert f"| {_URN} |  |" in _section(datasets)


def test_rows_keep_the_order_they_were_given() -> None:
    section = _section(
        _documents(
            ReferenceRow(identifier="doc 9", fields={"publication_title": "Second"}),
            ReferenceRow(identifier="doc 2", fields={"publication_title": "First"}),
        )
    )

    assert section.index("Second") < section.index("First")


# --- a cell --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("Market Outlook 2025", "Market Outlook 2025", id="string"),
        pytest.param(2025, "2025", id="integer"),
        pytest.param(1.5, "1.5", id="float"),
        pytest.param(True, "true", id="boolean"),
        pytest.param(["Trade", "Growth"], "Trade, Growth", id="list"),
        pytest.param([2024, 2025], "2024, 2025", id="list-of-numbers"),
        pytest.param(None, "", id="null"),
        pytest.param("", "", id="empty-string"),
        pytest.param({"nested": "object"}, "", id="object"),
    ],
)
def test_a_cell_renders_what_the_channel_stored(value: object, expected: str) -> None:
    """A channel owns its metadata, so a value is not required to be a string."""
    table = ReferencesTableContent(
        title="Documents",
        columns=_columns(("Publication", "publication_title"), ("Topics", "topics")),
        rows=[
            ReferenceRow(
                identifier="doc 207", fields={"publication_title": _TITLE, "topics": value}
            )
        ],
    )

    assert f"| {_TITLE} | {expected} |" in _section(table)


def test_a_pipe_in_a_value_cannot_break_the_table() -> None:
    section = _section(
        _documents(
            ReferenceRow(identifier="doc 207", fields={"publication_title": "Trade | Growth"})
        )
    )

    assert r"| Trade \| Growth |  |" in section


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_a_line_break_in_a_value_becomes_a_space(newline: str) -> None:
    section = _section(
        _documents(
            ReferenceRow(
                identifier="doc 207", fields={"publication_title": f"Market{newline}Outlook"}
            )
        )
    )

    assert "| Market Outlook |  |" in section
    # One row, not two: the break never ends the line.
    assert len([line for line in section.splitlines() if line.startswith("| Market")]) == 1


def test_a_heading_is_escaped_too() -> None:
    table = ReferencesTableContent(
        title="Documents",
        columns=_columns(("Pipe | Heading", "k")),
        rows=[ReferenceRow(identifier="doc 1", fields={"k": "v"})],
    )

    assert r"| Pipe \| Heading |" in _section(table)


# --- the rows the runner builds --------------------------------------------------------------


def test_document_rows_follow_the_cited_order_and_keep_unresolved_ids() -> None:
    rows = document_rows([207, 9], metadata={207: {"publication_title": _TITLE}})

    assert [row.identifier for row in rows] == ["doc 207", "doc 9"]
    assert rows[0].fields == {"publication_title": _TITLE}
    assert rows[1].fields == {}


def test_dataset_rows_follow_the_cited_order_and_keep_unresolved_urns() -> None:
    rows = dataset_rows([_URN, "ACME:OTHER"], records={_URN: {"name": "World Economic Outlook"}})

    assert [row.identifier for row in rows] == [_URN, "ACME:OTHER"]
    assert rows[1].fields == {}


# --- removing a section the writer wrote -----------------------------------------------------


def test_a_references_section_the_writer_wrote_is_removed() -> None:
    text = "## Overview\n\nThe answer.\n\n## References\n\n| doc id |\n"

    assert strip_references_section(text, heading="References") == "## Overview\n\nThe answer."


def test_a_decorated_heading_is_removed_too() -> None:
    text = "## Overview\n\nThe answer.\n\n## **References**\n\n| doc id |\n"

    assert strip_references_section(text, heading="References") == "## Overview\n\nThe answer."


def test_a_renamed_section_is_left_alone() -> None:
    text = "## Overview\n\nThe answer.\n\n## Bibliography\n\n| doc id |\n"

    assert strip_references_section(text, heading="References") == text


def test_a_heading_at_another_level_is_left_alone() -> None:
    text = "## Overview\n\nThe answer.\n\n### References\n\n| doc id |\n"

    assert strip_references_section(text, heading="References") == text


def test_a_text_without_the_section_is_unchanged() -> None:
    text = "## Overview\n\nThe answer.\n"

    assert strip_references_section(text, heading="References") == text
