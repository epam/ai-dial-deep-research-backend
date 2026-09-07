"""The inline-citations demo: its registration, its ten cases, and its refusal to half-answer.

What is protected here: the demo is absent unless its flag is set; its fixed report exercises
every behaviour of the citation mechanism through the shared code rather than a copy of it; and a
missing fixture or a request without a per-request key fails the turn with a message saying what
to do, instead of answering with an incomplete demonstration.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from dial_deep_research.app.annotations_demo import completion as demo
from dial_deep_research.app.annotations_demo.dial_files import BucketIds
from dial_deep_research.app.annotations_demo.report import FIXTURES, demo_report
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
_APPDATA = "user-bucket/appdata/deep-research"


class _FakeDialFiles:
    """The demo's file operations, with the DIAL calls replaced by their outcomes."""

    appdata: str | None = _APPDATA

    def __init__(self, **_: Any) -> None:
        self.copied: list[str] = []

    async def get_bucket_ids(self) -> BucketIds:
        return BucketIds(bucket="app-bucket", appdata=self.appdata)

    async def seed_into_app_bucket(self, *, bucket: str, source: Path) -> str:
        return f"files/{bucket}/{source.name}"

    async def copy_to_caller(self, *, source_url: str, appdata: str, name: str) -> str:
        self.copied.append(name)
        return f"files/{appdata}/{name}"


@pytest.fixture
def fixtures_in_place(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Both fixture PDFs present where the demo looks for them."""
    for file_name in FIXTURES.values():
        (tmp_path / file_name).write_bytes(b"%PDF-1.4 not a real document")
    monkeypatch.setattr(demo, "FIXTURES_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo, "DialFiles", _FakeDialFiles)


def _request() -> Any:
    return SimpleNamespace(api_key_secret=SecretStr("per-request-key"), messages=[])


async def _reply(choice: ChoiceSpy) -> None:
    await demo.AnnotationsDemoCompletion()._run_turn(_request(), choice)  # type: ignore[arg-type]


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
    fixtures_in_place: Path, fake_files: None
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert choice.content.count(f"<{CITATION_TAG_NAME} ") == 6
    assert len(annotations) == 7
    assert [annotation["index"] for annotation in annotations] == list(range(7))


async def test_every_annotation_names_a_tag_the_text_carries(
    fixtures_in_place: Path, fake_files: None
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    for annotation in annotations:
        tag_id = annotation["target"]["selector"]["id"]
        assert choice.content.count(f'data-id="{tag_id}"') == 1
        assert annotation["body"]["source"]["attachment"]["url"].startswith(f"files/{_APPDATA}/")


async def test_the_run_folds_into_one_tag_carrying_two_sources(
    fixtures_in_place: Path, fake_files: None
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    per_tag: dict[str, list[str]] = {}
    for annotation in annotations:
        per_tag.setdefault(annotation["target"]["selector"]["id"], []).append(
            annotation["body"]["title"]
        )
    # One tag carries the run's two distinct sources; the source repeated inside the run is
    # counted once. Every other tag carries exactly one.
    assert sorted(len(titles) for titles in per_tag.values()) == [1, 1, 1, 1, 1, 2]


async def test_the_cases_that_keep_their_marker_text_do(
    fixtures_in_place: Path, fake_files: None
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    lines = choice.content.splitlines()
    # The table cell and the heading both name a resolved document, and both keep the marker
    # because the client draws no pill there.
    table_row = next(line for line in lines if line.startswith("| A citation in a table cell"))
    heading = next(line for line in lines if line.startswith("### "))
    assert "[doc 101, page 1]" in table_row
    assert "[doc 101, page 1]" in heading
    # The document no URL resolved for keeps its marker where it stands.
    assert "[doc 999, page 1]" in choice.content


async def test_the_reply_points_nowhere_outside_the_retrieved_sources(
    fixtures_in_place: Path, fake_files: None
) -> None:
    choice = ChoiceSpy()

    await _reply(choice)

    assert "https://" not in choice.content
    assert "](" not in choice.content
    # The link's label survives, so the sentence still reads.
    assert "a link this report may not carry" in choice.content


async def test_only_the_cited_documents_with_a_fixture_are_copied(
    fixtures_in_place: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copies: list[str] = []

    class _RecordingFiles(_FakeDialFiles):
        async def copy_to_caller(self, *, source_url: str, appdata: str, name: str) -> str:
            copies.append(name)
            return await super().copy_to_caller(source_url=source_url, appdata=appdata, name=name)

    monkeypatch.setattr(demo, "DialFiles", _RecordingFiles)

    await _reply(ChoiceSpy())

    assert copies == ["doc-101.pdf", "doc-102.pdf"]


def test_the_demo_reuses_the_shared_conversion_rather_than_its_own() -> None:
    # The same three calls the demo makes, in the same order: same text, same annotation count.
    without_links = remove_hyperlinks(demo_report())
    urls = {
        document_id: f"files/{_APPDATA}/{file_name}"
        for document_id, file_name in FIXTURES.items()
        if document_id in cited_document_ids(without_links.text)
    }
    converted = convert_citations(without_links.text, document_urls=urls)

    assert len(converted.annotations) == 7
    assert converted.markers_left == 3
    assert without_links.removed == 2


# --- what it refuses to do ----------------------------------------------------------------------


async def test_a_missing_fixture_fails_the_turn_with_its_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_files: None
) -> None:
    monkeypatch.setattr(demo, "FIXTURES_DIR", str(tmp_path))

    with pytest.raises(demo.AnnotationsDemoUnavailableError) as raised:
        await _reply(ChoiceSpy())

    message = raised.value.user_message
    assert "doc-101.pdf" in message
    assert str(tmp_path) in message


async def test_a_request_without_a_per_request_key_fails_with_that_reason(
    fixtures_in_place: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _NoAppdataFiles(_FakeDialFiles):
        appdata = None

    monkeypatch.setattr(demo, "DialFiles", _NoAppdataFiles)

    with pytest.raises(demo.AnnotationsDemoUnavailableError) as raised:
        await _reply(ChoiceSpy())

    assert "appdata" in raised.value.user_message
