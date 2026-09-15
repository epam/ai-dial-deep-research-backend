"""Reading document metadata from the configured resource, and the titles taken out of it.

Every case here is decided by what the resource answered, so the client is a stub: the module
owns the URI it builds, the shape it accepts and the titles read out of it, and nothing else.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.documents.base import Blob

from dial_deep_research.app.research.document_metadata import (
    KIND_METADATA_READ_FAILED,
    KIND_METADATA_UNREADABLE,
    DocumentMetadataError,
    build_resource_uri,
    read_document_metadata,
    read_titles,
)
from dial_deep_research.app_properties import DocumentMetadataSource

SOURCE = DocumentMetadataSource(
    server_name="publications",
    resource_template="documents://metadata/{document_ids}",
    title_key="publication_title",
)


class _StubClient:
    """Answers one `get_resources` call, and records the URI it was asked for."""

    def __init__(self, *, body: str | None = None, error: Exception | None = None) -> None:
        self._body = body
        self._error = error
        self.requested_uris: list[str] = []

    async def get_resources(self, server_name: str, *, uris: list[str]) -> list[Blob]:
        self.requested_uris.extend(uris)
        if self._error is not None:
            raise self._error
        assert self._body is not None
        return [Blob.from_data(data=self._body, mime_type="application/json")]


async def _titles(body: str, document_ids: list[int] | None = None) -> dict[int, str]:
    """What a caller ends up with: the metadata the read returned, reduced to its titles."""
    metadata = await _metadata(body, document_ids)
    return read_titles(metadata, title_key=SOURCE.title_key)


async def _metadata(body: str, document_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    client = _StubClient(body=body)
    return await read_document_metadata(
        client=client,  # type: ignore[arg-type]
        source=SOURCE,
        document_ids=document_ids or [1],
    )


def test_the_uri_carries_the_cited_ids_in_order() -> None:
    assert build_resource_uri(SOURCE.resource_template, [9, 1, 5]) == "documents://metadata/9,1,5"


def test_a_single_id_needs_no_separator() -> None:
    assert build_resource_uri(SOURCE.resource_template, [7]) == "documents://metadata/7"


def test_only_the_placeholder_is_substituted() -> None:
    """A URI may hold braces of its own, which is why the placeholder is replaced literally."""
    template = "documents://{scope}/metadata/{document_ids}"
    assert build_resource_uri(template, [3]) == "documents://{scope}/metadata/3"


async def test_the_read_asks_for_the_ids_it_was_given() -> None:
    client = _StubClient(body="{}")
    await read_document_metadata(
        client=client,  # type: ignore[arg-type]
        source=SOURCE,
        document_ids=[4, 8],
    )
    assert client.requested_uris == ["documents://metadata/4,8"]


async def test_a_well_formed_answer_yields_the_configured_key() -> None:
    body = """
    {
      "1": {"publication_title": "Market Outlook 2025", "publication_date": "2025-04-22"},
      "5": {"publication_title": "Annual Report 2024"}
    }
    """
    assert await _titles(body) == {
        1: "Market Outlook 2025",
        5: "Annual Report 2024",
    }


async def test_integer_keys_are_accepted_as_well_as_string_ones() -> None:
    """JSON has no integer keys, but a server is free to answer either way."""
    assert await _titles('{"3": {"publication_title": "A"}}') == {3: "A"}


@pytest.mark.parametrize(
    ("fields", "case"),
    [
        ({}, "the key is absent"),
        ({"publication_title": ""}, "the value is empty"),
        ({"publication_title": "   "}, "the value is only whitespace"),
        ({"publication_title": None}, "the value is null"),
        ({"publication_title": 2025}, "the value is not a string"),
        ({"title": "Wrong key"}, "another key holds a title"),
    ],
)
async def test_a_document_without_a_usable_title_is_absent_rather_than_a_failure(
    fields: dict[str, Any], case: str
) -> None:
    """Its citations keep the marker label; the read itself still succeeds."""
    body = json.dumps({"1": fields, "2": {"publication_title": "Kept"}})
    assert await _titles(body, [1, 2]) == {2: "Kept"}, case


async def test_an_id_missing_from_the_answer_does_not_disturb_the_others() -> None:
    body = '{"2": {"publication_title": "Second"}}'
    assert await _titles(body, [1, 2]) == {2: "Second"}


async def test_a_failing_read_raises_the_typed_error() -> None:
    client = _StubClient(error=RuntimeError("connection reset"))
    with pytest.raises(DocumentMetadataError) as excinfo:
        await read_document_metadata(
            client=client,  # type: ignore[arg-type]
            source=SOURCE,
            document_ids=[1],
        )
    assert excinfo.value.kind == KIND_METADATA_READ_FAILED


@pytest.mark.parametrize(
    ("body", "case"),
    [
        ("not json at all", "the body is not JSON"),
        ("[1, 2, 3]", "the body is a list rather than an object"),
        ('{"1": "just a title"}', "a value is not a metadata object"),
        ('{"not-an-id": {"publication_title": "A"}}', "a key is not a document id"),
    ],
)
async def test_an_unreadable_answer_raises_the_typed_error(body: str, case: str) -> None:
    with pytest.raises(DocumentMetadataError) as excinfo:
        await _titles(body)
    assert excinfo.value.kind == KIND_METADATA_UNREADABLE, case


async def test_an_answer_carrying_no_content_is_unreadable() -> None:
    class _EmptyClient:
        async def get_resources(self, server_name: str, *, uris: list[str]) -> list[Blob]:
            return []

    with pytest.raises(DocumentMetadataError) as excinfo:
        await read_document_metadata(
            client=_EmptyClient(),  # type: ignore[arg-type]
            source=SOURCE,
            document_ids=[1],
        )
    assert excinfo.value.kind == KIND_METADATA_UNREADABLE
