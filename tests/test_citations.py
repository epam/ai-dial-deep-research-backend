"""The shared citation code: what becomes a pill, what stays as text, and what the payload says.

What is protected here: a citation is converted when the condition of the report-citations
capability holds for its kind of source — a document with a PDF URL, a dataset with a page a
browser can open — and a citation that fails it keeps the exact text the report writer wrote.
Everything else — the marker grammar, the run folding, the hyperlink removal and the payload's
shape — exists to make that outcome predictable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from dial_deep_research.app.research.citations import (
    CITATION_TAG_NAME,
    DATASET_MIME_TYPE,
    PDF_MIME_TYPE,
    DatasetSource,
    cited_data_query_ids,
    cited_dataset_ids,
    cited_document_ids,
    convert_citations,
    find_citation_markers,
    find_hyperlinks,
    remove_hyperlinks,
)
from dial_deep_research.app.research.data_queries import DataQueryRecord
from dial_deep_research.app.research.web_urls import is_web_url

_PDF_URL = "files/user-bucket/appdata/deep-research/doc%20101.pdf"
_OTHER_PDF_URL = "files/user-bucket/appdata/deep-research/doc-102.pdf"
_URLS = {101: _PDF_URL, 102: _OTHER_PDF_URL}


def _tag_ids() -> Callable[[], str]:
    """Predictable tag ids, so a test can name the id it expects."""
    ids: Iterator[str] = iter(f"tag-{number}" for number in range(100))
    return lambda: next(ids)


def _tag(tag_id: str) -> str:
    return f'<{CITATION_TAG_NAME} data-id="{tag_id}"></{CITATION_TAG_NAME}>'


def _convert(text: str, urls: dict[int, str] | None = None):
    return convert_citations(
        text, document_urls=_URLS if urls is None else urls, make_tag_id=_tag_ids()
    )


# --- the marker grammar -------------------------------------------------------------------------


def test_the_two_defined_forms_are_markers() -> None:
    markers = find_citation_markers("a [doc 101, page 3] and a [dataset IMF:WEO] here")
    assert [(marker.document_id, marker.page) for marker in markers] == [(101, 3), (None, None)]


def test_the_keyword_is_matched_without_regard_to_case() -> None:
    markers = find_citation_markers("[DOC 101, PAGE 3] and [Dataset IMF:WEO]")
    assert [(marker.document_id, marker.page) for marker in markers] == [(101, 3), (None, None)]


@pytest.mark.parametrize(
    "written",
    [
        pytest.param("[document 101, page 3]", id="lower-case"),
        pytest.param("[Document 101, Page 3]", id="as-a-server-writes-it"),
    ],
)
def test_the_document_keyword_written_out_in_full_is_a_marker(written: str) -> None:
    """A server's own attribution reads this way, and a writer may copy it instead of translating."""
    markers = find_citation_markers(f"A sentence. {written}")
    assert [(marker.document_id, marker.page) for marker in markers] == [(101, 3)]

    converted = _convert(f"A sentence. {written}", urls={101: "files/a/outlook.pdf"})
    assert converted.annotations != []
    assert written not in converted.text


@pytest.mark.parametrize(
    "written",
    [
        pytest.param("[doc 101, pages 3-4]", id="page-range"),
        pytest.param("[doc one hundred, page 3]", id="non-numeric-id"),
        pytest.param("[doc 101]", id="no-page"),
        pytest.param("[doc 101, page 3, page 4]", id="two-pages"),
        pytest.param("[[doc 101, page 3]]", id="nested-bracket"),
        pytest.param("[doc 0, page 3]", id="zero-id"),
        pytest.param("[doc 101, page 0]", id="zero-page"),
    ],
)
def test_a_marker_the_grammar_rejects_is_not_a_citation(written: str) -> None:
    paragraph = f"A sentence. {written}"

    assert [marker for marker in find_citation_markers(paragraph) if marker.document_id] == []
    converted = _convert(paragraph)
    assert converted.text == paragraph
    assert converted.annotations == []
    assert cited_document_ids(paragraph) == []


def test_a_nested_bracket_leaves_the_inner_marker_readable() -> None:
    # The inner text still matches, which is fine: nothing is converted, so the reader keeps
    # exactly what the writer wrote.
    converted = _convert("A sentence. [[doc 101, page 3]]")
    assert converted.text == "A sentence. [[doc 101, page 3]]"


# --- where a citation is converted --------------------------------------------------------------


@pytest.mark.parametrize(
    "draft",
    [
        pytest.param("A cited sentence. [doc 101, page 3]", id="paragraph"),
        pytest.param("- a cited bullet [doc 101, page 3]", id="list-item"),
        pytest.param("1. a cited bullet [doc 101, page 3]", id="ordered-list-item"),
        pytest.param("  - a nested bullet [doc 101, page 3]", id="nested-list-item"),
        pytest.param("| 2.4% | [doc 101, page 3] |", id="table-row"),
        pytest.param("## A heading [doc 101, page 3]", id="atx-heading"),
        pytest.param("A setext heading [doc 101, page 3]\n===", id="setext-heading"),
        pytest.param("> a quoted claim [doc 101, page 3]", id="blockquote"),
        pytest.param("**bold and cited [doc 101, page 3]**", id="emphasis-span"),
        # Markdown parses no raw HTML inside code, so the reader sees the tag as text in these
        # two. Converted all the same: where a marker stands is not a condition of conversion.
        pytest.param("a `span [doc 101, page 3]` here", id="inline-code-span"),
        pytest.param("```\ncode [doc 101, page 3]\n```", id="fenced-code-block"),
    ],
)
def test_a_citation_is_converted_wherever_it_stands(draft: str) -> None:
    converted = _convert(draft)
    assert converted.text == draft.replace("[doc 101, page 3]", _tag("tag-0"))
    assert len(converted.annotations) == 1
    assert converted.markers_left == 0


