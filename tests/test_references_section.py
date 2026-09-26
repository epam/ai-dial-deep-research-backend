"""Building the report's References section from what the servers reported about its sources.

What is protected here: every source the report cites gets a row, whether or not its metadata
resolved; the first column names the source and is the one that falls back to its identifier;
a cell carries what the channel stored, escaped so it cannot break the table; a server with
nothing cited contributes no table; a report that cited nothing says so; and a row whose source the
reader can open carries a pill in its first cell, labelled with the row's name alone.

The section is text the app writes, so these are string rules over data — no server, no model.
"""

from __future__ import annotations

import pytest

from dial_deep_research.app.research.citations import (
    DATASET_MIME_TYPE,
    PDF_MIME_TYPE,
    ConvertibleDatasetCitation,
    ConvertibleDocumentCitation,
    DatasetSource,
    DatasetTableEntry,
    cited_dataset_entries,
    cited_dataset_urns,
    find_hyperlinks,
)
from dial_deep_research.app.research.data_queries import DataQueryRecord
from dial_deep_research.app.research.references import (
    ReferenceRow,
    ReferencesSection,
    ReferencesTableContent,
    build_references_section,
    dataset_rows,
    document_rows,
)
from dial_deep_research.app_properties import ReferenceColumn

_URN = "IMF:WEO(1.0.0)"
_TITLE = "Market Outlook 2025"
_PDF_URL = "files/bucket/appdata/deep-research/report.pdf"
_PORTAL_URL = "https://portal.example.org/datasets/imf-weo"


def _entries(*urns: str) -> list[DatasetTableEntry]:
    return [DatasetTableEntry(urn=urn) for urn in urns]


def _columns(*pairs: tuple[str, str]) -> tuple[ReferenceColumn, ...]:
    return tuple(ReferenceColumn(heading=heading, key=key) for heading, key in pairs)


_DOCUMENT_COLUMNS = _columns(
    ("Publication", "publication_title"), ("Published", "publication_date")
)


def _documents(*rows: ReferenceRow) -> ReferencesTableContent:
    return ReferencesTableContent(title="Documents", columns=_DOCUMENT_COLUMNS, rows=list(rows))


def _built(
    *tables: ReferencesTableContent, first_index: int = 0, pill_title_max_chars: int | None = None
) -> ReferencesSection:
    tag_ids = iter(f"row-{number}" for number in range(100))
    return build_references_section(
        heading="References",
        empty_text="This report cites no source.",
        tables=list(tables),
        first_index=first_index,
        pill_title_max_chars=pill_title_max_chars,
        make_tag_id=lambda: next(tag_ids),
    )


def _section(*tables: ReferencesTableContent) -> str:
    return _built(*tables).text


def _document_target(document_id: int = 207, page: int = 13) -> ConvertibleDocumentCitation:
    return ConvertibleDocumentCitation(document_id=document_id, page=page, url=_PDF_URL)


def _dataset_target(source: DatasetSource) -> ConvertibleDatasetCitation:
    return ConvertibleDatasetCitation(dataset_id=_URN, url=_PORTAL_URL, source=source)


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


def test_a_first_column_value_of_whitespace_falls_back_too() -> None:
    """A value that only looks filled leaves a row a reader cannot identify, so it is not one."""
    section = _section(
        _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": "   "}))
    )

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
        pytest.param("   ", "", id="whitespace-only-string"),
        pytest.param("  Market Outlook 2025  ", "Market Outlook 2025", id="padded-string"),
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


# --- a row that opens its source ----------------------------------------------------------------


def test_an_openable_document_row_carries_only_a_tag_in_its_first_cell() -> None:
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 207",
                fields={"publication_title": _TITLE, "publication_date": "2025-03-01"},
                target=_document_target(page=13),
            )
        )
    )

    assert '| <cit data-id="row-0"></cit> | 2025-03-01 |' in built.text
    assert _TITLE not in built.text
    [annotation] = built.annotations
    assert annotation.target.selector.id == "row-0"
    assert annotation.body.source.attachment.type == PDF_MIME_TYPE
    assert annotation.body.source.attachment.url == _PDF_URL
    assert annotation.body.selector is not None
    assert annotation.body.selector.page == 13
    assert annotation.body.quote is None


def test_a_document_row_is_labelled_with_its_name_and_no_page() -> None:
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 207",
                fields={"publication_title": _TITLE},
                target=_document_target(),
            )
        )
    )

    [annotation] = built.annotations
    assert annotation.body.title == _TITLE
    assert annotation.body.source.attachment.title == _TITLE


