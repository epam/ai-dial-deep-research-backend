"""The shared citation code: what becomes a pill, what stays as text, and what the payload says.

What is protected here: a citation is converted when the condition of the report-citations
capability holds — the document it names has a PDF URL — and a citation that fails it keeps the
exact text the report writer wrote. Everything else — the marker grammar, the run folding, the
hyperlink removal and the payload's shape — exists to make that outcome predictable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from dial_deep_research.app.research.citations import (
    CITATION_TAG_NAME,
    PDF_MIME_TYPE,
    cited_document_ids,
    convert_citations,
    find_citation_markers,
    find_hyperlinks,
    remove_hyperlinks,
)

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
        pytest.param("[doc 101, pages 3-4]", id="page-range"),
        pytest.param("[doc one hundred, page 3]", id="non-numeric-id"),
        pytest.param("[doc 101]", id="no-page"),
        pytest.param("[doc 101, page 3, page 4]", id="two-pages"),
        pytest.param("[[doc 101, page 3]]", id="nested-bracket"),
        pytest.param("[doc 0, page 3]", id="zero-id"),
        pytest.param("[doc 101, page 0]", id="zero-page"),
        pytest.param("[document 101, page 3]", id="other-keyword"),
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


def test_a_dataset_citation_is_never_converted() -> None:
    draft = "…grew by 2.1% [dataset ABC:DEF] over the period."
    converted = _convert(draft)
    assert converted.text == draft
    assert converted.annotations == []
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
    # A dataset is not a document and is never asked for. 999 is asked for like the rest:
    # whether a URL comes back is the tool's answer.
    assert cited_document_ids(draft) == [101, 102, 103, 104, 999]


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


def test_a_dataset_marker_beside_a_document_citation_follows_the_tag() -> None:
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

    assert converted.annotations[0].model_dump() == {
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


def test_no_quote_is_sent() -> None:
    converted = _convert("A cited sentence. [doc 101, page 3]")
    assert "quote" not in converted.annotations[0].body.model_dump()


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