# --- the URL condition --------------------------------------------------------------------------


def test_a_document_no_url_resolved_for_keeps_its_text() -> None:
    converted = _convert("A cited sentence. [doc 999, page 3]")
    assert converted.text == "A cited sentence. [doc 999, page 3]"
    assert converted.annotations == []


def test_a_document_whose_url_is_not_a_pdf_keeps_its_text() -> None:
    converted = _convert(
        "A cited sentence. [doc 101, page 3]", urls={101: "files/bucket/report.docx"}
    )
    assert converted.text == "A cited sentence. [doc 101, page 3]"
    assert converted.annotations == []


def test_a_dataset_no_record_resolved_for_keeps_its_text() -> None:
    """The caller resolved no datasets at all, which is what the demo and a dataset-less
    channel both do."""
    draft = "…grew by 2.1% [dataset IMF:WEO(1.0.0)] over the period."
    converted = _convert(draft)
    assert converted.text == draft
    assert converted.annotations == []
    assert converted.markers_left == 1
    assert cited_document_ids(draft) == []


# --- which documents a URL is asked for ---------------------------------------------------------


def test_the_requested_ids_are_every_cited_document_in_report_order() -> None:
    draft = (
        "First. [doc 101, page 1]\n\n"
        "Second, the same document. [doc 101, page 2]\n\n"
        "- a bullet [doc 102, page 1]\n\n"
        "| in a table | [doc 103, page 1] |\n\n"
        "## in a heading [doc 104, page 1]\n\n"
        "A dataset [dataset ABC:DEF] and an unresolved document. [doc 999, page 1]"
    )
    # A dataset is not a document and is asked of the catalogue instead. 999 is asked for like
    # the rest: whether a URL comes back is the tool's answer.
    assert cited_document_ids(draft) == [101, 102, 103, 104, 999]


def test_the_requested_urns_are_every_cited_dataset_in_report_order() -> None:
    draft = (
        "First. [dataset IMF:WEO(1.0.0)]\n\n"
        "The same dataset again. [dataset IMF:WEO(1.0.0)]\n\n"
        "- a bullet [dataset IMF:PRIMARY_COMMODITY_PRICES(1.0.0)]\n\n"
        "A document. [doc 101, page 1]"
    )
    assert cited_dataset_ids(draft) == [
        "IMF:WEO(1.0.0)",
        "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)",
    ]


# --- runs ---------------------------------------------------------------------------------------


def test_three_adjacent_citations_become_one_tag_with_the_repeat_counted_once() -> None:
    converted = _convert(
        "…as the outlook notes. [doc 101, page 2], [doc 102, page 2], [doc 101, page 2]"
    )
    assert converted.text == f"…as the outlook notes. {_tag('tag-0')}"
    assert [
        (annotation.index, annotation.target.selector.id, annotation.body.title)
        for annotation in converted.annotations
    ] == [(0, "tag-0", "doc 101, page 2"), (1, "tag-0", "doc 102, page 2")]


def test_space_separated_citations_are_one_run() -> None:
    converted = _convert("A claim. [doc 101, page 1] [doc 101, page 3] [doc 102, page 1]")
    assert converted.text == f"A claim. {_tag('tag-0')}"
    assert len(converted.annotations) == 3
    assert {annotation.target.selector.id for annotation in converted.annotations} == {"tag-0"}


def test_semicolons_also_join_a_run() -> None:
    converted = _convert("A claim. [doc 101, page 1]; [doc 102, page 1]")
    assert converted.text == f"A claim. {_tag('tag-0')}"


@pytest.mark.parametrize(
    "between",
    [
        pytest.param(". Another claim. ", id="a-sentence"),
        pytest.param(" and ", id="a-word"),
        pytest.param("\n", id="a-line-break"),
    ],
)
def test_citations_separated_by_anything_else_are_separate_pills(between: str) -> None:
    converted = _convert(f"[doc 101, page 1]{between}[doc 102, page 1]")
    assert converted.text == f"{_tag('tag-0')}{between}{_tag('tag-1')}"
    assert [annotation.target.selector.id for annotation in converted.annotations] == [
        "tag-0",
        "tag-1",
    ]


def test_a_run_converts_what_it_can_and_keeps_the_rest_as_text() -> None:
    converted = _convert("A claim. [doc 101, page 2], [doc 999, page 3]")
    # The separator went with the markers it joined, so the surviving marker follows the tag
    # single-spaced rather than after a stray comma.
    assert converted.text == f"A claim. {_tag('tag-0')} [doc 999, page 3]"
    assert len(converted.annotations) == 1
    assert converted.markers_left == 1


def test_an_unresolved_dataset_marker_beside_a_document_citation_follows_the_tag() -> None:
    converted = _convert("A claim. [doc 101, page 2], [dataset ABC:DEF]")
    assert converted.text == f"A claim. {_tag('tag-0')} [dataset ABC:DEF]"