def test_a_dataset_row_opens_its_page_and_is_labelled_without_the_word_dataset() -> None:
    source = DatasetSource(
        url=_PORTAL_URL,
        name="World Economic Outlook",
        last_updated="2025-04-30",
        raw_fields={"name": "World Economic Outlook"},
    )
    datasets = ReferencesTableContent(
        title="Datasets",
        columns=_columns(("Dataset", "name")),
        rows=[
            ReferenceRow(
                identifier=_URN, fields=dict(source.raw_fields), target=_dataset_target(source)
            )
        ],
    )

    built = _built(datasets)

    assert '| <cit data-id="row-0"></cit> |' in built.text
    [annotation] = built.annotations
    assert annotation.body.source.attachment.type == DATASET_MIME_TYPE
    assert annotation.body.source.attachment.url == _PORTAL_URL
    assert annotation.body.title == "World Economic Outlook"
    assert annotation.body.source.attachment.title == "World Economic Outlook"
    assert annotation.body.quote is None
    assert annotation.body.selector is None


def test_a_row_without_a_target_stays_text_and_emits_nothing() -> None:
    built = _built(
        _documents(ReferenceRow(identifier="doc 207", fields={"publication_title": _TITLE}))
    )

    assert f"| {_TITLE} |  |" in built.text
    assert "<cit" not in built.text
    assert built.annotations == []


def test_a_document_row_named_by_its_identifier_is_not_shortened() -> None:
    """`doc <id>` is short by construction, and a cut could eat the id."""
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 1234567890",
                fields={},
                target=_document_target(document_id=1234567890),
            )
        ),
        pill_title_max_chars=10,
    )

    [annotation] = built.annotations
    assert annotation.body.title == "doc 1234567890"
    assert annotation.body.source.attachment.title == "doc 1234567890"


def test_a_dataset_row_named_by_its_urn_is_shortened_like_any_name() -> None:
    """A URN has no bounded length, so it obeys the budget as an inline dataset label does."""
    source = DatasetSource(url=_PORTAL_URL)
    datasets = ReferencesTableContent(
        title="Datasets",
        columns=_columns(("Dataset", "name")),
        rows=[ReferenceRow(identifier=_URN, fields={}, target=_dataset_target(source))],
    )

    [annotation] = _built(datasets, pill_title_max_chars=10).annotations

    assert annotation.body.title == _URN
    assert annotation.body.source.attachment.title == "IMF:WEO(1…"


def test_the_pill_budget_shortens_a_row_pill_and_not_its_card() -> None:
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 207",
                fields={"publication_title": _TITLE},
                target=_document_target(),
            )
        ),
        pill_title_max_chars=12,
    )

    [annotation] = built.annotations
    assert annotation.body.source.attachment.title == "Market Outl…"
    assert annotation.body.title == _TITLE


def test_a_row_label_is_not_escaped_for_the_table() -> None:
    """A label is not table text: a reader would see the backslash of an escaped pipe."""
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 207",
                fields={"publication_title": "Trade | Growth\nOutlook"},
                target=_document_target(),
            )
        )
    )

    [annotation] = built.annotations
    assert annotation.body.title == "Trade | Growth Outlook"
    assert annotation.body.source.attachment.title == "Trade | Growth Outlook"
    assert '| <cit data-id="row-0"></cit> |  |' in built.text


def test_row_annotations_are_numbered_from_the_first_index_in_row_order() -> None:
    built = _built(
        _documents(
            ReferenceRow(
                identifier="doc 9",
                fields={"publication_title": "Second"},
                target=_document_target(document_id=9),
            ),
            ReferenceRow(identifier="doc 5", fields={"publication_title": "Not openable"}),
            ReferenceRow(
                identifier="doc 2",
                fields={"publication_title": "First"},
                target=_document_target(document_id=2),
            ),
        ),
        first_index=5,
    )

    assert [annotation.index for annotation in built.annotations] == [5, 6]
    assert [annotation.body.title for annotation in built.annotations] == ["Second", "First"]
    assert [annotation.target.selector.id for annotation in built.annotations] == [
        "row-0",
        "row-1",
    ]


def test_an_openable_section_carries_no_hyperlink() -> None:
    source = DatasetSource(url=_PORTAL_URL, name="World Economic Outlook")
    datasets = ReferencesTableContent(
        title="Datasets",
        columns=_columns(("Dataset", "name")),
        rows=[
            ReferenceRow(
                identifier=_URN,
                fields={"name": "World Economic Outlook"},
                target=_dataset_target(source),
            )
        ],
    )
    documents = _documents(
        ReferenceRow(
            identifier="doc 207", fields={"publication_title": _TITLE}, target=_document_target()
        )
    )

    text = _built(documents, datasets).text

    assert find_hyperlinks(text) == []
    assert _PORTAL_URL not in text
    assert _PDF_URL not in text


# --- the rows the runner builds --------------------------------------------------------------


def test_document_rows_follow_the_cited_order_and_keep_unresolved_ids() -> None:
    rows = document_rows([207, 9], metadata={207: {"publication_title": _TITLE}}, document_urls={})

    assert [row.identifier for row in rows] == ["doc 207", "doc 9"]
    assert rows[0].fields == {"publication_title": _TITLE}
    assert rows[1].fields == {}


