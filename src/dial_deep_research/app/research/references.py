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

No row is interactive: no cell carries a link or a marker tag. A cited document's shared URL is
storage-relative, so an ordinary Markdown link to it opens nothing, and making a row openable means
an annotation of its own, which renders the row as a pill with a citation card. Because nothing
here writes a link, the report's no-hyperlink guarantee holds over the delivered text whole.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from dial_deep_research.app_properties import ReferenceColumn

from .report_length import SECTION_HEADING_LEVEL, SECTION_HEADING_PREFIX, find_section_heading_line

# The heading level each server's table is written under: one below the section's own, which is
# what the report-composition rule that sub-headings sit at `###` or deeper requires.
_TABLE_HEADING_PREFIX = "#" * (SECTION_HEADING_LEVEL + 1)

# What joins the items of a list-valued cell. A comma and a space, because a cell is one line.
_LIST_SEPARATOR = ", "


class ReferenceRow(BaseModel):
    """One cited source: how to name it when nothing resolves, and what its server reported.

    `identifier` is what the first column falls back to — `doc 207` for a document, the URN for a
    dataset — so it is the caller's business how a kind of source names itself. `fields` is the
    metadata object or the catalogue record as the server sent it, which the columns read by key.
    """

    identifier: str
    fields: dict[str, Any]


class ReferencesTableContent(BaseModel):
    """One table of the section: how it is rendered, and the sources it lists.

    A table with no rows is a server whose sources this report did not cite, and it is dropped
    whole rather than rendered empty.
    """

    title: str
    columns: tuple[ReferenceColumn, ...]
    rows: list[ReferenceRow]


def build_references_section(
    *,
    heading: str,
    empty_text: str,
    tables: Sequence[ReferencesTableContent],
) -> str:
    """The whole References section as Markdown, ready to append to the delivered report.

    Args:
        heading: the configured section name, written as a `##` heading.
        empty_text: what the section says when no source was cited at all — the configured
            references section's description, which is the only prose an app-built section holds.
        tables: one per configured server, in the order the tables are written. A table with no
            rows contributes nothing.

    Every table being empty means the report cited nothing, and then the section carries
    `empty_text` instead: a report with nothing to cite says so rather than showing a bare heading.
    """
    blocks = [_render_table(table) for table in tables if table.rows]
    body = "\n\n".join(blocks) if blocks else empty_text
    return f"{SECTION_HEADING_PREFIX} {heading}\n\n{body}"


def strip_references_section(text: str, *, heading: str) -> str:
    """The text without a references section the report writer wrote anyway.

    A draft is told not to write the section, and one that writes it is reported as a structure
    violation and measured with the rest — but it must not reach the reader beside the app's own,
    so it is removed here, at delivery.

    The heading is found by `find_section_heading_line`, so this agrees with the rest of the app
    about what a section heading is: at `##`, and lenient about the decoration a writer may add
    around the name, so `## **References**` is removed rather than delivered twice. Everything from
    that heading to the end goes with it, the section being last.
    """
    line = find_section_heading_line(text, name=heading)
    if line is None:
        return text
    return "\n".join(text.splitlines()[:line]).rstrip()


def _render_table(table: ReferencesTableContent) -> str:
    """One table: its sub-heading, its header row, and one row per source it lists."""
    headings = [_escape_cell(column.heading) for column in table.columns]
    lines = [
        f"{_TABLE_HEADING_PREFIX} {table.title}",
        "",
        f"| {' | '.join(headings)} |",
        f"| {' | '.join('---' for _ in headings)} |",
    ]
    lines.extend(_render_row(row, columns=table.columns) for row in table.rows)
    return "\n".join(lines)


def _render_row(row: ReferenceRow, *, columns: Sequence[ReferenceColumn]) -> str:
    """One source's row: each column's value, the first falling back to the identifier."""
    cells = [_render_value(row.fields.get(column.key)) for column in columns]
    if cells and not cells[0]:
        cells[0] = _escape_cell(row.identifier)
    return f"| {' | '.join(cells)} |"


def _render_value(value: Any) -> str:
    """One cell, from whatever the channel stored under that column's key.

    A channel owns its metadata, so a value is not required to be a string: a year stored as a
    number should fill its cell rather than blank it, and a list of topics should read as a list.
    Anything else — a nested object, a null, a string with nothing but whitespace in it — leaves the
    cell empty, which is what a reader can act on, rather than a rendering of the app's confusion.

    A string is stripped, so a value that only looks filled leaves the cell empty like an absent
    one — and in the first column that is what lets the row fall back to its source's identifier
    instead of reading blank, which would leave a reader with no way to tell which source it is.
    """
    if isinstance(value, str):
        return _escape_cell(value.strip())
    if isinstance(value, bool):
        # Before the number branch: `bool` is a subclass of `int`, and `True` should not read `1`.
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _escape_cell(str(value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [rendered for item in value if (rendered := _render_value(item))]
        return _LIST_SEPARATOR.join(items)
    return ""


def _escape_cell(text: str) -> str:
    """A value as a Markdown table cell: nothing in it may end the cell or the row.

    An unescaped `|` shifts every cell after it into the wrong column, and a line break ends the
    row entirely — both silently, and both from a value a channel is entitled to store.
    """
    return text.replace("|", r"\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def document_rows(
    document_ids: Sequence[int], *, metadata: Mapping[int, Mapping[str, Any]]
) -> list[ReferenceRow]:
    """One row per cited document, in the order the report first cites them.

    A document the metadata answer omits keeps its row, with no fields: its first cell reads
    `doc <id>`, the same text its citations carry when they cannot become pills.
    """
    return [
        ReferenceRow(identifier=f"doc {document_id}", fields=dict(metadata.get(document_id) or {}))
        for document_id in document_ids
    ]


def dataset_rows(
    dataset_ids: Sequence[str], *, records: Mapping[str, Mapping[str, Any]]
) -> list[ReferenceRow]:
    """One row per cited dataset, in the order the report first cites them.

    A dataset the catalogue does not report keeps its row, with no fields: its first cell reads the
    URN the report's marker carried, which is the only name the app has for it.
    """
    return [
        ReferenceRow(identifier=dataset_id, fields=dict(records.get(dataset_id) or {}))
        for dataset_id in dataset_ids
    ]