def test_a_run_that_converts_nothing_is_left_exactly_as_written() -> None:
    draft = "A claim. [doc 999, page 1], [dataset ABC:DEF]"
    assert _convert(draft).text == draft


def test_the_characters_around_a_run_are_not_the_runs() -> None:
    converted = _convert("(see [doc 101, page 1], [doc 102, page 1]) and so on")
    assert converted.text == f"(see {_tag('tag-0')}) and so on"


# --- tags and annotations pair up ---------------------------------------------------------------


def test_the_same_document_cited_in_several_places_gets_a_tag_each() -> None:
    draft = "First. [doc 101, page 3]\n\nSecond. [doc 101, page 3]\n\n- third [doc 101, page 3]"
    converted = _convert(draft)
    assert [annotation.target.selector.id for annotation in converted.annotations] == [
        "tag-0",
        "tag-1",
        "tag-2",
    ]
    assert converted.text.count(f"<{CITATION_TAG_NAME} ") == 3


def test_indices_are_sequential_and_unique_across_the_array() -> None:
    draft = (
        "A. [doc 101, page 1] [doc 102, page 1]\n\n"
        "B. [doc 101, page 2]\n\n"
        "C. [doc 102, page 2] [doc 101, page 3]"
    )
    converted = _convert(draft)
    assert [annotation.index for annotation in converted.annotations] == [0, 1, 2, 3, 4]


def test_the_payload_of_one_converted_citation() -> None:
    converted = _convert("A cited sentence. [doc 101, page 13]")

    # Dumped the way `send_annotations` dumps it, so a field that does not apply to a document
    # citation is absent from what this compares rather than present as a null.
    assert converted.annotations[0].model_dump(exclude_none=True) == {
        "index": 0,
        "target": {"selector": {"type": "html_tag", "tag": "cit", "id": "tag-0"}},
        "body": {
            "title": "doc 101, page 13",
            "source": {
                "type": "attachment",
                "attachment": {
                    "type": PDF_MIME_TYPE,
                    "url": _PDF_URL,
                    "title": "doc 101, page 13",
                },
            },
            "selector": {"type": "pdf_bbox", "page": 13, "x1": 0, "y1": 0, "x2": 0, "y2": 0},
        },
    }


def test_the_url_is_carried_verbatim_and_the_page_travels_in_the_selector() -> None:
    converted = _convert("A. [doc 101, page 3]\n\nB. [doc 101, page 9]")
    first, second = converted.annotations

    assert first.body.source.attachment.url == second.body.source.attachment.url == _PDF_URL
    assert "#" not in first.body.source.attachment.url
    assert (first.body.selector.page, second.body.selector.page) == (3, 9)


def test_a_document_citation_sends_no_quote() -> None:
    """The app does not hold the cited passage's text, and an empty quote reserves blank space."""
    converted = _convert("A cited sentence. [doc 101, page 3]")
    assert converted.annotations[0].body.quote is None
    assert "quote" not in converted.annotations[0].body.model_dump(exclude_none=True)


def test_a_draft_citing_nothing_is_delivered_unchanged() -> None:
    draft = "A report with no citations at all.\n\n- and a bullet\n"
    converted = _convert(draft)
    assert converted.text == draft
    assert converted.annotations == []
    assert converted.markers_left == 0


def test_tag_ids_are_unique_by_default() -> None:
    converted = convert_citations(
        "A. [doc 101, page 1]\n\nB. [doc 101, page 1]", document_urls=_URLS
    )
    ids = {annotation.target.selector.id for annotation in converted.annotations}
    assert len(ids) == 2
    for tag_id in ids:
        assert converted.text.count(f'data-id="{tag_id}"') == 1


# --- hyperlinks -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("draft", "delivered", "kind"),
    [
        pytest.param(
            "see the [latest outlook](https://example.org/outlook) for more",
            "see the latest outlook for more",
            "link",
            id="markdown-link-keeps-its-label",
        ),
        pytest.param(
            "before ![chart](https://example.org/chart.png) after",
            "before  after",
            "image",
            id="image-is-dropped-whole",
        ),
        pytest.param(
            "published at <https://example.org/outlook>",
            "published at ",
            "autolink",
            id="autolink-is-deleted",
        ),
        pytest.param(
            "published at https://example.org/outlook",
            "published at ",
            "bare_url",
            id="bare-url-is-deleted",
        ),
        pytest.param(
            "see www.example.org/outlook now",
            "see  now",
            "bare_url",
            id="bare-www-url-is-deleted",
        ),
        pytest.param(
            'see <a href="https://example.org">the outlook</a> for more',
            "see the outlook for more",
            "html_anchor",
            id="html-anchor-keeps-its-text",
        ),
        pytest.param(
            'before <img src="https://example.org/c.png" alt="chart"> after',
            "before  after",
            "html_image",
            id="html-image-tag-is-dropped",
        ),
    ],
)
def test_each_hyperlink_form_is_repaired_as_specified(
    draft: str, delivered: str, kind: str
) -> None:
    removal = remove_hyperlinks(draft)
    assert removal.text == delivered
    assert [hyperlink.kind for hyperlink in removal.hyperlinks] == [kind]


def test_a_bare_url_keeps_the_sentences_own_full_stop() -> None:
    assert remove_hyperlinks("published at https://example.org/outlook.").text == ("published at .")