def test_a_document_row_opens_its_first_page_when_its_url_is_a_pdf() -> None:
    """A row names the whole document, so it opens where the document begins."""
    rows = document_rows(
        [207, 9, 4],
        metadata={},
        document_urls={207: _PDF_URL, 9: "files/bucket/appdata/deep-research/report.docx"},
    )

    assert rows[0].target == ConvertibleDocumentCitation(document_id=207, page=1, url=_PDF_URL)
    # Not a PDF, and no URL at all: the conditions an inline citation converts on.
    assert rows[1].target is None
    assert rows[2].target is None


def test_dataset_rows_follow_the_cited_order_and_keep_unresolved_urns() -> None:
    source = DatasetSource(
        name="World Economic Outlook", raw_fields={"name": "World Economic Outlook"}
    )
    rows = dataset_rows(_entries(_URN, "ACME:OTHER"), sources={_URN: source})

    assert [row.identifier for row in rows] == [_URN, "ACME:OTHER"]
    assert rows[0].fields == {"name": "World Economic Outlook"}
    assert rows[1].fields == {}


def test_a_dataset_row_opens_only_when_its_record_carries_a_web_url() -> None:
    with_url = DatasetSource(url=_PORTAL_URL)
    without_url = DatasetSource(name="Primary Commodity Prices")
    rows = dataset_rows(
        _entries(_URN, "IMF:PCPS", "ACME:OTHER"), sources={_URN: with_url, "IMF:PCPS": without_url}
    )

    assert rows[0].target == ConvertibleDatasetCitation(
        dataset_id=_URN, url=_PORTAL_URL, source=with_url
    )
    assert rows[1].target is None
    assert rows[2].target is None


def test_a_dataset_row_whose_url_a_browser_cannot_open_stays_text() -> None:
    """A storage-relative path would make the client offer a download rather than a page."""
    source = DatasetSource(
        url="files/bucket/appdata/deep-research/weo.html", name="World Economic Outlook"
    )
    [row] = dataset_rows(_entries(_URN), sources={_URN: source})

    assert row.target is None


# --- datasets cited through data queries ---------------------------------------------------------

_TRADE_URN = "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"


def _query(
    query_id: str, *, urn: str | None, url: str | None = "https://x.example.org/e"
) -> DataQueryRecord:
    meta = {"queryId": query_id, **({"dataExplorerUrl": url} if url else {})}
    content = {"queryId": query_id, **({"datasetUrn": urn} if urn else {})}
    return DataQueryRecord.model_validate({"_meta": meta, "structured_content": content})


def test_a_dataset_cited_only_through_queries_is_listed_once() -> None:
    queries = {
        "dq_0000000001": _query("dq_0000000001", urn=_URN),
        "dq_0000000002": _query("dq_0000000002", urn=_URN),
    }
    text = "One [data_query dq_0000000001]. Two [data_query dq_0000000002]."

    assert cited_dataset_entries(text, data_queries=queries) == _entries(_URN)
    assert cited_dataset_urns(text, data_queries=queries) == [_URN]


def test_a_dataset_cited_both_ways_is_listed_once_at_its_first_citation() -> None:
    queries = {
        "dq_0000000001": _query("dq_0000000001", urn=_URN),
        "dq_0000000002": _query("dq_0000000002", urn=_TRADE_URN),
    }
    text = (
        f"First [dataset {_TRADE_URN}]. Then [data_query dq_0000000001]."
        " Then [data_query dq_0000000002]."
    )

    assert cited_dataset_entries(text, data_queries=queries) == _entries(_TRADE_URN, _URN)


def test_an_uncaptured_id_and_a_query_without_a_link_add_no_row() -> None:
    queries = {"dq_0000000001": _query("dq_0000000001", urn=_URN, url=None)}
    text = "One [data_query dq_0000000001]. Two [data_query dq_ffffffffff]."

    assert cited_dataset_entries(text, data_queries=queries) == []


def test_a_query_without_a_dataset_urn_gets_a_text_row() -> None:
    queries = {"dq_0123abcd45": _query("dq_0123abcd45", urn=None)}
    entries = cited_dataset_entries("A [data_query dq_0123abcd45].", data_queries=queries)
    rows = dataset_rows(entries, sources={})

    assert [(row.identifier, row.fields, row.target) for row in rows] == [
        ("data_query dq_0123abcd45", {}, None)
    ]
    built = _built(
        ReferencesTableContent(
            title="Datasets",
            columns=_columns(("Dataset", "name"), ("Updated", "lastUpdated")),
            rows=rows,
        )
    )
    assert "| data_query dq_0123abcd45 |  |" in built.text
    assert built.annotations == []
