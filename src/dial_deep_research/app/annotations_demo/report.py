"""The fixed report the annotations demo replies with, and what it needs from the caller.

Every paragraph below demonstrates one behaviour of the citation step and says, in its own text,
what should appear at that spot — so someone who has never read the specification can look at the
rendered reply and tell a correct rendering from a broken one. Nothing else is in the report: no
research prose, no invented findings, and no Markdown beyond what a case needs in order to exist.

The report cites three documents. Two of them are the PDFs the caller attached, in the order they
arrive; which attachment becomes which document does not matter, because every case works either
way. The third is cited with nothing attached behind it, and is the case that keeps its marker
text because no URL resolved for it.

The report text is written one block per line, however long the line gets, and this file is the
one place the project's line limit is set aside. DIAL Chat's Markdown renderer turns every single
newline into a visible line break, so a hard-wrapped paragraph renders ragged; and a wrapped line
can open a Markdown construct of its own — a line starting `1. ` becomes an ordered list item —
which changes the very rendering the case beside it is there to show.
"""

from __future__ import annotations

from dial_deep_research.app.research.citations import find_citation_markers

# The documents an attachment is taken for, in the order the caller's PDFs are consumed.
ATTACHED_DOCUMENT_IDS: tuple[int, int] = (1, 2)

# Cited with nothing attached behind it, so its markers stay as text.
UNATTACHED_DOCUMENT_ID = 3

_REPORT = """\
This reply is a fixed demonstration of inline citations. It runs no research and calls no model: each paragraph below shows one behaviour of the citation step and says what you should see at that spot. Documents 1 and 2 are the two PDFs you attached, in the order they arrived.

Here is a lone citation in a paragraph: it becomes one pill that opens page 1 of document 1. [doc 1, page 1]

Here are three citations standing next to each other: they fold into a single pill. Two of the three name the same document and the same page, so that source is listed once and the pill's popup carries two entries rather than three. [doc 1, page 2] [doc 2, page 1], [doc 1, page 2]

Here is the same document and page cited again, in a paragraph of its own: it draws a second pill here rather than joining the one above. [doc 1, page 2]

- Here is a citation in a list item: it becomes a pill, as in a paragraph. [doc 2, page 2]

Here are two pages of one document, cited in two sentences: each becomes a pill of its own, and the two open different pages. [doc 2, page 1]. This second one opens page 3. [doc 2, page 3]

Here is a citation inside a table cell: it becomes a pill there too, because the client draws one wherever the marker tag stands.

| What the row shows | The citation |
| --- | --- |
| A citation in a table cell | [doc 1, page 1] |

### Here is a citation in a heading: it becomes a pill here as well [doc 1, page 1]

Here is a citation of a document you attached nothing for: it keeps its marker text and shows no pill, so a citation is never lost, only left as it was written. [doc 3, page 1]

Here is a Markdown link: it is delivered as its label alone, so the words [a link this report may not carry](https://example.org/outlook) are ordinary text with nothing to click.

Here is a bare URL: it is deleted from the delivered text, so this sentence ends right after the word "at": published at https://example.org/outlook
"""


def demo_report() -> str:
    """The report as it goes into the citation step."""
    return _REPORT


def _deepest_cited_page() -> int:
    """The deepest page the report cites, so an attachment shallower than this is refused.

    Read out of the report rather than written down beside it: a case that cites a new page then
    cannot disagree with the number the demo checks against.
    """
    return max(marker.page for marker in find_citation_markers(demo_report()) if marker.page)


# The page count every attached PDF must reach. The report cites only its first few pages, so a
# short document is still usable; one shallower than this leaves a pill scrolling to a page that
# is not there.
MIN_PAGES = _deepest_cited_page()