def test_a_reference_style_link_loses_both_bracket_pairs_and_its_definition() -> None:
    draft = "see the [latest outlook][ref] for more\n\n[ref]: https://example.org/outlook\n\nnext"
    removal = remove_hyperlinks(draft)

    assert "https://example.org/outlook" not in removal.text
    assert "see the latest outlook for more" in removal.text
    assert "[ref]" not in removal.text
    assert {hyperlink.kind for hyperlink in removal.hyperlinks} == {
        "reference_link",
        "reference_definition",
    }


def test_a_shortcut_reference_link_is_repaired_only_when_it_is_defined() -> None:
    defined = remove_hyperlinks("see [the outlook] here\n\n[the outlook]: https://example.org")
    assert "see the outlook here" in defined.text

    undefined = remove_hyperlinks("see [the outlook] here")
    assert undefined.text == "see [the outlook] here"
    assert undefined.hyperlinks == []


def test_the_inline_citation_forms_are_not_hyperlinks() -> None:
    draft = "A claim [doc 101, page 3] and a dataset [dataset ABC:DEF]."
    removal = remove_hyperlinks(draft)
    assert removal.text == draft
    assert removal.hyperlinks == []


def test_find_hyperlinks_reports_every_occurrence() -> None:
    draft = (
        "one [a](https://example.org/a), two ![b](https://example.org/b.png), "
        "three https://example.org/c"
    )
    assert [hyperlink.kind for hyperlink in find_hyperlinks(draft)] == [
        "link",
        "image",
        "bare_url",
    ]


def test_nothing_of_a_removed_link_is_kept() -> None:
    removal = remove_hyperlinks("see the [latest outlook](https://example.org/outlook)")
    assert "example.org" not in removal.text
    assert "http" not in removal.text


# --- the two alterations in order ---------------------------------------------------------------


def test_a_link_whose_label_looks_like_a_citation_yields_no_pill() -> None:
    # Link removal runs first, so the citation parser reads the bare label and matches nothing.
    without_links = remove_hyperlinks("see the [doc 101 overview](https://example.org/d)")
    converted = _convert(without_links.text)

    assert converted.text == "see the doc 101 overview"
    assert converted.annotations == []


def test_a_link_whose_label_is_a_marker_loses_its_brackets_and_its_pill() -> None:
    without_links = remove_hyperlinks("as noted [doc 101, page 3](https://example.org/d)")
    converted = _convert(without_links.text)

    assert converted.text == "as noted doc 101, page 3"
    assert converted.annotations == []


def test_a_citation_beside_a_removed_bare_url_is_still_converted() -> None:
    without_links = remove_hyperlinks(
        "A claim. [doc 101, page 3] Published at https://example.org/x"
    )
    converted = _convert(without_links.text)

    assert converted.text == f"A claim. {_tag('tag-0')} Published at "
    assert len(converted.annotations) == 1
    assert without_links.removed == 1


# --- labels -------------------------------------------------------------------------------------


_TITLE = "Market Outlook 2025"


def _convert_titled(text: str, titles: dict[int, str]):
    return convert_citations(
        text, document_urls=_URLS, document_titles=titles, make_tag_id=_tag_ids()
    )


def test_a_titled_document_labels_both_halves_with_its_publication_title() -> None:
    """The client labels the pill from the attachment title and the popup entry from the body."""
    converted = _convert_titled("A claim. [doc 101, page 13]", {101: _TITLE})
    annotation = converted.annotations[0]
    assert annotation.body.title == f"{_TITLE}, page 13"
    assert annotation.body.source.attachment.title == f"{_TITLE}, page 13"


def test_an_untitled_document_is_labelled_from_its_marker() -> None:
    converted = _convert_titled("A claim. [doc 101, page 13]", {})
    annotation = converted.annotations[0]
    assert annotation.body.title == "doc 101, page 13"
    assert annotation.body.source.attachment.title == "doc 101, page 13"
    assert annotation.body.source.attachment.url == _PDF_URL


def test_a_caller_passing_no_titles_at_all_labels_every_citation_from_its_marker() -> None:
    converted = _convert("A claim. [doc 101, page 13]")
    assert converted.annotations[0].body.title == "doc 101, page 13"


def test_a_run_labels_each_source_by_its_own_document() -> None:
    converted = _convert_titled(
        "A claim. [doc 101, page 2] [doc 102, page 4]", {101: "Titled publication"}
    )
    assert [annotation.body.title for annotation in converted.annotations] == [
        "Titled publication, page 2",
        "doc 102, page 4",
    ]


def test_two_pages_of_one_titled_document_differ_only_in_the_page() -> None:
    """A document server attributes at page level, so the popup must tell two pages apart."""
    converted = _convert_titled(
        "A claim. [doc 101, page 4] [doc 101, page 9]", {101: "Titled publication"}
    )
    assert [annotation.body.title for annotation in converted.annotations] == [
        "Titled publication, page 4",
        "Titled publication, page 9",
    ]
    assert {annotation.target.selector.id for annotation in converted.annotations} == {"tag-0"}


_LONG_TITLE = "A publication title long enough not to fit on a narrow pill"


def _convert_with_budget(title: str, budget: int | None):
    return convert_citations(
        "A claim. [doc 101, page 1]",
        document_urls=_URLS,
        document_titles={101: title},
        pill_title_max_chars=budget,
        make_tag_id=_tag_ids(),
    )


