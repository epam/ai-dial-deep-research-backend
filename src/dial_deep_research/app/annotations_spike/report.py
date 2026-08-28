"""The fixed report the annotations spike replies with, and its citation markers.

The report is ordinary substantive prose, not commentary about the spike that renders it. Its
only spike-specific feature is four placeholders — `{plan_url}`, `{scaling_url}`, `{solo_url}`,
and `{quote_url}` — bare url templates that `build_report` fills in with the caller's actual DIAL
paths at request time; everything else is fixed text.

The report is authored with inline `[[<url>]]` markers placed right after each cited sentence.
A marker's text is the exact attachment url its citation carries, fragment included, so the raw
source and the rendered message can be read against each other without cross-referencing this
package. `build_report` strips the markers and reports where each one sat, so the offsets can
never drift from the wording: editing a sentence moves its marker with it.

Marker text is therefore not unique. The three citations that share one bare url all carry the
same marker text, and that repetition is one of the things the spike is demonstrating. Markers
are consequently recorded positionally, as a list in report order — a marker is identified by
where it sits, never by what it reads.

DIAL Chat injects a citation pill *after* the character at `target.selector.end`, so a marker's
offset is the index of the last character before it. Every marker is placed after a full stop, so
the pill always follows the end of a sentence.

The source below is wrapped to keep it readable, but the wrapping is undone before the report is
sent: DIAL Chat's markdown renderer applies `remark-breaks`, which turns every single newline into
a visible line break, so a hard-wrapped paragraph would render ragged. Offsets are computed after
unwrapping and after interpolation, against the text as it is actually sent. Each marker must
therefore stay on one source line: `_unwrap_paragraphs` joins a paragraph's lines with a space,
and a marker split over two lines would take that space into the middle of its url.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# Markers are stripped before the text is sent, so their syntax only has to be unambiguous
# against the report's own markdown. The body is a url, matched non-greedily so that two markers
# on one line would still be read as two.
_MARKER_PATTERN = re.compile(r"\[\[(.+?)\]\]")

# A `str.format` template: the only braces in it are the four url placeholders.
_REPORT_SOURCE = """\
## Overview

Two lines of work ask the same question from opposite ends: how much of a model's competence
should be spent before it answers, and how much while it answers.

## When planning pays off

Planning is not uniformly useful. It earns its cost on tasks whose steps depend on each other,
and is close to wasted on tasks that decompose cleanly.[[{plan_url}]] The interesting cases sit
between those extremes, where the decision of whether to plan is itself the hard part.

An agent that decides per task, rather than planning always or never, keeps most of the benefit
at a fraction of the cost.[[{plan_url}]]

## Spending compute at answer time

Test-time compute is the other lever. Allocating more of it to a smaller model can beat a much
larger model given the same total budget, provided the allocation adapts to how hard the prompt
is.[[{scaling_url}#page=5]] The gain disappears when the budget is spread uniformly, which is why
the allocation policy matters more than the raw amount.[[{scaling_url}#page=9]]

## Taken together

Both results point the same way: the decision of where to spend effort is worth more than the
effort itself. Deciding when to plan is the training-time version of that question, and deciding
how long to think is the inference-time version.[[{plan_url}]] The paper introducing the planning
question frames it in its opening page.[[{solo_url}]] A later analysis restates the same point
about test-time compute.[[{quote_url}]]
"""


class CitationMarker(BaseModel):
    """One citation marker found in the report, and where its pill anchors."""

    # The marker's text: the attachment url this citation points at, fragment included.
    url: str
    # Index of the last character before the marker sat.
    end: int


class ReportWithMarkers(BaseModel):
    """The report as sent, plus the markers stripped out of it, in the order they appeared."""

    text: str
    markers: list[CitationMarker]


def _unwrap_paragraphs(text: str) -> str:
    """Join the wrapped lines of each paragraph into one line.

    Blocks are separated by blank lines, and every block here is either a heading or a
    paragraph, so joining a block's lines with a single space is enough.
    """
    blocks = [" ".join(line.strip() for line in block.splitlines()) for block in text.split("\n\n")]
    return "\n\n".join(blocks)


def build_report(
    *, plan_url: str, scaling_url: str, solo_url: str, quote_url: str
) -> ReportWithMarkers:
    """Fill in the four urls, unwrap the paragraphs, then strip the markers and record them.

    The urls are interpolated first, so that both the offsets and the recorded marker urls
    describe the text as it is actually sent.

    Args:
        plan_url: DIAL path of plan.pdf in the caller's bucket, with no `#page=N` fragment.
        scaling_url: DIAL path of scaling.pdf in the caller's bucket, with no `#page=N` fragment.
        solo_url: DIAL path of the second copy of plan.pdf in the caller's bucket, with no
            `#page=N` fragment.
        quote_url: DIAL path of the second copy of scaling.pdf in the caller's bucket, with no
            `#page=N` fragment.

    Raises:
        ValueError: if a marker sits at the very start of the text, where there is no preceding
            character to anchor a pill to.
    """
    source = _unwrap_paragraphs(
        _REPORT_SOURCE.format(
            plan_url=plan_url, scaling_url=scaling_url, solo_url=solo_url, quote_url=quote_url
        )
    )
    parts: list[str] = []
    markers: list[CitationMarker] = []
    clean_length = 0
    cursor = 0

    for match in _MARKER_PATTERN.finditer(source):
        url = match.group(1)
        parts.append(source[cursor : match.start()])
        clean_length += match.start() - cursor
        if clean_length == 0:
            raise ValueError(f"citation marker {url!r} has no text before it")

        markers.append(CitationMarker(url=url, end=clean_length - 1))
        cursor = match.end()

    parts.append(source[cursor:])
    return ReportWithMarkers(text="".join(parts), markers=markers)
