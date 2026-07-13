"""Tests for `image_attachments.upload_image_blocks` and `rehydrate_image_blocks`.

We stand up a fake `AsyncDial` rather than mocking — the helpers only touch
`dial.bucket.get_raw()`, `dial.files.upload(url, file)`, and
`dial.files.download(url)`, so a tiny stand-in is clearer and more readable
than `unittest.mock`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)

from dial_deep_research.utils.image_attachments import (
    rehydrate_image_blocks,
    upload_image_blocks,
)

_PNG = b"\x89PNG\r\n\x1a\nfake png bytes"
_PNG_B64 = base64.b64encode(_PNG).decode()


# --------------------------------------------------------------------- fakes


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

    async def get_raw(self) -> _BucketResp:
        return self.response


@dataclass
class _FakeFiles:
    uploads: list[tuple[str, str, bytes, str]] = field(default_factory=list)
    upload_url_template: str = "https://dial/v1/{relative}"
    upload_exc: Exception | None = None
    download_payloads: dict[str, bytes] = field(default_factory=dict)
    download_exc: Exception | None = None

    async def upload(
        self,
        *,
        url: str,
        file: tuple[str, bytes, str],
    ) -> _UploadResult:
        if self.upload_exc is not None:
            raise self.upload_exc
        filename, raw, content_type = file
        self.uploads.append((url, filename, raw, content_type))
        return _UploadResult(url=self.upload_url_template.format(relative=url))

    async def download(self, url: str) -> _DownloadResult:
        if self.download_exc is not None:
            raise self.download_exc
        return _DownloadResult(payload=self.download_payloads[url])


@dataclass
class _FakeDial:
    bucket: _FakeBucket
    files: _FakeFiles


def _make_dial(
    *,
    appdata: str | None = "ub/appdata/deep-research",
    bucket: str = "ub",
    upload_exc: Exception | None = None,
    download_payloads: dict[str, bytes] | None = None,
    download_exc: Exception | None = None,
) -> _FakeDial:
    return _FakeDial(
        bucket=_FakeBucket(_BucketResp(bucket=bucket, appdata=appdata)),
        files=_FakeFiles(
            upload_exc=upload_exc,
            download_payloads=download_payloads or {},
            download_exc=download_exc,
        ),
    )


# --------------------------------------------------------------------- 4.1: upload happy path


async def test_upload_rewrites_image_block_to_url() -> None:
    tool_msg = ToolMessage(
        content=[
            {"type": "text", "text": "hi"},
            {"type": "image", "base64": _PNG_B64, "mime_type": "image/png"},
        ],
        tool_call_id="call_1",
    )
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "get_page", "args": {}, "type": "tool_call"}],
        ),
        tool_msg,
    ]
    dial = _make_dial(appdata="ub/appdata/deep-research")

    await upload_image_blocks(messages, dial)  # type: ignore[arg-type]

    assert tool_msg.content[0] == {"type": "text", "text": "hi"}
    image_block = tool_msg.content[1]
    assert image_block["type"] == "image"
    assert image_block["mime_type"] == "image/png"
    assert "base64" not in image_block
    assert (
        image_block["url"]
        == "https://dial/v1/files/ub/appdata/deep-research/dial-deep-research/call_1-1.png"
    )
    # exactly one upload call, with the right path / bytes / type
    assert len(dial.files.uploads) == 1
    url, filename, raw, content_type = dial.files.uploads[0]
    assert url == "files/ub/appdata/deep-research/dial-deep-research/call_1-1.png"
    assert filename == "call_1-1.png"
    assert raw == _PNG
    assert content_type == "image/png"


# --------------------------------------------------------------------- 4.2: round-trip


async def test_upload_then_serialize_then_rehydrate_recovers_base64() -> None:
    original = [
        ToolMessage(
            content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
            tool_call_id="call_1",
        )
    ]
    dial = _make_dial()

    await upload_image_blocks(original, dial)  # type: ignore[arg-type]
    uploaded_url = original[0].content[0]["url"]
    raw_at_upload = dial.files.uploads[0][2]

    dumped = messages_to_dict(original)
    restored = list(messages_from_dict(dumped))

    # Set the fake to return the exact bytes that were uploaded.
    dial.files.download_payloads[uploaded_url] = raw_at_upload

    await rehydrate_image_blocks(restored, dial)  # type: ignore[arg-type]

    rehydrated_block = restored[0].content[0]
    assert rehydrated_block["type"] == "image"
    assert rehydrated_block["mime_type"] == "image/png"
    assert "url" not in rehydrated_block
    assert rehydrated_block["base64"] == _PNG_B64


# --------------------------------------------------------------------- 4.3: upload failure


async def test_upload_failure_replaces_block_with_text_placeholder() -> None:
    tool_msg = ToolMessage(
        content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
        tool_call_id="call_1",
    )
    dial = _make_dial(upload_exc=RuntimeError("upstream blew up"))

    await upload_image_blocks([tool_msg], dial)  # type: ignore[arg-type]

    block = tool_msg.content[0]
    assert block["type"] == "text"
    assert "image/png" in block["text"]
    assert "upload" in block["text"]
    # Ensure no base64 survives anywhere — the whole point of fail-closed.
    assert "base64" not in block


# --------------------------------------------------------------------- 4.4: rehydration failure


async def test_rehydration_failure_replaces_block_with_text_placeholder() -> None:
    tool_msg = ToolMessage(
        content=[
            {
                "type": "image",
                "url": "https://dial/v1/files/ub/dial-deep-research/call_1-0.png",
                "mime_type": "image/png",
            }
        ],
        tool_call_id="call_1",
    )
    dial = _make_dial(download_exc=RuntimeError("file gone"))

    await rehydrate_image_blocks([tool_msg], dial)  # type: ignore[arg-type]

    block = tool_msg.content[0]
    assert block["type"] == "text"
    assert "image/png" in block["text"]
    assert "download" in block["text"]
    assert "base64" not in block


# --------------------------------------------------------------------- 4.5: bucket fallback


@pytest.mark.parametrize(
    ("appdata", "bucket", "expected_path_prefix"),
    [
        (
            "ub/appdata/deep-research",
            "ub",
            "files/ub/appdata/deep-research/dial-deep-research/",
        ),
        (None, "ub", "files/ub/dial-deep-research/"),
    ],
)
async def test_bucket_fallback(appdata: str | None, bucket: str, expected_path_prefix: str) -> None:
    tool_msg = ToolMessage(
        content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
        tool_call_id="call_x",
    )
    dial = _make_dial(appdata=appdata, bucket=bucket)

    await upload_image_blocks([tool_msg], dial)  # type: ignore[arg-type]

    upload_url = dial.files.uploads[0][0]
    assert upload_url.startswith(expected_path_prefix)


# --------------------------------------------------------------------- 4.6: walker tolerance


@pytest.mark.parametrize(
    "content",
    [
        "",  # empty string (ToolMessage coerces None to a string anyway)
        "plain string content",
        [{"type": "text", "text": "no images here"}],
    ],
)
async def test_walker_tolerates_non_list_or_non_image_content(content: Any) -> None:
    msg = ToolMessage(content=content, tool_call_id="call_1")
    dial = _make_dial()

    await upload_image_blocks([msg], dial)  # type: ignore[arg-type]

    assert dial.files.uploads == []
    assert msg.content == content


# --------------------------------------------------------------------- AIMessage parity


async def test_ai_message_image_block_is_uploaded_by_same_walker() -> None:
    ai_msg = AIMessage(
        content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
        id="lc_abc",
    )
    dial = _make_dial()

    await upload_image_blocks([ai_msg], dial)  # type: ignore[arg-type]

    assert "base64" not in ai_msg.content[0]
    assert ai_msg.content[0]["url"].endswith("dial-deep-research/lc_abc-0.png")