def test_a_long_title_is_shortened_on_the_pill_and_whole_on_the_card() -> None:
    """DIAL Chat does not shorten an overflowing label, so the app shortens the pill's copy."""
    body = _convert_with_budget(_LONG_TITLE, 20).annotations[0].body

    assert body.title == f"{_LONG_TITLE}, page 1"
    assert body.source.attachment.title == "A publication title…, page 1"


def test_no_budget_shows_every_title_whole() -> None:
    """For a client with the room, or one that shortens labels itself."""
    body = _convert_with_budget(_LONG_TITLE, None).annotations[0].body
    assert body.title == body.source.attachment.title == f"{_LONG_TITLE}, page 1"


def test_no_budget_is_the_default_for_a_caller_that_names_none() -> None:
    converted = _convert_titled("A claim. [doc 101, page 1]", {101: _LONG_TITLE})
    assert converted.annotations[0].body.source.attachment.title == f"{_LONG_TITLE}, page 1"


def test_a_title_within_the_budget_is_untouched_on_both() -> None:
    body = _convert_with_budget("Market Outlook 2025", 20).annotations[0].body
    assert body.title == body.source.attachment.title == "Market Outlook 2025, page 1"


def test_the_pill_keeps_the_page_however_long_the_title() -> None:
    """The page is appended after the shortening, so a long title never costs the reader it."""
    converted = convert_citations(
        "A claim. [doc 101, page 7]",
        document_urls=_URLS,
        document_titles={101: "x" * 500},
        pill_title_max_chars=20,
        make_tag_id=_tag_ids(),
    )
    assert converted.annotations[0].body.source.attachment.title.endswith(", page 7")


def test_the_pill_budget_is_configurable() -> None:
    body = _convert_with_budget(_LONG_TITLE, 10).annotations[0].body
    assert body.source.attachment.title == "A publica…, page 1"


def test_whitespace_at_the_cut_goes_with_it() -> None:
    """Otherwise the label reads as a gap before the ellipsis."""
    body = _convert_with_budget("Market Outlook 2025 and more", 20).annotations[0].body
    assert body.source.attachment.title == "Market Outlook 2025…, page 1"


def test_an_untitled_citation_is_not_shortened() -> None:
    """The marker label is short by construction, and cutting it would lose the id or the page."""
    converted = convert_citations(
        "A claim. [doc 101, page 1]",
        document_urls=_URLS,
        pill_title_max_chars=4,
        make_tag_id=_tag_ids(),
    )
    body = converted.annotations[0].body
    assert body.title == body.source.attachment.title == "doc 101, page 1"


def test_a_title_for_a_document_that_resolved_no_url_changes_nothing() -> None:
    """No URL means no pill, so the title has nothing to label."""
    converted = convert_citations(
        "A claim. [doc 999, page 1]",
        document_urls={},
        document_titles={999: "Never rendered"},
        make_tag_id=_tag_ids(),
    )
    assert converted.annotations == []
    assert converted.text == "A claim. [doc 999, page 1]"


# --- dataset citations --------------------------------------------------------------------------


_DATASET_ID = "IMF:WEO(1.0.0)"
_DATASET_NAME = "World Economic Outlook"
_DATASET_URL = "https://portal.example.org/datasets/imf-weo"
_LAST_UPDATE = "2025-04-30"
_DATASET = DatasetSource(url=_DATASET_URL, name=_DATASET_NAME, last_updated=_LAST_UPDATE)


def _convert_datasets(
    text: str,
    sources: dict[str, DatasetSource] | None = None,
    *,
    budget: int | None = None,
):
    return convert_citations(
        text,
        document_urls=_URLS,
        dataset_sources={_DATASET_ID: _DATASET} if sources is None else sources,
        pill_title_max_chars=budget,
        make_tag_id=_tag_ids(),
    )


def test_the_payload_of_one_converted_dataset_citation() -> None:
    converted = _convert_datasets(f"…rose by 2.1% [dataset {_DATASET_ID}] over the period.")

    # Dumped the way `send_annotations` dumps it: a dataset citation names no page and carries no
    # quote, so both are absent from the payload rather than present as a null.
    assert converted.annotations[0].model_dump(exclude_none=True) == {
        "index": 0,
        "target": {"selector": {"type": "html_tag", "tag": "cit", "id": "tag-0"}},
        "body": {
            "title": f"{_DATASET_NAME} dataset - last update {_LAST_UPDATE}",
            "source": {
                "type": "attachment",
                "attachment": {
                    "type": DATASET_MIME_TYPE,
                    "url": _DATASET_URL,
                    "title": f"{_DATASET_NAME} dataset",
                },
            },
        },
    }
    assert converted.markers_left == 0


def test_a_cited_dataset_with_a_portal_url_becomes_a_pill() -> None:
    converted = _convert_datasets(f"…rose by 2.1% [dataset {_DATASET_ID}] over the period.")
    assert converted.text == f"…rose by 2.1% {_tag('tag-0')} over the period."


