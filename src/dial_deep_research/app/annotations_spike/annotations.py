"""Builds the `custom_content.annotations` array the spike emits.

DIAL Chat groups annotations by `body.source.attachment.url` and renders one pill per group, at
the *first* annotation's offset. All seven citations here carry a bare url, so grouping falls out
of which document each citation points at, giving four groups:

- Group A: three citations of plan.pdf share its bare url — pages 3, 7, and 3 again — so all
  three collapse into a single pill and the second and third locations render nothing. It has a
  switcher and no quote, and its popup reserves a blank quote area.
- Group B: two citations of scaling.pdf share its bare url — pages 5 and 9 — and collapse the
  same way. It has a switcher and no quote, and shows the same blank gap as group A.
- Group C: one citation of a second copy of plan.pdf, stored under a different destination
  filename so its url matches nothing else, forms a singleton pill of its own. It has no
  switcher and no quote, and its popup shows no gap — confirming the gap tracks `hasSwitcher`,
  not whether a quote exists.
- Group D: one citation of a second copy of scaling.pdf, stored under yet another destination
  filename, also forming a singleton pill. Unlike the other three groups it carries a real
  `body.quote`, to confirm that quote text renders as actual content when one is present.

The page a pill navigates to never comes from the url. It is carried by `body.selector`, a
degenerate zero-size `pdf_bbox` — the only selector Chat maps to a scroll target.
"""

from __future__ import annotations

from pydantic import BaseModel

from dial_deep_research.app.annotations_spike.report import CitationMarker

PDF_MIME_TYPE = "application/pdf"


class SpikePdf(BaseModel):
    """One of the two PDFs the spike cites, as stored in DIAL file storage."""

    # DIAL file path, e.g. `files/<bucket>/plan.pdf` — no fragment.
    url: str
    title: str


class Citation(BaseModel):
    """One citation to turn into an annotation."""

    pdf: SpikePdf
    page: int
    # When true, the page goes into the url as `#page=N`, giving this citation its own group.
    page_in_url: bool
    # A real excerpt for `body.quote`. Most citations leave this unset; see `build_annotations`
    # for how presence versus absence changes the emitted body.
    quote: str | None = None

    @property
    def url(self) -> str:
        """The attachment url this citation points at — what DIAL Chat groups pills by."""
        return f"{self.pdf.url}#page={self.page}" if self.page_in_url else self.pdf.url


def build_citations(
    *, plan_pdf: SpikePdf, scaling_pdf: SpikePdf, solo_pdf: SpikePdf, quote_pdf: SpikePdf
) -> list[Citation]:
    """The seven citations, ordered as they appear in the report."""
    return [
        Citation(pdf=plan_pdf, page=3, page_in_url=False),
        Citation(pdf=plan_pdf, page=7, page_in_url=False),
        # `page_in_url` is currently false for all seven citations: a `#page=N` fragment does
        # split pill groups, but it also breaks Preview and Download on the annotation path.
        # Flip it back to true here to re-run that fragment experiment.
        Citation(pdf=scaling_pdf, page=5, page_in_url=False),
        Citation(pdf=scaling_pdf, page=9, page_in_url=False),
        # Same PDF and same page as the first citation: the decisive test of whether one page
        # cited twice in different places yields two pills or one.
        Citation(pdf=plan_pdf, page=3, page_in_url=False),
        # A second copy of plan.pdf at a url no other citation shares — group C, the singleton.
        Citation(pdf=solo_pdf, page=1, page_in_url=False),
        # A second copy of scaling.pdf at a url no other citation shares — group D, the
        # singleton that carries a real quote.
        Citation(
            pdf=quote_pdf,
            page=1,
            page_in_url=False,
            quote=(
                "Test-time compute helps most when its allocation adapts to problem "
                "difficulty, not when more of it is simply added."
            ),
        ),
    ]


def build_annotations(*, citations: list[Citation], markers: list[CitationMarker]) -> list[dict]:
    """Pair each citation with the marker in the same position, and number them 0..N-1.

    Markers carry a url rather than an id, and three of them read the same url, so position is
    the only thing that pairs a marker with its citation. The pairing is verified rather than
    assumed: a marker whose url disagrees with its citation's means the report text and this
    list have drifted apart, which would otherwise anchor a pill to the wrong sentence with
    nothing to show for it.

    The sequential `index` is required on both sides: the DIAL SDK's non-streaming merge asserts
    every element of an indexed list carries an integer `index`, and DIAL Chat merges streaming
    deltas by it. Two annotations sharing an `index` would have their string fields concatenated
    by that merge, so the numbering must be unique as well as present.

    Raises:
        ValueError: if the report holds a different number of markers than there are citations,
            or if a marker's url differs from that of the citation it is paired with.
    """
    if len(markers) != len(citations):
        raise ValueError(
            f"the report holds {len(markers)} citation marker(s) but there are "
            f"{len(citations)} citation(s)"
        )

    annotations: list[dict] = []
    for index, citation in enumerate(citations):
        marker = markers[index]
        if marker.url != citation.url:
            raise ValueError(
                f"citation {index} points at {citation.url!r}, but the marker in that position "
                f"reads {marker.url!r}"
            )
        end_offset = marker.end

        body: dict = {
            # Per-entry label inside a group's popup switcher — must carry the page so
            # stepping through 1/3, 2/3, 3/3 is distinguishable.
            "title": f"{citation.pdf.title}, page {citation.page}",
            "source": {
                "type": "attachment",
                "attachment": {
                    "type": PDF_MIME_TYPE,
                    "url": citation.url,
                    # Group-level label — this is what the pill itself displays
                    # (groupAnnotationsBySource's sourceName), so it stays page-free.
                    "title": citation.pdf.title,
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
        }
        # `quote` is included only when the citation carries one, using that exact text. When
        # `citation.quote` is None the key is omitted rather than set to "": the citation-card
        # spec reserves no space when the key is absent, but an empty string still left a blank
        # gap in the popup.
        if citation.quote is not None:
            body["quote"] = citation.quote

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
                "body": body,
            }
        )
    return annotations
