"""Building the report's References section from what the servers reported about its sources.

Pure functions over data — no DIAL objects, no LangChain, no I/O — so every rule below is testable
without a server, a model or a browser, the same shape `citations.py` has and for the same reason.

The section is the report's factual index of its sources, which is the one job a model's
recollection cannot do: a report writer can only write the titles and dates it remembers from the
chunks it read. So the app writes it, from the metadata the citation step has already resolved —
the document-metadata resource's answer and the dataset catalogue — and the report writer is given
the other sections only.

What a row holds is configuration rather than code: each MCP server declares the table its sources
are listed in, as a title and an ordered list of columns, each column a heading a reader sees and
the key it reads (see `ReferencesTable`). The caller pairs each table with the rows of its kind;
this module never learns which server serves what.

Two rules carry most of the behaviour:

- **Every cited source gets a row**, whether or not its metadata resolved and whether or not its
  citations became pills. The row is what tells a reader which source a marker names, so a source
  that lost its pill is the one whose reader needs it most.
- **The first column names the source, and it is the column that degrades.** Where its key resolves
  nothing, the cell falls back to the source's own identifier — the same fallback a pill's label
  uses — and every other column is simply left blank. Nothing marks a row as degraded.

A row whose source the reader can open carries a pill in its first cell: the cell holds only a
marker tag, and an annotation of the row's own claims it, so the source's name is rendered as the
pill. It opens what an inline pill of the same source opens, and on the same condition, both
decided in `citations.py`; a row whose source cannot be opened keeps its name as text. An
annotation rather than a link, because a cited document's shared URL is storage-relative, so an
ordinary Markdown link to it opens nothing. Nothing here writes a link: the no-hyperlink rule
governs what the report writer writes, and a marker tag is not a hyperlink.

The section is appended to a draft and nothing is taken out of one. A draft that writes its own
references section carries an extra `##` heading, which the structure check reports and the
revision loop acts on; a draft that spends its last version still carrying one is delivered with
that section followed by this one. Removing it here would mean removing a heading and everything
below it, which takes whatever the writer put after it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from dial_deep_research.app_properties import ReferenceColumn

from .citations import (
    Annotation,
    ConvertibleCitation,
    DatasetSource,
    build_row_annotation,
    convertible_dataset,
    convertible_document,
    marker_tag,
    new_tag_id,
)
from .report_length import SECTION_HEADING_LEVEL, SECTION_HEADING_PREFIX

# The heading level each server's table is written under: one below the section's own, which is
# what the report-composition rule that sub-headings sit at `###` or deeper requires.
_TABLE_HEADING_PREFIX = "#" * (SECTION_HEADING_LEVEL + 1)

# What joins the items of a list-valued cell. A comma and a space, because a cell is one line.
_LIST_SEPARATOR = ", "

# The page a document row opens its document at. A row names the whole document rather than a
# location in it, so it opens where the document begins; the viewer still needs a page to open at.
_DOCUMENT_ROW_PAGE = 1


class ReferenceRow(BaseModel):
    """One cited source: how to name it when nothing resolves, what its server reported, and what
    the row opens.

    `identifier` is what the first column falls back to — `doc 207` for a document, the URN for a
    dataset — so it is the caller's business how a kind of source names itself. `fields` is the
    metadata object or the catalogue record as the server sent it, which the columns read by key.
    `target` is what the row's pill opens, or `None` when the reader cannot open the source, and
    the first cell then carries the name as text.
    """

    identifier: str
    fields: dict[str, Any]
    target: ConvertibleCitation | None = None


class ReferencesTableContent(BaseModel):
    """One table of the section: how it is rendered, and the sources it lists.

    A table with no rows is a server whose sources this report did not cite, and it is dropped
    whole rather than rendered empty.
    """

    title: str
    columns: tuple[ReferenceColumn, ...]
    rows: list[ReferenceRow]


class ReferencesSection(BaseModel):
    """The built section, and the annotations claiming the marker tags of its openable rows."""

    text: str
    annotations: list[Annotation]


def build_references_section(
    *,
    heading: str,
    empty_text: str,
    tables: Sequence[ReferencesTableContent],
    first_index: int = 0,
    pill_title_max_chars: int | None = None,
    make_tag_id: Callable[[], str] = new_tag_id,
) -> ReferencesSection:
    """The whole References section as Markdown, ready to append to the delivered report, and the
    annotations claiming the marker tags of its openable rows.

    Args:
        heading: `references_section_name`, written as a `##` heading.
        empty_text: `references_section_empty_text`, what the section says when no source was cited
            at all, which is the only prose an app-built section holds.
        tables: one per configured server, in the order the tables are written. A table with no
            rows contributes nothing.
        first_index: the `index` of the first row annotation. The row annotations join the array
            after the inline citations' ones, so this is how many of those there are.
        pill_title_max_chars: the channel's pill budget, which a row's pill obeys like any pill.
        make_tag_id: source of tag ids. Injectable so a test can read the ids it expects.

    Every table being empty means the report cited nothing, and then the section carries
    `empty_text` instead: a report with nothing to cite says so rather than showing a bare heading.
    """
    pills = _RowPills(
        first_index=first_index,
        pill_title_max_chars=pill_title_max_chars,
        make_tag_id=make_tag_id,
    )
    blocks = [_render_table(table, pills=pills) for table in tables if table.rows]
    body = "\n\n".join(blocks) if blocks else empty_text
    return ReferencesSection(
        text=f"{SECTION_HEADING_PREFIX} {heading}\n\n{body}", annotations=pills.annotations
    )


class _RowPills:
    """Writes the marker tag of each row that opens its source, and collects its annotation."""

    def __init__(
        self,
        *,
        first_index: int,
        pill_title_max_chars: int | None,
        make_tag_id: Callable[[], str],
    ) -> None:
        self._first_index = first_index
        self._pill_title_max_chars = pill_title_max_chars
        self._make_tag_id = make_tag_id
        self.annotations: list[Annotation] = []

    def claim(self, *, row: ReferenceRow, target: ConvertibleCitation, name: str) -> str:
        """The first cell of a row that opens its source; `name` is empty when none resolved."""
        tag_id = self._make_tag_id()
        self.annotations.append(
            build_row_annotation(
                index=self._first_index + len(self.annotations),
                tag_id=tag_id,
                target=target,
                label=name if name else row.identifier,
                label_is_identifier=not name,
                pill_title_max_chars=self._pill_title_max_chars,
            )
        )
        return marker_tag(tag_id)


def _render_table(table: ReferencesTableContent, *, pills: _RowPills) -> str:
    """One table: its sub-heading, its header row, and one row per source it lists."""
    headings = [_escape_cell(column.heading) for column in table.columns]
    lines = [
        f"{_TABLE_HEADING_PREFIX} {table.title}",
        "",
        f"| {' | '.join(headings)} |",
        f"| {' | '.join('---' for _ in headings)} |",
    ]
    lines.extend(_render_row(row, columns=table.columns, pills=pills) for row in table.rows)
    return "\n".join(lines)


def _render_row(row: ReferenceRow, *, columns: Sequence[ReferenceColumn], pills: _RowPills) -> str:
    """One source's row: each column's value, the first falling back to the identifier.

    A row that opens its source carries only the marker tag in its first cell, the name moving
    into the pill's label. The label is the value before table escaping: a label is not table
    text, and a reader would see the backslash of an escaped `|`.
    """
    values = [_plain_value(row.fields.get(column.key)) for column in columns]
    cells = [_escape_cell(value) for value in values]
    if row.target is not None:
        cells[0] = pills.claim(row=row, target=row.target, name=_one_line(values[0]))
    elif not cells[0]:
        cells[0] = _escape_cell(row.identifier)
    return f"| {' | '.join(cells)} |"


def _plain_value(value: Any) -> str:
    """One cell's text, from whatever the channel stored under that column's key, unescaped.

    A channel owns its metadata, so a value is not required to be a string: a year stored as a
    number should fill its cell rather than blank it, and a list of topics should read as a list.
    Anything else — a nested object, a null, a string with nothing but whitespace in it — leaves the
    cell empty, which is what a reader can act on, rather than a rendering of the app's confusion.

    A string is stripped, so a value that only looks filled leaves the cell empty like an absent
    one — and in the first column that is what lets the row fall back to its source's identifier
    instead of reading blank, which would leave a reader with no way to tell which source it is.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        # Before the number branch: `bool` is a subclass of `int`, and `True` should not read `1`.
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [rendered for item in value if (rendered := _plain_value(item))]
        return _LIST_SEPARATOR.join(items)
    return ""