def test_a_dataset_the_catalogue_does_not_report_keeps_its_text() -> None:
    draft = "…fell sharply [dataset IMF:UNKNOWN(1.0.0)] last year."
    converted = _convert_datasets(draft)
    assert converted.text == draft
    assert converted.annotations == []
    assert converted.markers_left == 1


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("files/bucket/catalogue.pdf", id="storage-relative"),
        pytest.param("/datasets/imf-weo", id="site-relative"),
        pytest.param("ftp://portal.example.org/datasets", id="another-scheme"),
        pytest.param("portal.example.org/datasets/imf-weo", id="no-scheme"),
        pytest.param("https://", id="no-host"),
        pytest.param("not a url at all", id="not-a-url"),
    ],
)
def test_a_url_a_browser_cannot_open_keeps_the_marker_text(url: str) -> None:
    """A pill that opens nothing is worse than a marker that at least names its source."""
    draft = f"A claim. [dataset {_DATASET_ID}]"
    converted = _convert_datasets(draft, {_DATASET_ID: DatasetSource(url=url)})
    assert converted.text == draft
    assert converted.annotations == []
    assert is_web_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(_DATASET_URL, id="https"),
        pytest.param("http://portal.example.org/datasets/imf-weo", id="http"),
    ],
)
def test_an_absolute_web_url_is_openable(url: str) -> None:
    assert is_web_url(url) is True


def test_a_versioned_urn_is_matched_exactly() -> None:
    """Two versions of one dataset are two datasets, and the marker names one of them."""
    other = DatasetSource(url="https://portal.example.org/datasets/imf-weo-2", name="Newer")
    converted = _convert_datasets(
        f"A claim. [dataset {_DATASET_ID}]",
        {_DATASET_ID: _DATASET, "IMF:WEO(2.0.0)": other},
    )
    assert converted.annotations[0].body.source.attachment.url == _DATASET_URL


def test_a_urn_differing_only_in_case_is_not_a_match() -> None:
    """The comparison is character for character, as the identifier rule requires."""
    draft = f"A claim. [dataset {_DATASET_ID}]"
    converted = _convert_datasets(draft, {_DATASET_ID.lower(): _DATASET})
    assert converted.text == draft
    assert converted.annotations == []


def test_an_unnamed_dataset_falls_back_to_the_urn_the_marker_carried() -> None:
    converted = _convert_datasets(
        f"A claim. [dataset {_DATASET_ID}]", {_DATASET_ID: DatasetSource(url=_DATASET_URL)}
    )
    annotation = converted.annotations[0]
    assert annotation.body.title == f"{_DATASET_ID} dataset"
    assert annotation.body.source.attachment.title == f"{_DATASET_ID} dataset"


def test_a_named_and_an_unnamed_dataset_produce_the_same_label_shape() -> None:
    """Nothing in a label tells the reader which of the two citations fell back."""
    unnamed_id = "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)"
    converted = _convert_datasets(
        f"One [dataset {_DATASET_ID}]. Two [dataset {unnamed_id}].",
        {
            _DATASET_ID: _DATASET,
            unnamed_id: DatasetSource(url="https://portal.example.org/datasets/pcp"),
        },
    )
    named, unnamed = converted.annotations
    assert named.body.title == f"{_DATASET_NAME} dataset - last update {_LAST_UPDATE}"
    assert unnamed.body.title == f"{unnamed_id} dataset"
    for annotation in converted.annotations:
        assert annotation.body.source.attachment.title.endswith(" dataset")


def test_the_pill_shortens_the_name_and_the_card_keeps_it_whole() -> None:
    converted = _convert_datasets(f"A claim. [dataset {_DATASET_ID}]", budget=20)
    annotation = converted.annotations[0]
    assert annotation.body.source.attachment.title == "World Economic Outl… dataset"
    assert annotation.body.title == f"{_DATASET_NAME} dataset - last update {_LAST_UPDATE}"


def test_the_budget_applies_to_a_urn_too_and_the_word_survives_it() -> None:
    """A URN has no bounded length, so a fallback label is shortened like a name."""
    long_id = "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"
    converted = _convert_datasets(
        f"A claim. [dataset {long_id}]",
        {long_id: DatasetSource(url=_DATASET_URL)},
        budget=20,
    )
    annotation = converted.annotations[0]
    assert annotation.body.source.attachment.title == "IMF:DIRECTION_OF_TR… dataset"
    assert annotation.body.title == f"{long_id} dataset"


def test_no_budget_shows_the_whole_name_on_both() -> None:
    converted = _convert_datasets(f"A claim. [dataset {_DATASET_ID}]", budget=None)
    annotation = converted.annotations[0]
    assert annotation.body.source.attachment.title == f"{_DATASET_NAME} dataset"
    assert annotation.body.title.startswith(f"{_DATASET_NAME} dataset")


def test_no_dataset_label_carries_the_url() -> None:
    converted = _convert_datasets(f"A claim. [dataset {_DATASET_ID}]", budget=20)
    annotation = converted.annotations[0]
    assert _DATASET_URL not in annotation.body.title
    assert _DATASET_URL not in annotation.body.source.attachment.title
    assert "portal.example.org" not in annotation.body.source.attachment.title


def test_a_dataset_with_no_last_update_date_has_no_date_in_its_title() -> None:
    converted = _convert_datasets(
        f"A claim. [dataset {_DATASET_ID}]",
        {_DATASET_ID: DatasetSource(url=_DATASET_URL, name=_DATASET_NAME)},
    )
    body = converted.annotations[0].body
    assert body.title == f"{_DATASET_NAME} dataset"
    assert body.quote is None


def test_the_last_update_date_is_carried_as_the_tool_reported_it() -> None:
    converted = _convert_datasets(
        f"A claim. [dataset {_DATASET_ID}]",
        {
            _DATASET_ID: DatasetSource(
                url=_DATASET_URL, name=_DATASET_NAME, last_updated="30 April 2025"
            )
        },
    )
    body = converted.annotations[0].body
    assert body.title == f"{_DATASET_NAME} dataset - last update 30 April 2025"
    assert body.source.attachment.title == f"{_DATASET_NAME} dataset"
    assert body.quote is None


