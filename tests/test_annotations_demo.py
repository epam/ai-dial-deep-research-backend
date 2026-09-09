"""The inline-citations demo: its registration, its ten cases, and its refusal to half-answer.

What is protected here: the demo is absent unless its flag is set; its fixed report exercises
every behaviour of the citation mechanism through the shared code rather than a copy of it; its
annotations point at the caller's own attachments; and a call that cannot carry the report fails
the turn with a message saying what to attach, instead of answering with an incomplete
demonstration.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from aidial_sdk.chat_completion import Attachment
from pydantic import SecretStr
from pypdf import PdfWriter

from dial_deep_research.app.annotations_demo import attachments as attach
from dial_deep_research.app.annotations_demo import completion as demo
from dial_deep_research.app.annotations_demo.report import (
    ATTACHED_DOCUMENT_IDS,
    MIN_PAGES,
    demo_report,
)
from dial_deep_research.app.factory import create_app
from dial_deep_research.app.research.citations import (
    CITATION_TAG_NAME,
    cited_document_ids,
    convert_citations,
    remove_hyperlinks,
)
from dial_deep_research.app_properties import ANNOTATIONS_DEMO_DEPLOYMENT_NAME
from dial_deep_research.settings import settings

from .dial_spies import ChoiceSpy

_DEMO_ROUTE = f"/openai/deployments/{ANNOTATIONS_DEMO_DEPLOYMENT_NAME}/chat/completions"
_FIRST_URL = "files/user-bucket/first.pdf"
_SECOND_URL = "files/user-bucket/second.pdf"


def _pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _attachment(
    url: str, *, type_: str = "application/pdf", title: str | None = None
) -> Attachment:
    return Attachment(type=type_, url=url, title=title)


def _request(*files: Attachment) -> Any:
    message = SimpleNamespace(custom_content=SimpleNamespace(attachments=list(files)))
    return SimpleNamespace(api_key_secret=SecretStr("per-request-key"), messages=[message])


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Every attachment deep enough to carry the report, unless a test says otherwise."""
    contents = {_FIRST_URL: _pdf(MIN_PAGES), _SECOND_URL: _pdf(MIN_PAGES + 4)}

    async def _fake_download(*, url: str, client: Any, headers: dict[str, str]) -> bytes:
        return contents[url]

    monkeypatch.setattr(attach, "_download", _fake_download)
    return contents


async def _reply(choice: ChoiceSpy, *files: Attachment) -> None:
    request = _request(*(files or (_attachment(_FIRST_URL), _attachment(_SECOND_URL))))
    await demo.AnnotationsDemoCompletion()._run_turn(request, choice)  # type: ignore[arg-type]


def _annotations(choice: ChoiceSpy) -> list[dict[str, Any]]:
    return choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]


# --- registration -------------------------------------------------------------------------------


def _routes() -> set[str]:
    return {route.path for route in create_app().routes}  # type: ignore[attr-defined]


def test_the_demo_is_absent_unless_its_flag_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_annotations_demo", False)
    assert _DEMO_ROUTE not in _routes()


def test_the_flag_registers_the_demo_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_annotations_demo", True)
    assert _DEMO_ROUTE in _routes()


# --- the reply ----------------------------------------------------------------------------------


async def test_the_reply_carries_the_report_and_its_annotations(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    annotations = _annotations(choice)
    assert choice.content.count(f"<{CITATION_TAG_NAME} ") == 8
    assert len(annotations) == 9
    assert [annotation["index"] for annotation in annotations] == list(range(9))


async def test_every_annotation_points_at_an_attachment_and_a_tag_the_text_carries(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    for annotation in _annotations(choice):
        tag_id = annotation["target"]["selector"]["id"]
        assert choice.content.count(f'data-id="{tag_id}"') == 1
        assert annotation["body"]["source"]["attachment"]["url"] in {_FIRST_URL, _SECOND_URL}


async def test_the_run_folds_into_one_tag_carrying_two_sources(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    per_tag: dict[str, list[str]] = {}
    for annotation in _annotations(choice):
        per_tag.setdefault(annotation["target"]["selector"]["id"], []).append(
            annotation["body"]["title"]
        )
    # One tag carries the run's two distinct sources; the source repeated inside the run is
    # counted once. Every other tag carries exactly one.
    assert sorted(len(titles) for titles in per_tag.values()) == [1, 1, 1, 1, 1, 1, 1, 2]


async def test_the_table_cell_and_the_heading_carry_a_tag_like_any_other_case(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    lines = choice.content.splitlines()
    table_row = next(line for line in lines if line.startswith("| A citation in a table cell"))
    heading = next(line for line in lines if line.startswith("### "))
    for line in (table_row, heading):
        assert f"<{CITATION_TAG_NAME} " in line
        assert "[doc 1, page 1]" not in line


async def test_the_document_nothing_was_attached_for_keeps_its_marker(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    assert "[doc 3, page 1]" in choice.content


async def test_the_reply_points_nowhere_outside_the_attachments(
    downloads: dict[str, bytes],
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    assert "https://" not in choice.content
    assert "](" not in choice.content
    # The link's label survives, so the sentence still reads.
    assert "a link this report may not carry" in choice.content


async def test_the_two_attachments_become_the_two_cited_documents(
    downloads: dict[str, bytes],
) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        urls = await attach.resolve_documents(
            request=_request(_attachment(_FIRST_URL), _attachment(_SECOND_URL)), client=client
        )

    assert urls == dict(zip(ATTACHED_DOCUMENT_IDS, [_FIRST_URL, _SECOND_URL], strict=True))


def test_the_demo_reuses_the_shared_conversion_rather_than_its_own() -> None:
    # The same three calls the demo makes, in the same order: same text, same annotation count.
    without_links = remove_hyperlinks(demo_report())
    resolved = dict(zip(ATTACHED_DOCUMENT_IDS, [_FIRST_URL, _SECOND_URL], strict=True))
    urls = {
        document_id: url
        for document_id, url in resolved.items()
        if document_id in cited_document_ids(without_links.text)
    }
    converted = convert_citations(without_links.text, document_urls=urls)

    assert len(converted.annotations) == 9
    assert converted.markers_left == 1
    assert without_links.removed == 2


# --- what it refuses to do ----------------------------------------------------------------------


async def test_too_few_attachments_fail_the_turn_with_what_to_attach(
    downloads: dict[str, bytes],
) -> None:
    with pytest.raises(attach.AnnotationsDemoUnavailableError) as raised:
        await _reply(ChoiceSpy(), _attachment(_FIRST_URL))

    message = raised.value.user_message
    assert "carried 1" in message
    assert f"at least {MIN_PAGES} pages" in message


async def test_an_attachment_that_is_not_a_pdf_does_not_count(
    downloads: dict[str, bytes],
) -> None:
    with pytest.raises(attach.AnnotationsDemoUnavailableError) as raised:
        await _reply(
            ChoiceSpy(),
            _attachment(_FIRST_URL),
            _attachment("files/user-bucket/notes.txt", type_="text/plain"),
        )

    assert "carried 1" in raised.value.user_message


async def test_a_shallow_attachment_fails_naming_the_file_and_its_pages(
    downloads: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads[_SECOND_URL] = _pdf(MIN_PAGES - 1)

    with pytest.raises(attach.AnnotationsDemoUnavailableError) as raised:
        await _reply(
            ChoiceSpy(),
            _attachment(_FIRST_URL),
            _attachment(_SECOND_URL, title="short.pdf"),
        )

    message = raised.value.user_message
    assert "short.pdf" in message
    assert f"has {MIN_PAGES - 1} page(s)" in message