def _escape_cell(text: str) -> str:
    """A value as a Markdown table cell: nothing in it may end the cell or the row.

    An unescaped `|` shifts every cell after it into the wrong column, and a line break ends the
    row entirely — both silently, and both from a value a channel is entitled to store.
    """
    return _one_line(text).replace("|", r"\|")


def _one_line(text: str) -> str:
    """The text with every line break made a space, for a cell or a label that is one line."""
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def document_rows(
    document_ids: Sequence[int],
    *,
    metadata: Mapping[int, Mapping[str, Any]],
    document_urls: Mapping[int, str],
) -> list[ReferenceRow]:
    """One row per cited document, in the order the report first cites them.

    A document the metadata answer omits keeps its row, with no fields: its first cell reads
    `doc <id>`, the same text its citations carry when they cannot become pills. A document the
    reader can open opens at its first page.
    """
    return [
        ReferenceRow(
            identifier=f"doc {document_id}",
            fields=dict(metadata.get(document_id) or {}),
            target=convertible_document(
                document_id=document_id, page=_DOCUMENT_ROW_PAGE, document_urls=document_urls
            ),
        )
        for document_id in document_ids
    ]


def dataset_rows(
    dataset_ids: Sequence[str], *, sources: Mapping[str, DatasetSource]
) -> list[ReferenceRow]:
    """One row per cited dataset, in the order the report first cites them.

    A dataset the catalogue does not report keeps its row, with no fields: its first cell reads the
    URN the report's marker carried, which is the only name the app has for it. Its fields are the
    catalogue record as reported, which is what the configured columns read.
    """
    rows: list[ReferenceRow] = []
    for dataset_id in dataset_ids:
        source = sources.get(dataset_id)
        rows.append(
            ReferenceRow(
                identifier=dataset_id,
                fields=dict(source.raw_fields) if source is not None else {},
                target=convertible_dataset(dataset_id=dataset_id, dataset_sources=sources),
            )
        )
    return rows
