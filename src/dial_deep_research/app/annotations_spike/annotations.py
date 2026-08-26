"""Builds the `custom_content.annotations` array the spike emits.

Two grouping variants are emitted deliberately, because DIAL Chat groups annotations by
`body.source.attachment.url` and renders one pill per group at the *first* annotation's offset:

- Three citations of one PDF share a bare `plan.pdf` url — two of them on the same page, one on
  another page. If Chat behaves as its `citation-marker` spec reads, all three collapse into a
  single pill and the second and third citation locations show nothing.
- Two citations of the other PDF carry a `#page=N` fragment, making their urls differ. If the
  fragment is enough to separate them, that is a producer-side workaround for the collapse.

Page navigation is likewise requested two ways so they can be compared: a degenerate zero-size
`pdf_bbox` (the only selector Chat maps to a scroll target) and the `#page=N` fragment.
"""

from __future__ import annotations

from pydantic import BaseModel

PDF_MIME_TYPE = "application/pdf"


class SpikePdf(BaseModel):
    """One of the two PDFs the spike cites, as stored in DIAL file storage."""

    # DIAL file path, e.g. `files/<bucket>/plan.pdf` — no fragment.
    url: str
    title: str


class Citation(BaseModel):
    """One citation to turn into an annotation."""

    marker_id: str
    pdf: SpikePdf
    page: int
    # When true, the page goes into the url as `#page=N`, giving this citation its own group.
    page_in_url: bool


def build_citations(*, plan_pdf: SpikePdf, scaling_pdf: SpikePdf) -> list[Citation]:
    """The five citations, ordered as they appear in the report."""
    return [
        Citation(marker_id="c1", pdf=plan_pdf, page=3, page_in_url=False),
        Citation(marker_id="c2", pdf=plan_pdf, page=7, page_in_url=False),
        Citation(marker_id="c3", pdf=scaling_pdf, page=5, page_in_url=True),
        Citation(marker_id="c4", pdf=scaling_pdf, page=9, page_in_url=True),
        # Same PDF and same page as c1: the decisive test of whether one page cited twice in
        # different places yields two pills or one.
        Citation(marker_id="c5", pdf=plan_pdf, page=3, page_in_url=False),
    ]


def build_annotations(*, citations: list[Citation], offsets: dict[str, int]) -> list[dict]:
    """Turn citations into annotation dicts, numbering them 0..N-1.

    The sequential `index` is required on both sides: the DIAL SDK's non-streaming merge asserts
    every element of an indexed list carries an integer `index`, and DIAL Chat merges streaming
    deltas by it. Two annotations sharing an `index` would have their string fields concatenated
    by that merge, so the numbering must be unique as well as present.

    Raises:
        KeyError: if a citation's marker never appeared in the report text.
    """
    annotations: list[dict] = []
    for index, citation in enumerate(citations):
        end_offset = offsets[citation.marker_id]
        url = (
            f"{citation.pdf.url}#page={citation.page}" if citation.page_in_url else citation.pdf.url
        )

        annotations.append(
            {
                "index": index,
                "target": {
                    "selector": {
                        "type": "text_character_range",
                        # Chat reads only `end`; `start` is sent for schema completeness.
                        "start": end_offset,
                        "end": end_offset,
                    }
                },
                "body": {
                    "title": f"{citation.pdf.title}, page {citation.page}",
                    "quote": "",
                    "source": {
                        "type": "attachment",
                        "attachment": {
                            "type": PDF_MIME_TYPE,
                            "url": url,
                            "title": f"{citation.pdf.title}, page {citation.page}",
                        },
                    },
                    # A zero-size box carries the page without drawing a region. Chat applies a
                    # visible style to every highlight it maps, so whether this leaves a visible
                    # artifact is one of the things the spike is here to find out.
                    "selector": {
                        "type": "pdf_bbox",
                        "page": citation.page,
                        "x1": 0,
                        "y1": 0,
                        "x2": 0,
                        "y2": 0,
                    },
                },
            }
        )
    return annotations


def build_reference_attachments(*, citations: list[Citation]) -> list[dict]:
    """Reference-only attachments for the same sources, as a side-by-side comparison.

    This is the convention that already works today: an attachment with a `reference_url` and no
    `url` renders as a trailing pill, and Chat's `referenceAttachmentToPdfCanvasContent` parses a
    `*.pdf#page=N` reference to scroll the viewer to that page. Emitting both lets the annotation
    pills and the trailing pills be compared in one conversation.
    """
    seen: set[str] = set()
    attachments: list[dict] = []
    for citation in citations:
        reference_url = f"{citation.pdf.url}#page={citation.page}"
        if reference_url in seen:
            continue
        seen.add(reference_url)
        attachments.append(
            {
                "type": "text/markdown",
                "title": f"{citation.pdf.title}, page {citation.page}",
                "data": f"Reference-only variant for {citation.pdf.title} page {citation.page}.",
                "reference_url": reference_url,
                "reference_type": PDF_MIME_TYPE,
            }
        )
    return attachments
