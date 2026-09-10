"""Turning a delivered report's citation markers into DIAL inline citation annotations.

Pure functions over strings — no DIAL objects, no LangChain, no I/O — so every rule below is
testable without a server, a model or a browser. Two callers share them: the research turn's
delivery step, and the annotations demo completion. A behaviour shown in the demo is therefore
the behaviour a real report gets.

The delivered text is produced by two alterations, in this order:

1. `remove_hyperlinks`, which leaves nothing in the report pointing the reader outward.
2. the citation conversion — `cited_document_ids` over the link-free text, a URL resolved for
   each id it reports, then `convert_citations` — which replaces each convertible marker with a
   marker tag and returns the annotations that claim those tags.

The order is fixed so the outcome is deterministic. It also keeps the marker parser free of any
rule about a bracket followed by `(`: a Markdown link written `[doc 1 overview](url)` reaches the
parser as the bare label `doc 1 overview`, which matches no marker.

A citation becomes a pill when the cited document has a PDF URL the reader can open, and keeps
its marker text when it does not, so the failure mode is a missing pill and never a lost
citation. Where in the Markdown the marker stands is not a condition: the client parses a marker
tag wherever it appears — a paragraph, a list item, a table cell, a heading, a blockquote. The
exception is code, where Markdown parses no raw HTML: a marker inside a fenced block or a code
span becomes a tag the reader sees as text.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel

# The tag written at each converted citation, and the tag name every annotation's selector
# carries. The client rewrites a tag whose id an annotation claims into a pill, and shows a tag
# no annotation claims as text. Note the asymmetry the client's contract fixes: the tag's
# attribute is `data-id`, while the selector's field naming the same value is `id`.
CITATION_TAG_NAME = "cit"

PDF_MIME_TYPE = "application/pdf"

# The two inline citation forms the report is written in (see the research-execution capability).
# The document form takes a positive integer id and a positive integer page, because both halves
# are used: the id is what the file-sharing tool is asked for, and the page is what the reader is
# scrolled to. Anything else in the brackets is left as text — a page range, a non-numeric id, a
# page-less document citation, a nested bracket — because conversion acts only on the defined
# form. This is deliberately stricter than `report_length._CITATION_RE`, which errs the other way:
# matching too much only keeps citation text out of a word count, while matching too much here
# would claim a pill for something that is not a citation.
_DOCUMENT_MARKER = r"\[[ \t]*doc[ \t]+(?P<doc_id>[1-9][0-9]*)[ \t]*,[ \t]*page[ \t]+(?P<page>[1-9][0-9]*)[ \t]*\]"  # noqa: E501
# A dataset id is not an integer — the report writes the id the dataset-query tool reports, such
# as `IMF:WEO`. The id is never read: a dataset is not a file, so a dataset citation is never
# converted. The form is recognized only so that a dataset marker standing beside a document
# citation folds into the same run and its separator goes with the markers it joined.
_DATASET_MARKER = r"\[[ \t]*dataset[ \t]+(?P<dataset_id>[^\[\]\n]+?)[ \t]*\]"
_MARKER_RE = re.compile(f"{_DOCUMENT_MARKER}|{_DATASET_MARKER}", re.IGNORECASE)

# What may stand between two markers of one run, matched in full. No newline: a citation on the
# next line supports a different statement, as does one after a full stop or a word.
_RUN_SEPARATOR_RE = re.compile(r"[ \t,;]*")


class CitationMarker(BaseModel):
    """One citation marker found in report text, and the span it occupies."""

    start: int
    end: int
    text: str
    # A dataset marker carries neither: its id is not read, and it has no page.
    document_id: int | None = None
    page: int | None = None


class HtmlTagSelector(BaseModel):
    """Where the pill goes: the marker tag in the text carrying this `id` as its `data-id`."""

    type: Literal["html_tag"] = "html_tag"
    tag: str
    id: str


class AnnotationTarget(BaseModel):
    selector: HtmlTagSelector


class PdfPageSelector(BaseModel):
    """The cited page, as a zero-size box: it scrolls the viewer to the page and draws nothing."""

    type: Literal["pdf_bbox"] = "pdf_bbox"
    page: int
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0


class AnnotationAttachment(BaseModel):
    """The cited file: its type, the URL the file-sharing step returned, and the pill's label."""

    type: str = PDF_MIME_TYPE
    url: str
    title: str


class AnnotationSource(BaseModel):
    type: Literal["attachment"] = "attachment"
    attachment: AnnotationAttachment