def test_a_dataset_citation_carries_no_page_selector() -> None:
    converted = _convert_datasets(f"A claim. [dataset {_DATASET_ID}]")
    assert converted.annotations[0].body.selector is None


def test_a_document_and_a_dataset_in_one_run_share_a_pill() -> None:
    converted = _convert_datasets(f"A claim. [doc 101, page 2], [dataset {_DATASET_ID}]")
    assert converted.text == f"A claim. {_tag('tag-0')}"
    assert [
        (annotation.index, annotation.target.selector.id, annotation.body.title)
        for annotation in converted.annotations
    ] == [
        (0, "tag-0", "doc 101, page 2"),
        (1, "tag-0", f"{_DATASET_NAME} dataset - last update {_LAST_UPDATE}"),
    ]
    assert converted.markers_left == 0


def test_one_dataset_cited_twice_in_a_run_is_one_annotation() -> None:
    """A dataset server attributes to the dataset, so there is no finer level to differ at."""
    converted = _convert_datasets(f"A claim. [dataset {_DATASET_ID}], [dataset {_DATASET_ID}]")
    assert converted.text == f"A claim. {_tag('tag-0')}"
    assert len(converted.annotations) == 1


def test_a_dataset_is_converted_wherever_it_stands() -> None:
    converted = _convert_datasets(f"| 2.4% | [dataset {_DATASET_ID}] |")
    assert converted.text == f"| 2.4% | {_tag('tag-0')} |"
    assert len(converted.annotations) == 1


# --- data-query citations -----------------------------------------------------------------------


_QUERY_ID = "dq_0123abcd45"
_EXPLORER_URL = "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE.GDP"


def _query(
    query_id: str = _QUERY_ID,
    *,
    url: str | None = _EXPLORER_URL,
    urn: str | None = _DATASET_ID,
    series_count: int | None = 2,
    filters: list[dict[str, Any]] | None = None,
    period: dict[str, str] | None = None,
    structured: bool = True,
) -> DataQueryRecord:
    meta: dict[str, Any] = {"queryId": query_id}
    if url is not None:
        meta["dataExplorerUrl"] = url
    content: dict[str, Any] = {"queryId": query_id, "filters": filters or []}
    if urn is not None:
        content["datasetUrn"] = urn
    if series_count is not None:
        content["seriesCount"] = series_count
    if period is not None:
        content["requestedPeriod"] = period
    return DataQueryRecord.model_validate(
        {"_meta": meta, "structured_content": content if structured else None}
    )


def _in_filter(dimension: str, *names: str) -> dict[str, Any]:
    return {
        "dimensionId": dimension.upper(),
        "dimensionName": dimension,
        "operator": "in",
        "values": [{"id": name[:2].upper(), "name": name} for name in names],
    }


def _convert_queries(
    text: str,
    queries: dict[str, DataQueryRecord],
    *,
    sources: dict[str, DatasetSource] | None = None,
    budget: int | None = None,
    line_budget: int = 80,
):
    return convert_citations(
        text,
        document_urls=_URLS,
        dataset_sources={_DATASET_ID: _DATASET} if sources is None else sources,
        data_queries=queries,
        pill_title_max_chars=budget,
        filter_line_max_chars=line_budget,
        make_tag_id=_tag_ids(),
    )


def test_a_data_query_marker_is_parsed_with_its_id_verbatim() -> None:
    assert cited_data_query_ids(f"A [data_query {_QUERY_ID}] and [DATA_QUERY  Dq_X ].") == [
        _QUERY_ID,
        "Dq_X",
    ]


def test_a_cited_query_with_an_explorer_link_becomes_a_pill() -> None:
    converted = _convert_queries(
        f"…grew 2.9% in 2023 [data_query {_QUERY_ID}].", {_QUERY_ID: _query()}
    )

    assert converted.text == f"…grew 2.9% in 2023 {_tag('tag-0')}."
    [annotation] = converted.annotations
    attachment = annotation.body.source.attachment
    assert attachment.type == DATASET_MIME_TYPE
    assert attachment.url == _EXPLORER_URL
    assert attachment.title == f"{_DATASET_NAME} dataset"
    assert annotation.body.title == f"{_DATASET_NAME} dataset - last update {_LAST_UPDATE}"
    assert annotation.body.selector is None
    assert converted.markers_left == 0


def test_the_query_id_is_matched_verbatim() -> None:
    draft = "A claim. [data_query DQ_0123ABCD45]"
    converted = _convert_queries(draft, {_QUERY_ID: _query()})
    assert converted.text == draft
    assert converted.annotations == []


def test_a_query_id_the_turn_never_captured_keeps_its_text() -> None:
    draft = "A claim. [data_query dq_ffffffffff]"
    converted = _convert_queries(draft, {_QUERY_ID: _query()})
    assert converted.text == draft
    assert converted.markers_left == 1


def test_a_query_captured_without_a_link_keeps_its_text_and_draws_no_dataset_pill() -> None:
    draft = f"A claim. [data_query {_QUERY_ID}]"
    converted = _convert_queries(draft, {_QUERY_ID: _query(url=None)})
    assert converted.text == draft
    assert converted.annotations == []


