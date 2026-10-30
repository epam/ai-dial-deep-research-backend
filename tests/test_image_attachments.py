"""Tests for the image blocks of a research record: placeholders, snapshot uploads and downloads.

We stand up a fake `AsyncDial` rather than mocking — the helpers only touch
`dial.bucket.get_raw()`, `dial.files.upload(url, file)` and `dial.files.download(url)`,
so a tiny stand-in that scripts each call's outcome is clearer than `unittest.mock`.
`asyncio.sleep` is replaced by a recorder, so the retry delays are asserted, not waited.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
from aidial_client import DialException, ResourceNotFoundError
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from dial_deep_research.app.error_resolution import SnapshotImageUnavailableError
from dial_deep_research.utils import image_attachments
from dial_deep_research.utils.image_attachments import (
    download_snapshot_images,
    replace_images_with_placeholders,
    upload_snapshot_images,
)

_PNG = b"\x89PNG\r\n\x1a\nfake png bytes"
_PNG_B64 = base64.b64encode(_PNG).decode()
_JPEG = b"\xff\xd8\xff\xe0fake jpeg bytes"
_JPEG_B64 = base64.b64encode(_JPEG).decode()

_LOGGER_NAME = image_attachments.__name__

# --------------------------------------------------------------------- fakes

Outcome = Exception | None
"""A scripted upload outcome: the exception to raise, or `None` for success."""


@dataclass
class _BucketResp:
    bucket: str
    appdata: str | None


@dataclass
class _UploadResult:
    url: str


@dataclass
class _DownloadResult:
    payload: bytes

    async def aget_content(self) -> bytes:
        return self.payload


@dataclass
class _FakeBucket:
    response: _BucketResp
    exc: Exception | None = None
    calls: int = 0

    async def get_raw(self) -> _BucketResp:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.response


@dataclass
class _FakeFiles:
    """Answers each call with the next scripted outcome for its file; succeeds once none is left.

    Upload outcomes are keyed by the uploaded file name, download outcomes by the requested URL.
    """

    upload_outcomes: dict[str, list[Outcome]] = field(default_factory=dict)
    download_outcomes: dict[str, list[Exception | bytes]] = field(default_factory=dict)
    uploads: list[tuple[str, str, bytes, str]] = field(default_factory=list)
    upload_requests: list[str] = field(default_factory=list)
    download_requests: list[str] = field(default_factory=list)

    async def upload(self, *, url: str, file: tuple[str, bytes, str]) -> _UploadResult:
        filename, raw, content_type = file
        self.upload_requests.append(url)
        script = self.upload_outcomes.get(filename, [])
        if script and (exc := script.pop(0)) is not None:
            raise exc
        self.uploads.append((url, filename, raw, content_type))
        return _UploadResult(url=f"https://dial/v1/{url}")

    async def download(self, url: str) -> _DownloadResult:
        self.download_requests.append(url)
        outcome = self.download_outcomes[url].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _DownloadResult(payload=outcome)


@dataclass
class _FakeDial:
    bucket: _FakeBucket
    files: _FakeFiles


def _make_dial(
    *,
    appdata: str | None = "ub/appdata/deep-research",
    bucket: str = "ub",
    bucket_exc: Exception | None = None,
    upload_outcomes: dict[str, list[Outcome]] | None = None,
    download_outcomes: dict[str, list[Exception | bytes]] | None = None,
) -> _FakeDial:
    return _FakeDial(
        bucket=_FakeBucket(response=_BucketResp(bucket=bucket, appdata=appdata), exc=bucket_exc),
        files=_FakeFiles(
            upload_outcomes=upload_outcomes or {}, download_outcomes=download_outcomes or {}
        ),
    )


def _dial_error(status_code: int) -> DialException:
    return DialException(message=f"status {status_code}", status_code=status_code)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The delay of every `asyncio.sleep` call, in call order; none of them waits."""
    recorded: list[float] = []

    async def record(delay: float, *args: Any, **kwargs: Any) -> None:
        recorded.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record)
    return recorded


def _image(*, payload_b64: str = _PNG_B64, mime_type: str = "image/png") -> dict[str, Any]:
    return {"type": "image", "base64": payload_b64, "mime_type": mime_type}


def _tool_image_message(call_id: str = "call_1") -> ToolMessage:
    return ToolMessage(content=[_image()], tool_call_id=call_id)