class AnnotationBody(BaseModel):
    """The pill's content. No `quote` field: the app does not hold the cited passage's text, and
    an empty quote reserves blank space in the popup."""

    title: str
    source: AnnotationSource
    selector: PdfPageSelector


class Annotation(BaseModel):
    """One entry of `custom_content.annotations`.

    `index` is required and unique across the array: the client merges streaming deltas by it,
    and two annotations sharing one tag id with no index are treated as a single source.
    """

    index: int
    target: AnnotationTarget
    body: AnnotationBody


class _ConvertibleCitation(BaseModel):
    """A citation the condition holds for: the document and page it names, and its PDF URL."""

    document_id: int
    page: int
    url: str


class CitationConversion(BaseModel):
    """What the conversion produced: the delivered text, its annotations, and what it counted."""

    text: str
    annotations: list[Annotation]
    # Citation markers still standing in `text`, in whatever form the writer wrote them —
    # dataset markers, and markers whose document resolved no PDF URL.
    markers_left: int


class Hyperlink(BaseModel):
    """One hyperlink found in a draft: what kind it is, and the text it was written as."""

    kind: Literal[
        "link",
        "image",
        "reference_link",
        "reference_definition",
        "html_anchor",
        "html_image",
        "autolink",
        "bare_url",
    ]
    text: str


class HyperlinkRemoval(BaseModel):
    """The link-free text, and every hyperlink taken out of it."""

    text: str
    hyperlinks: list[Hyperlink]

    @property
    def removed(self) -> int:
        return len(self.hyperlinks)


def find_citation_markers(text: str) -> list[CitationMarker]:
    """Every citation marker in the text, in the order it appears."""
    markers: list[CitationMarker] = []
    for match in _MARKER_RE.finditer(text):
        if _sits_in_another_bracket(text, match):
            continue
        doc_id = match.group("doc_id")
        markers.append(
            CitationMarker(
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                document_id=int(doc_id) if doc_id is not None else None,
                page=int(match.group("page")) if doc_id is not None else None,
            )
        )
    return markers


def _sits_in_another_bracket(text: str, match: re.Match[str]) -> bool:
    """Whether a bracket pair of someone else's markup encloses this marker.

    The marker pattern already refuses a bracket inside the marker; this refuses one around it,
    so `[[doc 101, page 3]]` keeps its text rather than delivering a pill between two stray
    brackets. Two markers written back to back are unaffected: what stands next to each of them
    is the other's bracket of the opposite kind.
    """
    before = text[match.start() - 1] if match.start() > 0 else ""
    after = text[match.end()] if match.end() < len(text) else ""
    return before == "[" or after == "]"


def cited_document_ids(text: str) -> list[int]:
    """The distinct document ids the text cites, in report order.

    Every one of them is asked for a URL: a citation becomes a pill wherever it stands, so no
    document is cited only in places that cannot carry one.
    """
    ids: list[int] = []
    for marker in find_citation_markers(text):
        if marker.document_id is None or marker.document_id in ids:
            continue
        ids.append(marker.document_id)
    return ids


