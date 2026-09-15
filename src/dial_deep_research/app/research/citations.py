"""Turning a delivered report's citation markers into DIAL inline citation annotations.

Pure functions over strings — no DIAL objects, no LangChain, no I/O — so every rule below is
testable without a server, a model or a browser. Two callers share them: the research turn's
delivery step, and the annotations demo completion. A behaviour shown in the demo is therefore
the behaviour a real report gets.

The delivered text is produced by three alterations, in this order:

1. `remove_hyperlinks`, which leaves nothing in the report pointing the reader outward.
2. the citation conversion — `cited_document_ids` and `cited_dataset_ids` over the link-free
   text, the documents' URLs and titles and the datasets' catalogue records resolved for what
   they report, then `convert_citations` — which replaces each convertible marker with a marker
   tag and returns the annotations that claim those tags.
3. the References section, built by `references.py` from the same resolved metadata and appended
   to the converted text. This module knows nothing about it beyond the order.

A citation's labels are a leading part naming the source and a fixed trailing part saying what
kind of source it is: `<publication title>, page <ix>` for a document, `<dataset name> dataset`
for a dataset. A lookup that resolved nothing changes only the leading part — `doc <id>` for a
document, the dataset's URN for a dataset — so the cost of missing metadata is a plainer pill
rather than a missing one, and no label tells the reader which citations fell back.

The order is fixed so the outcome is deterministic. It also keeps the marker parser free of any
rule about a bracket followed by `(`: a Markdown link written `[doc 1 overview](url)` reaches the
parser as the bare label `doc 1 overview`, which matches no marker.

Each kind of citation becomes a pill on its own condition — a document when it has a PDF URL the
reader can open, a dataset when the catalogue reported a page a browser can open — and keeps its
marker text when the condition fails, so the failure mode is a missing pill and never a lost
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
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

# The tag written at each converted citation, and the tag name every annotation's selector
# carries. The client rewrites a tag whose id an annotation claims into a pill, and shows a tag
# no annotation claims as text. Note the asymmetry the client's contract fixes: the tag's
# attribute is `data-id`, while the selector's field naming the same value is `id`.
CITATION_TAG_NAME = "cit"

PDF_MIME_TYPE = "application/pdf"

# What a dataset citation's source is: a page on the web rather than a file. The client branches
# on this string twice — it routes only `application/pdf` into its document viewer, and it offers
# the open-in-browser action, the one action that reaches a page, only for an HTML type.
DATASET_MIME_TYPE = "text/html"

# What marks a title the pill shows only part of. One character, so it costs the caller's
# budget as little as possible.
_ELLIPSIS = "…"

# The schemes a citation pill may open. A dataset citation's URL is followed by the client in a
# new browser tab, so it has to be one the browser can resolve on its own.
_WEB_URL_SCHEMES = ("http", "https")

# The word every dataset label ends with. A dataset's name is often a bare noun phrase that says
# nothing about what kind of source it is, and a URN says less still.
_DATASET_LABEL_SUFFIX = " dataset"

# The two inline citation forms the report is written in (see the research-execution capability).
# The document form takes a positive integer id and a positive integer page, because both halves
# are used: the id is what the file-sharing tool is asked for, and the page is what the reader is
# scrolled to. Anything else in the brackets is left as text — a page range, a non-numeric id, a
# page-less document citation, a nested bracket — because conversion acts only on the defined
# form. This is deliberately stricter than `report_length._CITATION_RE`, which errs the other way:
# matching too much only keeps citation text out of a word count, while matching too much here
# would claim a pill for something that is not a citation.
# `document` is accepted beside `doc` as a guard against one predictable mistake, not as a second
# report format: a retrieval server's own attribution may read `[Document 12, Page 1]`, which is
# close enough to the report's form that the writer may copy it through instead of translating it.
# Rejecting the copy would cost that citation its pill silently.
_DOCUMENT_MARKER = r"\[[ \t]*doc(?:ument)?[ \t]+(?P<doc_id>[1-9][0-9]*)[ \t]*,[ \t]*page[ \t]+(?P<page>[1-9][0-9]*)[ \t]*\]"  # noqa: E501
# A dataset id is not an integer but a URN, the string the dataset server reports for that
# dataset — such as `IMF:WEO(1.0.0)`. Every character of it is part of the identifier, so the
# pattern accepts anything but a bracket or a newline and the colon and parenthesised version
# survive parsing unchanged. The id is matched against the catalogue verbatim (see
# **source-attribution**), which is why nothing here trims, folds or decodes it.
_DATASET_MARKER = r"\[[ \t]*dataset[ \t]+(?P<dataset_id>[^\[\]\n]+?)[ \t]*\]"
_MARKER_RE = re.compile(f"{_DOCUMENT_MARKER}|{_DATASET_MARKER}", re.IGNORECASE)

# What may stand between two markers of one run, matched in full. No newline: a citation on the
# next line supports a different statement, as does one after a full stop or a word.
_RUN_SEPARATOR_RE = re.compile(r"[ \t,;]*")


class CitationMarker(BaseModel):
    """One citation marker found in report text, and the span it occupies.

    Which pair of fields is filled says which form the marker was written in: a document marker
    carries the document id and the cited page, a dataset marker carries the URN alone — a
    dataset citation names no location inside what it cites.
    """

    start: int
    end: int
    text: str
    document_id: int | None = None
    page: int | None = None
    dataset_id: str | None = None


class DatasetSource(BaseModel):
    """What the catalogue reported about one cited dataset.

    The pill's three fields travel together because they arrive together, in one record of one
    answer: a URL without the name it belongs to could label a pill with the wrong dataset. Each
    of the three is optional, and each absence costs one thing: `url` is what makes the citation
    convertible, so a record without one is cited as text and still listed in the report's
    References section; a record with no usable name is labelled from the URN; one with no date
    carries one fewer fact on its card. `raw_fields` is that same record unread, which a
    References row needs and a pill never looks at.
    """

    model_config = ConfigDict(frozen=True)

    # `None` where the catalogue reported no URL, and where it reported one a browser cannot open:
    # an unusable URL is normalized away at the boundary, so a record read from a catalogue never
    # carries a URL the client could not follow.
    url: str | None = None
    name: str | None = None
    # Carried exactly as the tool reported it — the app is not the authority on what a server's
    # value means, so it is neither reformatted nor rendered as a relative phrase.
    last_updated: str | None = None
    # The record as the catalogue reported it, whole and unvalidated, which is what a References
    # row reads its configured columns out of: those columns are configured per channel, so a cell
    # may read a key this model does not name. The three fields above are the pill's own view of
    # the same record — named by the contract, and normalized where the pill needs them to be,
    # which the raw record is not, so the two can report the same fact differently.
    raw_fields: dict[str, Any] = Field(default_factory=dict)


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
    """What the citation opens: its media type, its address, and the label the pill shows.

    The type is stated per citation rather than defaulted, because it is what the client
    branches on: `application/pdf` for a cited document, whose URL is the file the file-sharing
    tool shared, and `text/html` for a cited dataset, whose URL is a page on the web.
    """

    type: str
    url: str
    title: str


class AnnotationSource(BaseModel):
    type: Literal["attachment"] = "attachment"
    attachment: AnnotationAttachment


class AnnotationBody(BaseModel):
    """The pill's content: its popup label, the source it opens, and what it says about it.

    Both optional fields are absent on exactly one kind of citation, and `send_annotations`
    dumps the payload with `exclude_none=True` so an absent field never travels as an explicit
    null. Any later field that is meaningfully null on the wire has to revisit that dump.

    A document citation carries `selector` and no `quote`: the page is what a reader is scrolled
    to, and the app does not hold the cited passage's text. A dataset citation carries `quote`
    and no `selector`: it names no location inside what it cites, and the field the client
    reserves for a passage is where its identity and currency go instead.
    """

    title: str
    source: AnnotationSource
    selector: PdfPageSelector | None = None
    quote: str | None = None


class Annotation(BaseModel):
    """One entry of `custom_content.annotations`.

    `index` is required and unique across the array: the client merges streaming deltas by it,
    and two annotations sharing one tag id with no index are treated as a single source.
    """

    index: int
    target: AnnotationTarget
    body: AnnotationBody


class _ConvertibleDocumentCitation(BaseModel):
    """A document citation its condition holds for: the document and page it names, and the URL."""

    document_id: int
    page: int
    url: str

    @property
    def source_key(self) -> tuple[str, ...]:
        """What makes this one source. A document server attributes per page, so the page is
        part of the identity: two pages of one publication are two sources."""
        return ("document", str(self.document_id), str(self.page))


class _ConvertibleDatasetCitation(BaseModel):
    """A dataset citation its condition holds for: the URN it names, and what the catalogue said.

    `url` is carried beside the record rather than read back out of it, because being convertible
    is exactly having one: the record's own `url` is optional, and this one is not.
    """

    dataset_id: str
    url: str
    source: DatasetSource

    @property
    def source_key(self) -> tuple[str, ...]:
        """What makes this one source. A dataset server attributes to the dataset, and there is
        no finer level for two citations of it to differ at."""
        return ("dataset", self.dataset_id)


# One citation the conversion will emit an annotation for. A pair of models rather than one
# widened model: the two kinds share no field beyond the URL buried in each, and half the fields
# of a merged model would be `None` in every instance.
_ConvertibleCitation = _ConvertibleDocumentCitation | _ConvertibleDatasetCitation


class CitationConversion(BaseModel):
    """What the conversion produced: the delivered text, its annotations, and what it counted."""

    text: str
    annotations: list[Annotation]
    # Citation markers still standing in `text`, in whatever form the writer wrote them — the
    # ones whose document resolved no PDF URL, and whose dataset resolved no page URL.
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
                # Taken exactly as written: the URN is matched against the catalogue verbatim.
                dataset_id=match.group("dataset_id"),
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


def cited_dataset_ids(text: str) -> list[str]:
    """The distinct dataset URNs the text cites, in report order.

    Each is carried exactly as the report writer wrote it, because it is compared to the
    catalogue's own ids character for character.
    """
    ids: list[str] = []
    for marker in find_citation_markers(text):
        if marker.dataset_id is None or marker.dataset_id in ids:
            continue
        ids.append(marker.dataset_id)
    return ids


def convert_citations(
    text: str,
    *,
    document_urls: Mapping[int, str],
    document_titles: Mapping[int, str] | None = None,
    dataset_sources: Mapping[str, DatasetSource] | None = None,
    pill_title_max_chars: int | None = None,
    make_tag_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> CitationConversion:
    """Replace every convertible citation with its marker tag, and build the annotations.

    Args:
        text: the settled draft, with its hyperlinks already removed.
        document_urls: the DIAL file URL of each document a URL was obtained for, by document id.
            An id that is absent, or whose URL is not a PDF, keeps its citations as text.
        document_titles: the publication title of each document one was obtained for, by document
            id. An absent id is labelled from its marker instead; a caller that resolves no
            titles at all passes nothing and every label reads as the marker did.
        dataset_sources: what the catalogue reported about each cited dataset, by URN. A URN that
            is absent, or whose URL is not one a browser can open, keeps its citations as text; a
            caller resolving no datasets at all passes nothing and every dataset marker stays.
        pill_title_max_chars: how much of a label's leading part the pill shows, the ellipsis
            counted within it. `None` shows it whole. The popup card carries the leading part
            whole either way.
        make_tag_id: source of tag ids. Injectable so a test can read the ids it expects; the
            default is opaque and unique per tag.
    """
    titles = document_titles or {}
    datasets = dataset_sources or {}
    markers = find_citation_markers(text)

    pieces: list[str] = []
    annotations: list[Annotation] = []
    markers_left = 0
    cursor = 0

    for run in _group_into_runs(markers, text=text):
        convertible: list[_ConvertibleCitation] = []
        kept_as_text: list[CitationMarker] = []
        for marker in run:
            citation = _convertible_citation(
                marker, document_urls=document_urls, dataset_sources=datasets
            )
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

        # Two markers naming the same source are one source cited once.
        sources_seen: set[tuple[str, ...]] = set()
        for citation in convertible:
            if citation.source_key in sources_seen:
                continue
            sources_seen.add(citation.source_key)
            annotations.append(
                _build_annotation(
                    index=len(annotations),
                    tag_id=tag_id,
                    citation=citation,
                    document_titles=titles,
                    pill_title_max_chars=pill_title_max_chars,
                )
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
    documents_titled: int,
    datasets_requested: int,
    datasets_resolved: int,
    annotations: int,
    markers_left: int,
    hyperlinks_removed: int,
    duration_seconds: float,
) -> None:
    """Emit the citation-step event (8c) of the logging-policy INFO skeleton.

    One renderer for every caller, so the event's shape cannot drift between the research turn
    and the demo. Counts only: no URL, no file name, no id of a cited document or dataset, no
    document title, no dataset name and no report text.

    `documents_titled` is bounded by `documents_resolved` rather than by `documents_requested`,
    even though the metadata resource is asked about every cited document: a title is counted
    only where a URL came back, because only those citations become pills and a title on no pill
    was never shown. The two being equal is the ordinary case; a gap between them is how a
    channel with incomplete metadata reads, and it is the only record a document without a title
    gets.

    `datasets_resolved` counts the cited datasets the catalogue reported a usable page URL for.
    The gap to `datasets_requested` is likewise the whole record of a dataset that has no portal
    page, which is the channel's own data rather than a fault and warns about nothing.
    """
    log.info(
        "Report citations resolved: documents_requested=%d documents_resolved=%d"
        " documents_titled=%d datasets_requested=%d datasets_resolved=%d annotations=%d"
        " markers_left=%d hyperlinks_removed=%d duration=%.1fs",
        documents_requested,
        documents_resolved,
        documents_titled,
        datasets_requested,
        datasets_resolved,
        annotations,
        markers_left,
        hyperlinks_removed,
        duration_seconds,
    )


def _shorten_for_pill(leading: str, max_chars: int | None) -> str:
    """A label's leading part as the pill shows it: `max_chars` at most, the ellipsis within it.

    `None` returns it unchanged, for a caller whose client has room for it or which shortens
    labels itself. What follows the leading part is appended by the caller, after this, so no
    budget can cost a label its cited page or the word saying what kind of source it names.

    Whitespace left at the cut goes with it, so a name broken at a space does not read as a gap
    before the ellipsis. The cut is by character rather than at a word boundary: a budget this
    small would often leave one word, and a ragged edge costs the reader less than a label whose
    length swings with where the spaces happen to fall.
    """
    if max_chars is None or len(leading) <= max_chars:
        return leading
    return leading[: max_chars - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


def _build_annotation(
    *,
    index: int,
    tag_id: str,
    citation: _ConvertibleCitation,
    document_titles: Mapping[int, str],
    pill_title_max_chars: int | None,
) -> Annotation:
    """One annotation for one converted citation, whichever kind of source it names.

    The client labels the pill from the attachment title and the popup entry from the body
    title, and the two differ only in how much of the leading part they carry: the pill's copy is
    shortened to `pill_title_max_chars`, the card's is whole. What follows the leading part — a
    document's cited page, a dataset's `dataset` — is appended after the shortening, so a long
    name never costs the reader the part that says what the label names.

    No label is derived from a URL and no part of one is decoded: the file name inside a shared
    URL is a storage path segment and the last segment of a portal URL is a slug, neither of them
    a name the reader should be shown.
    """
    body = (
        _document_body(citation, document_titles=document_titles, pill_chars=pill_title_max_chars)
        if isinstance(citation, _ConvertibleDocumentCitation)
        else _dataset_body(citation, pill_chars=pill_title_max_chars)
    )
    return Annotation(
        index=index,
        target=AnnotationTarget(selector=HtmlTagSelector(tag=CITATION_TAG_NAME, id=tag_id)),
        body=body,
    )


def _document_body(
    citation: _ConvertibleDocumentCitation,
    *,
    document_titles: Mapping[int, str],
    pill_chars: int | None,
) -> AnnotationBody:
    """A cited document's popup entry: its publication title and the page, and the file to open.

    The page belongs in both labels, because a document server attributes at page level: two
    pages of one publication are two sources, and a run folding them behind one pill must still
    read as two entries in its popup. A document no title resolved for reads `doc <id>, page
    <ix>` in both — the text the marker carried, and the one label that is not shortened, because
    it is short by construction and the smallest configurable budget could eat the id.
    """
    title = document_titles.get(citation.document_id)
    leading = title if title else f"doc {citation.document_id}"
    trailing = f", page {citation.page}"
    pill_leading = _shorten_for_pill(leading, pill_chars) if title else leading
    return AnnotationBody(
        title=f"{leading}{trailing}",
        source=AnnotationSource(
            attachment=AnnotationAttachment(
                type=PDF_MIME_TYPE, url=citation.url, title=f"{pill_leading}{trailing}"
            )
        ),
        selector=PdfPageSelector(page=citation.page),
    )


def _dataset_body(
    citation: _ConvertibleDatasetCitation, *, pill_chars: int | None
) -> AnnotationBody:
    """A cited dataset's popup entry: its name and the page to open in a browser.

    The leading part is the catalogue's name for the dataset, or the URN the marker carried when
    it reported none — the same shape either way, so nothing in the label says which. The URL is
    carried verbatim and appears in no label: the reader reaches it through the card's
    open-in-browser action, which is the client's own path and the only one there is.
    """
    source = citation.source
    leading = source.name if source.name else citation.dataset_id
    return AnnotationBody(
        title=f"{leading}{_DATASET_LABEL_SUFFIX}",
        source=AnnotationSource(
            attachment=AnnotationAttachment(
                type=DATASET_MIME_TYPE,
                url=citation.url,
                title=f"{_shorten_for_pill(leading, pill_chars)}{_DATASET_LABEL_SUFFIX}",
            )
        ),
        quote=_dataset_quote(citation),
    )


def _dataset_quote(citation: _ConvertibleDatasetCitation) -> str:
    """What the card says about the dataset: which one it is, and how current it is.

    A Markdown list, because the client renders this one field through its Markdown renderer, so
    two facts read as two items rather than as one run-on line. The last-update row is dropped
    whole when the catalogue reported no date: a reader learns nothing from a line saying the app
    knows nothing, and a dataset without a date is ordinary rather than a fault.
    """
    items = [f"* URN: {citation.dataset_id}"]
    if citation.source.last_updated:
        items.append(f"* Last update: {citation.source.last_updated}")
    return "\n".join(items)


def _convertible_citation(
    marker: CitationMarker,
    *,
    document_urls: Mapping[int, str],
    dataset_sources: Mapping[str, DatasetSource],
) -> _ConvertibleCitation | None:
    """What this citation opens, or None when it cannot become a pill.

    One condition per kind of source, both decided here and both about whether the reader can
    open what the pill would point at. A document citation needs a PDF URL for the document it
    names. A dataset citation needs a record for the URN it names, carrying a URL a browser can
    open — a storage-relative path would make the client offer a file download rather than a page.
    """
    if marker.document_id is not None and marker.page is not None:
        url = document_urls.get(marker.document_id)
        if url is None or not is_pdf_url(url):
            return None
        return _ConvertibleDocumentCitation(
            document_id=marker.document_id, page=marker.page, url=url
        )
    if marker.dataset_id is not None:
        source = dataset_sources.get(marker.dataset_id)
        # A record with no URL is a cited dataset all the same: it keeps its marker text here and
        # is still listed in the References section, which is why the catalogue read keeps every
        # cited record rather than only the ones a pill can use. The URL is checked here rather
        # than assumed — the catalogue reader normalizes an unusable one away, but this function
        # is also called with sources a caller built itself.
        if source is None or source.url is None or not is_web_url(source.url):
            return None
        return _ConvertibleDatasetCitation(
            dataset_id=marker.dataset_id, url=source.url, source=source
        )
    return None


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


def is_web_url(url: str) -> bool:
    """Whether the URL is one a browser can open: absolute, `http` or `https`, with a host.

    Public for the reason `is_pdf_url` is: a caller resolving URLs has to refuse one this would
    reject, rather than hand over a URL whose citations then quietly keep their marker text.

    The dataset-metadata contract returns a string and nothing else, so the URL's own form is
    what the app has to go on. A storage-relative `files/…` path, a scheme the client would not
    follow and a value that is not a URL at all are each treated as not openable — the
    conservative direction, since a pill that opens nothing is worse than a marker that at least
    names its source. A relative path in particular would make the client offer a file download
    rather than open a page.
    """
    parts = urlsplit(url)
    return parts.scheme.lower() in _WEB_URL_SCHEMES and bool(parts.netloc)


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