def _placeholder_text(*, reason: str, mime_type: str, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return f"[image not stored: {reason}, {mime_type}, sha256={digest}]"


def _assert_no_image_bytes_logged(caplog: pytest.LogCaptureFixture) -> None:
    for record in caplog.records:
        text = record.getMessage()
        assert _PNG_B64 not in text
        assert _JPEG_B64 not in text
        assert all(arg not in (_PNG, _JPEG) for arg in record.args or ())


# --------------------------------------------------------------------- placeholders


def test_every_image_becomes_its_own_successful_run_placeholder() -> None:
    first = ToolMessage(
        content=[
            {"type": "text", "text": "page 1"},
            _image(),
            {"type": "text", "text": "page 2"},
            _image(payload_b64=_JPEG_B64, mime_type="image/jpeg"),
        ],
        tool_call_id="call_1",
    )
    second = AIMessage(content=[_image(payload_b64=_JPEG_B64, mime_type="image/jpeg")])

    # It takes no dial client, so no files call can be made.
    replace_images_with_placeholders([first, second])

    png_text = _placeholder_text(reason="successful run", mime_type="image/png", payload=_PNG)
    jpeg_text = _placeholder_text(reason="successful run", mime_type="image/jpeg", payload=_JPEG)
    assert first.content == [
        {"type": "text", "text": "page 1"},
        {"type": "text", "text": png_text},
        {"type": "text", "text": "page 2"},
        {"type": "text", "text": jpeg_text},
    ]
    assert second.content == [{"type": "text", "text": jpeg_text}]


# --------------------------------------------------------------------- uploads


async def test_upload_rewrites_the_image_block_to_a_url(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    tool_msg = ToolMessage(
        content=[{"type": "text", "text": "hi"}, _image()],
        tool_call_id="call_1",
    )
    dial = _make_dial(appdata="ub/appdata/deep-research")

    not_stored = await upload_snapshot_images([tool_msg], dial)  # type: ignore[arg-type]

    assert not_stored == 0
    assert tool_msg.content[0] == {"type": "text", "text": "hi"}
    assert tool_msg.content[1] == {
        "type": "image",
        "mime_type": "image/png",
        "url": "https://dial/v1/files/ub/appdata/deep-research/dial-deep-research/call_1-1.png",
    }
    [(url, filename, raw, content_type)] = dial.files.uploads
    assert url == "files/ub/appdata/deep-research/dial-deep-research/call_1-1.png"
    assert filename == "call_1-1.png"
    assert raw == _PNG
    assert content_type == "image/png"
    assert sleeps == []
    assert caplog.records == []


@pytest.mark.parametrize(
    ("appdata", "bucket", "expected_path_prefix"),
    [
        ("ub/appdata/deep-research", "ub", "files/ub/appdata/deep-research/dial-deep-research/"),
        (None, "ub", "files/ub/dial-deep-research/"),
    ],
)
async def test_the_upload_prefers_appdata_over_the_bucket(
    appdata: str | None, bucket: str, expected_path_prefix: str
) -> None:
    dial = _make_dial(appdata=appdata, bucket=bucket)

    await upload_snapshot_images([_tool_image_message()], dial)  # type: ignore[arg-type]

    [upload_url] = dial.files.upload_requests
    assert upload_url.startswith(expected_path_prefix)


async def test_an_ai_message_image_is_named_after_the_message_id() -> None:
    ai_msg = AIMessage(content=[_image()], id="lc_abc")
    dial = _make_dial()

    await upload_snapshot_images([ai_msg], dial)  # type: ignore[arg-type]

    assert "base64" not in ai_msg.content[0]
    assert ai_msg.content[0]["url"].endswith("dial-deep-research/lc_abc-0.png")  # type: ignore[index]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "plain string content",
        [{"type": "text", "text": "no images here"}],
    ],
)
async def test_messages_without_images_make_no_files_call(content: Any) -> None:
    msg = ToolMessage(content=content, tool_call_id="call_1")
    dial = _make_dial()

    not_stored = await upload_snapshot_images([msg], dial)  # type: ignore[arg-type]

    assert not_stored == 0
    assert dial.bucket.calls == 0
    assert dial.files.upload_requests == []
    assert msg.content == content


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
async def test_an_upload_failing_with_a_retried_status_is_retried(
    status_code: int, sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    tool_msg = _tool_image_message()
    dial = _make_dial(upload_outcomes={"call_1-0.png": [_dial_error(status_code)]})

    not_stored = await upload_snapshot_images([tool_msg], dial)  # type: ignore[arg-type]

    assert not_stored == 0
    assert len(dial.files.upload_requests) == 2
    assert tool_msg.content[0]["url"].endswith("call_1-0.png")  # type: ignore[index]
    assert sleeps == [1.0]
    _assert_no_image_bytes_logged(caplog)


async def test_an_upload_that_fails_twice_with_503_then_succeeds_stores_the_url(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    tool_msg = _tool_image_message()
    dial = _make_dial(upload_outcomes={"call_1-0.png": [_dial_error(503), _dial_error(503)]})

    not_stored = await upload_snapshot_images([tool_msg], dial)  # type: ignore[arg-type]

    assert not_stored == 0
    assert tool_msg.content == [
        {
            "type": "image",
            "mime_type": "image/png",
            "url": "https://dial/v1/files/ub/appdata/deep-research/dial-deep-research/call_1-0.png",
        }
    ]
    assert len(dial.files.upload_requests) == 3
    assert sleeps == [1.0, 2.0]
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.WARNING]
    assert "attempt=1" in caplog.records[0].getMessage()
    assert "attempt=2" in caplog.records[1].getMessage()
    _assert_no_image_bytes_logged(caplog)


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
async def test_an_upload_that_fails_all_four_attempts_gets_the_upload_failed_placeholder(
    status_code: int, sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    tool_msg = _tool_image_message()
    dial = _make_dial(upload_outcomes={"call_1-0.png": [_dial_error(status_code)] * 5})

    not_stored = await upload_snapshot_images([tool_msg], dial)  # type: ignore[arg-type]

    assert not_stored == 1
    assert len(dial.files.upload_requests) == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert tool_msg.content == [
        {
            "type": "text",
            "text": _placeholder_text(reason="upload failed", mime_type="image/png", payload=_PNG),
        }
    ]
    # One WARNING per retried attempt, then one for the image whose last attempt failed.
    assert len(caplog.records) == 4
    assert "last attempt" in caplog.records[-1].getMessage()
    _assert_no_image_bytes_logged(caplog)


async def test_an_upload_failing_with_400_is_not_retried(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    tool_msg = _tool_image_message()
    dial = _make_dial(upload_outcomes={"call_1-0.png": [_dial_error(400)]})

    not_stored = await upload_snapshot_images([tool_msg], dial)  # type: ignore[arg-type]

    assert not_stored == 1
    assert len(dial.files.upload_requests) == 1
    assert sleeps == []
    [block] = tool_msg.content
    assert block["type"] == "text"  # type: ignore[index]
    assert block["text"].startswith("[image not stored: upload failed, image/png")  # type: ignore[index]
    [record] = caplog.records
    assert "error=DialException" in record.getMessage()
    _assert_no_image_bytes_logged(caplog)


async def test_a_failed_bucket_lookup_gives_every_image_a_placeholder_logged_once(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    messages = [_tool_image_message(call_id=f"call_{n}") for n in range(3)]
    dial = _make_dial(bucket_exc=RuntimeError("bucket lookup failed"))

    not_stored = await upload_snapshot_images(messages, dial)  # type: ignore[arg-type]

    assert not_stored == 3
    expected = _placeholder_text(reason="upload failed", mime_type="image/png", payload=_PNG)
    for message in messages:
        assert message.content == [{"type": "text", "text": expected}]
    [record] = caplog.records
    assert "error=RuntimeError" in record.getMessage()
    assert dial.files.upload_requests == []
    assert sleeps == []
    _assert_no_image_bytes_logged(caplog)


# --------------------------------------------------------------------- downloads

_SNAPSHOT_IMAGE_URL = "files/ub/dial-deep-research/call_9-0.png?sig=secret#frag"
_SNAPSHOT_IMAGE_PATH = "files/ub/dial-deep-research/call_9-0.png"
_OTHER_IMAGE_URL = "files/ub/dial-deep-research/call_8-0.png?sig=other"


def _snapshot_messages(*urls: str) -> list[BaseMessage]:
    return [
        ToolMessage(
            content=[{"type": "image", "url": url, "mime_type": "image/png"}],
            tool_call_id=f"call_{n}",
        )
        for n, url in enumerate(urls or (_SNAPSHOT_IMAGE_URL,))
    ]


def _assert_no_query_logged(caplog: pytest.LogCaptureFixture) -> None:
    for record in caplog.records:
        text = record.getMessage()
        assert "?" not in text
        assert "sig=" not in text
        assert "frag" not in text


@pytest.mark.parametrize("status_code", [502, 503])
async def test_a_download_failing_with_a_retried_status_is_retried(
    status_code: int, sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    messages = _snapshot_messages()
    dial = _make_dial(download_outcomes={_SNAPSHOT_IMAGE_URL: [_dial_error(status_code), _PNG]})

    missing = await download_snapshot_images(messages, dial)  # type: ignore[arg-type]

    assert missing == 0
    assert messages[0].content == [{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}]
    assert len(dial.files.download_requests) == 2
    assert sleeps == [1.0]
    [record] = caplog.records
    text = record.getMessage()
    assert "attempt=1" in text
    assert "error=DialException" in text
    assert f"url={_SNAPSHOT_IMAGE_PATH}" in text
    _assert_no_query_logged(caplog)


async def test_a_download_failing_three_times_with_503_cannot_be_loaded(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    dial = _make_dial(download_outcomes={_SNAPSHOT_IMAGE_URL: [_dial_error(503)] * 3})

    with pytest.raises(SnapshotImageUnavailableError) as raised:
        await download_snapshot_images(_snapshot_messages(), dial)  # type: ignore[arg-type]

    assert isinstance(raised.value.__cause__, DialException)
    assert len(dial.files.download_requests) == 3
    assert sleeps == [1.0, 2.0]
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.WARNING]
    assert all("retrying" in r.getMessage() for r in caplog.records)
    _assert_no_query_logged(caplog)


@pytest.mark.parametrize("status_code", [500, 504])
async def test_a_download_failing_with_another_status_is_not_retried(
    status_code: int, sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    dial = _make_dial(download_outcomes={_SNAPSHOT_IMAGE_URL: [_dial_error(status_code)]})

    with pytest.raises(SnapshotImageUnavailableError) as raised:
        await download_snapshot_images(_snapshot_messages(), dial)  # type: ignore[arg-type]

    assert raised.value.__cause__ is not None
    assert raised.value.__cause__.status_code == status_code  # type: ignore[attr-defined]
    assert len(dial.files.download_requests) == 1
    assert sleeps == []
    assert caplog.records == []


async def test_a_gone_snapshot_image_is_counted_and_not_retried(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    messages = _snapshot_messages()
    dial = _make_dial(
        download_outcomes={_SNAPSHOT_IMAGE_URL: [ResourceNotFoundError(message="gone")]}
    )

    missing = await download_snapshot_images(messages, dial)  # type: ignore[arg-type]

    assert missing == 1
    assert len(dial.files.download_requests) == 1
    assert sleeps == []
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage() == f"Snapshot image is gone: url={_SNAPSHOT_IMAGE_PATH}"
    _assert_no_query_logged(caplog)


async def test_a_gone_image_beside_one_that_keeps_failing_is_counted_without_raising(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    messages = _snapshot_messages(_SNAPSHOT_IMAGE_URL, _OTHER_IMAGE_URL)
    dial = _make_dial(
        download_outcomes={
            _SNAPSHOT_IMAGE_URL: [ResourceNotFoundError(message="gone")],
            _OTHER_IMAGE_URL: [_dial_error(503)] * 3,
        }
    )

    missing = await download_snapshot_images(messages, dial)  # type: ignore[arg-type]

    assert missing == 1
    assert dial.files.download_requests.count(_SNAPSHOT_IMAGE_URL) == 1
    assert dial.files.download_requests.count(_OTHER_IMAGE_URL) == 3
    assert sleeps == [1.0, 2.0]
    gone = [r for r in caplog.records if "is gone" in r.getMessage()]
    assert [r.getMessage() for r in gone] == [f"Snapshot image is gone: url={_SNAPSHOT_IMAGE_PATH}"]
    _assert_no_query_logged(caplog)


class _UploadResultWithoutUrl:
    """An upload answer whose URL cannot be read."""

    @property
    def url(self) -> str:
        raise AttributeError("url")


async def test_an_upload_whose_url_cannot_be_read_leaves_a_placeholder(
    sleeps: list[float],
) -> None:
    dial = _make_dial()

    async def upload(*, url: str, file: tuple[str, bytes, str]) -> _UploadResultWithoutUrl:
        return _UploadResultWithoutUrl()

    dial.files.upload = upload  # type: ignore[method-assign]
    message = _tool_image_message()

    not_stored = await upload_snapshot_images(messages=[message], dial=dial)  # type: ignore[arg-type]

    assert not_stored == 1
    assert message.content == [
        {
            "type": "text",
            "text": _placeholder_text(
                reason="upload failed", mime_type="image/png", payload=base64.b64decode(_PNG_B64)
            ),
        }
    ]