def test_a_relative_explorer_link_is_not_convertible() -> None:
    draft = f"A claim. [data_query {_QUERY_ID}]"
    converted = _convert_queries(draft, {_QUERY_ID: _query(url="explorer?urn=IMF:WEO(1.0.0)")})
    assert converted.annotations == []


def test_a_query_that_returned_no_data_but_has_a_link_still_converts() -> None:
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: _query(series_count=None)}
    )
    assert converted.annotations[0].body.source.attachment.url == _EXPLORER_URL


def test_a_query_without_a_dataset_urn_is_labelled_with_its_marker_text() -> None:
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: _query(structured=False)}, budget=10
    )
    body = converted.annotations[0].body
    assert body.title == f"data_query {_QUERY_ID}"
    assert body.source.attachment.title == f"data_query {_QUERY_ID}"
    assert body.quote is None


def test_a_catalogue_without_the_dataset_labels_the_query_by_its_urn() -> None:
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: _query()}, sources={}
    )
    body = converted.annotations[0].body
    assert body.title == f"{_DATASET_ID} dataset"
    assert body.source.attachment.title == f"{_DATASET_ID} dataset"


def test_the_pill_budget_shortens_a_query_pill_before_the_word_dataset() -> None:
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: _query()}, budget=20
    )
    assert converted.annotations[0].body.source.attachment.title == "World Economic Outl… dataset"


def test_a_data_query_pill_never_opens_the_datasets_page() -> None:
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: _query()})
    dumped = converted.annotations[0].model_dump_json()
    assert _DATASET_URL not in dumped


def test_two_queries_of_one_dataset_in_a_run_are_two_entries() -> None:
    queries = {
        "dq_0000000001": _query("dq_0000000001", url=f"{_EXPLORER_URL}&a=1"),
        "dq_0000000002": _query("dq_0000000002", url=f"{_EXPLORER_URL}&a=2"),
    }
    converted = _convert_queries(
        "A claim. [data_query dq_0000000001] [data_query dq_0000000002]", queries
    )
    assert converted.text == f"A claim. {_tag('tag-0')}"
    assert [a.target.selector.id for a in converted.annotations] == ["tag-0", "tag-0"]
    assert [a.body.source.attachment.url for a in converted.annotations] == [
        f"{_EXPLORER_URL}&a=1",
        f"{_EXPLORER_URL}&a=2",
    ]


def test_one_query_cited_twice_in_a_run_is_one_annotation() -> None:
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}], [data_query {_QUERY_ID}]", {_QUERY_ID: _query()}
    )
    assert len(converted.annotations) == 1


def test_a_data_query_card_shows_the_filter_in_words() -> None:
    record = _query(
        filters=[
            _in_filter("Series", "Real GDP growth"),
            _in_filter("Country", "United States", "Germany"),
        ],
        period={"startPeriod": "2020-01-01", "endPeriod": "2024-12-31"},
    )
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    assert converted.annotations[0].body.quote == (
        "* Series: Real GDP growth\n"
        "* Country: United States, Germany\n"
        "* From 2020-01-01 until 2024-12-31"
    )


def test_a_filter_without_names_falls_back_to_the_codes() -> None:
    record = _query(
        filters=[{"dimensionId": "COUNTRY", "operator": "in", "values": [{"id": "DE"}]}]
    )
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    assert converted.annotations[0].body.quote == "* COUNTRY: DE"


def test_a_long_filter_item_is_cut_to_the_default_budget() -> None:
    record = _query(filters=[_in_filter("Country", *(f"Country number {i}" for i in range(35)))])
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    [item] = converted.annotations[0].body.quote.splitlines()
    assert len(item) == 80
    assert item.endswith("…")


def test_a_channels_line_budget_sets_the_item_length() -> None:
    long_item = _in_filter("Country", "United States", "Germany", "France", "Japan", "Brazil")
    short_item = _in_filter("Series", "Real GDP growth")
    record = _query(filters=[long_item, short_item])
    converted = _convert_queries(
        f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record}, line_budget=40
    )
    first, second = converted.annotations[0].body.quote.splitlines()
    assert len(first) == 40
    assert first.endswith("…")
    assert second == "* Series: Real GDP growth"


@pytest.mark.parametrize(
    ("period", "item"),
    [
        pytest.param({"startPeriod": "2020-01-01"}, "* From 2020-01-01", id="start-only"),
        pytest.param({"endPeriod": "2030-01-01"}, "* Until 2030-01-01", id="end-only"),
    ],
)
def test_an_open_ended_period_names_its_one_bound(period: dict[str, str], item: str) -> None:
    record = _query(period=period)
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    assert converted.annotations[0].body.quote == item


def test_a_query_with_no_period_has_no_period_item() -> None:
    record = _query(filters=[_in_filter("Country", "Germany")])
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    assert converted.annotations[0].body.quote == "* Country: Germany"


def test_a_non_set_operator_is_left_out() -> None:
    excluded = {**_in_filter("Country", "Germany"), "operator": "excluded"}
    record = _query(filters=[excluded, _in_filter("Series", "Real GDP growth")])
    converted = _convert_queries(f"A claim. [data_query {_QUERY_ID}]", {_QUERY_ID: record})
    assert converted.annotations[0].body.quote == "* Series: Real GDP growth"


def test_without_captured_queries_every_data_query_marker_stays() -> None:
    draft = f"A claim. [data_query {_QUERY_ID}]"
    converted = convert_citations(draft, document_urls=_URLS)
    assert converted.text == draft
    assert converted.markers_left == 1