def convert_citations(
    text: str,
    *,
    document_urls: Mapping[int, str],
    make_tag_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> CitationConversion:
    """Replace every convertible citation with its marker tag, and build the annotations.

    Args:
        text: the settled draft, with its hyperlinks already removed.
        document_urls: the DIAL file URL of each document a URL was obtained for, by document id.
            An id that is absent, or whose URL is not a PDF, keeps its citations as text.
        make_tag_id: source of tag ids. Injectable so a test can read the ids it expects; the
            default is opaque and unique per tag.
    """
    markers = find_citation_markers(text)

    pieces: list[str] = []
    annotations: list[Annotation] = []
    markers_left = 0
    cursor = 0

    for run in _group_into_runs(markers, text=text):
        convertible: list[_ConvertibleCitation] = []
        kept_as_text: list[CitationMarker] = []
        for marker in run:
            citation = _convertible_citation(marker, document_urls=document_urls)
            if citation is None:
                kept_as_text.append(marker)
            else:
                convertible.append(citation)

        if not convertible:
            # Nothing folds here, so the run's own text — separators included — is left alone.
            markers_left += len(run)
            continue

        pieces.append(text[cursor : run[0].start])
        tag_id = make_tag_id()
        pieces.append(f'<{CITATION_TAG_NAME} data-id="{tag_id}"></{CITATION_TAG_NAME}>')

        # Two markers naming the same document and page are one source cited once.
        sources_seen: set[tuple[int, int]] = set()
        for citation in convertible:
            source = (citation.document_id, citation.page)
            if source in sources_seen:
                continue
            sources_seen.add(source)
            annotations.append(
                _build_annotation(index=len(annotations), tag_id=tag_id, citation=citation)
            )

        # The separators inside the run went with the markers they joined, so each surviving
        # marker follows the tag single-spaced, in the order it was written.
        for marker in kept_as_text:
            pieces.append(f" {marker.text}")
        markers_left += len(kept_as_text)
        cursor = run[-1].end

    pieces.append(text[cursor:])
    return CitationConversion(
        text="".join(pieces), annotations=annotations, markers_left=markers_left
    )


def remove_hyperlinks(text: str) -> HyperlinkRemoval:
    """Leave nothing in the text pointing the reader outward.

    Each form is repaired as the **report-composition** capability states: a Markdown link keeps
    its label, an image is dropped whole, a reference-style link keeps its label and loses its
    definition line, a raw HTML anchor keeps its text, a raw HTML image tag is dropped, and an
    autolink or bare URL — which has no label to keep — is deleted.

    The repair stops at removal. It does not interpret a link, does not match its target against
    anything, keeps the URL nowhere, and does not rewrite the prose around the removal, which may
    therefore read worse for the loss.
    """
    found: list[Hyperlink] = []
    without_references = _remove_reference_links(text, found=found)
    return HyperlinkRemoval(
        text=_remove_inline_hyperlinks(without_references, found=found), hyperlinks=found
    )


def find_hyperlinks(text: str) -> list[Hyperlink]:
    """Every hyperlink in the text — the one definition the report rule and the delivery share."""
    return remove_hyperlinks(text).hyperlinks


def log_citations_resolved(
    log: logging.Logger,
    *,
    documents_requested: int,
    documents_resolved: int,
    annotations: int,
    markers_left: int,
    hyperlinks_removed: int,
    duration_seconds: float,
) -> None:
    """Emit the citation-step event (8c) of the logging-policy INFO skeleton.

    One renderer for every caller, so the event's shape cannot drift between the research turn
    and the demo. Counts only: no URL, no file name, no document id and no report text.
    """
    log.info(
        "Report citations resolved: documents_requested=%d documents_resolved=%d annotations=%d"
        " markers_left=%d hyperlinks_removed=%d duration=%.1fs",
        documents_requested,
        documents_resolved,
        annotations,
        markers_left,
        hyperlinks_removed,
        duration_seconds,
    )


def _build_annotation(*, index: int, tag_id: str, citation: _ConvertibleCitation) -> Annotation:
    """One annotation for one converted citation.

    Both labels read `doc <id>, page <ix>` — the text the marker carried — because the app holds
    no document title. The file name inside the URL is a storage path segment rather than a
    title, so no label is derived from the URL and no part of it is decoded. The client labels
    the pill from the attachment title and the popup entry from the body title.
    """
    label = f"doc {citation.document_id}, page {citation.page}"
    return Annotation(
        index=index,
        target=AnnotationTarget(selector=HtmlTagSelector(tag=CITATION_TAG_NAME, id=tag_id)),
        body=AnnotationBody(
            title=label,
            source=AnnotationSource(attachment=AnnotationAttachment(url=citation.url, title=label)),
            selector=PdfPageSelector(page=citation.page),
        ),
    )


def _convertible_citation(
    marker: CitationMarker, *, document_urls: Mapping[int, str]
) -> _ConvertibleCitation | None:
    """This citation's document, page and URL, or None when it cannot become a pill.

    One condition, decided here: the marker names a document and a page, and that document has a
    PDF URL. A dataset marker fails it because it names no page, and so does a document no URL
    resolved for.
    """
    if marker.document_id is None or marker.page is None:
        return None
    url = document_urls.get(marker.document_id)
    if url is None or not is_pdf_url(url):
        return None
    return _ConvertibleCitation(document_id=marker.document_id, page=marker.page, url=url)


def is_pdf_url(url: str) -> bool:
    """Whether the URL's own path names a PDF.

    Public because a caller resolving URLs has to refuse one this would reject, rather than hand
    over a URL whose citations then quietly keep their marker text.

    The file-sharing contract returns a URL and nothing else, so the extension is what the app
    has to go on. A PDF stored under another extension is treated as a non-PDF and keeps its
    marker, which is the conservative direction: the alternative is a pill that opens nothing.
    """
    path = url.split("#", 1)[0].split("?", 1)[0]
    return path.lower().endswith(".pdf")


def _group_into_runs(markers: Sequence[CitationMarker], *, text: str) -> list[list[CitationMarker]]:
    """Group markers separated only by spaces, commas or semicolons into one run each."""
    runs: list[list[CitationMarker]] = []
    for marker in markers:
        if runs and _RUN_SEPARATOR_RE.fullmatch(text[runs[-1][-1].end : marker.start]):
            runs[-1].append(marker)
        else:
            runs.append([marker])
    return runs


# A Markdown image, a Markdown link, a raw HTML image tag, a raw HTML anchor, an autolink and a
# bare URL, in the order they must be tried: the image alternative before the link one it
# contains, and both HTML forms and the autolink before the bare URL inside them.
_INLINE_HYPERLINK_RE = re.compile(
    r"""
      (?P<image>!\[[^\]]*\]\([^)]*\))
    | (?P<link>\[(?P<link_label>[^\]]*)\]\([^)]*\))
    | (?P<html_image><img\b[^>]*>)
    | (?P<html_anchor><a\b[^>]*>(?P<anchor_text>.*?)</a\s*>)
    | (?P<autolink><[a-z][a-z0-9+.-]*:[^>\s]*>)
    | (?P<bare_url>(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>()\[\]"']+)
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# `[ref]: url "title"` on its own line — the definition half of a reference-style link. The
# trailing newline belongs to the match, so deleting a definition takes its whole line.
_REFERENCE_DEFINITION_RE = re.compile(
    r"^ {0,3}\[(?P<label>[^\]\n]+)\]:[ \t]*\S+.*(?:\n|$)", re.MULTILINE
)

# The full (`[label][ref]`), collapsed (`[label][]`) and shortcut (`[label]`) reference forms,
# and the image (`![label][ref]`) each of them also has.
_REFERENCE_LINK_RE = re.compile(
    r"(?P<bang>!?)\[(?P<label>[^\]\n]+)\](?:\[(?P<reference>[^\]\n]*)\])?"
)

# Trailing sentence punctuation is the sentence's, not the URL's.
_URL_TRAILING_PUNCTUATION = ".,;:!?"


def _remove_reference_links(text: str, *, found: list[Hyperlink]) -> str:
    """Repair reference-style links, then delete the definition lines they pointed at.

    A bracketed token is a reference-style link only when a matching definition exists, which is
    what keeps an inline citation marker from ever being read as one.
    """
    definitions = {
        match.group("label").strip().casefold() for match in _REFERENCE_DEFINITION_RE.finditer(text)
    }
    if not definitions:
        return text

    def drop_definition(match: re.Match[str]) -> str:
        found.append(Hyperlink(kind="reference_definition", text=match.group(0).rstrip("\n")))
        return ""

    # The definitions go first, whole line included, so that a definition's own `[ref]:` is never
    # read as a link to repair. One that no link points at goes too: it is a URL written as
    # markup that renders as nothing.
    without_definitions = _REFERENCE_DEFINITION_RE.sub(drop_definition, text)

    def repair(match: re.Match[str]) -> str:
        label = match.group("label")
        reference = match.group("reference")
        wanted = (reference if reference else label).strip().casefold()
        if wanted not in definitions:
            return match.group(0)
        if match.group("bang"):
            found.append(Hyperlink(kind="image", text=match.group(0)))
            return ""
        found.append(Hyperlink(kind="reference_link", text=match.group(0)))
        return label

    return _REFERENCE_LINK_RE.sub(repair, without_definitions)


def _remove_inline_hyperlinks(text: str, *, found: list[Hyperlink]) -> str:
    def repair(match: re.Match[str]) -> str:
        if match.group("image") is not None:
            found.append(Hyperlink(kind="image", text=match.group(0)))
            return ""
        if match.group("link") is not None:
            found.append(Hyperlink(kind="link", text=match.group(0)))
            return match.group("link_label")
        if match.group("html_image") is not None:
            found.append(Hyperlink(kind="html_image", text=match.group(0)))
            return ""
        if match.group("html_anchor") is not None:
            found.append(Hyperlink(kind="html_anchor", text=match.group(0)))
            return match.group("anchor_text")
        if match.group("autolink") is not None:
            found.append(Hyperlink(kind="autolink", text=match.group(0)))
            return ""
        url = match.group("bare_url").rstrip(_URL_TRAILING_PUNCTUATION)
        found.append(Hyperlink(kind="bare_url", text=url))
        return match.group(0)[len(url) :]

    return _INLINE_HYPERLINK_RE.sub(repair, text)
