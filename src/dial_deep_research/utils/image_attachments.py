"""Upload-and-rehydrate helpers for image content blocks in tool/AI messages.

The MCP→LangChain adapter emits image content as LangChain v1
`{type: "image", base64, mime_type}` blocks. Every later request carries the
states of all earlier turns, and DIAL Core rejects a request above its size
limit (64 MiB by default) with 413, so image bytes kept in a state would bring
the conversation closer to a request that can no longer be sent. We therefore
upload each image to the DIAL files API before serialisation and swap the
`base64` field for a `url` reference. On the next turn the same blocks are
rehydrated by downloading the file and putting `base64` back, so the in-flight
contract from `multimodal-tool-output` (LLM endpoints receive base64 image
blocks, not DIAL-internal URLs) is preserved.

Fail-closed on upload error: we replace the failing block with a
`TextContentBlock` placeholder (rather than keeping the inline base64) so a
state never carries image bytes. A research snapshot is the exception on both
sides: its upload re-raises a failed bucket lookup, and its download retries and
raises, because a snapshot with placeholders would resume research without the
images research-agent saw.
"""

import asyncio
import base64
import logging
import mimetypes
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aidial_client import AsyncDial, ResourceNotFoundError
from langchain_core.messages import BaseMessage, ToolMessage

from dial_deep_research.app.error_resolution import (
    SnapshotImageUnavailableError,
    SnapshotUnreadableError,
)
from dial_deep_research.utils.content import is_image_block
from dial_deep_research.utils.llm import STREAM_DROP_INITIAL_DELAY, STREAM_DROP_MAX_ATTEMPTS

logger = logging.getLogger(__name__)

_BUCKET_PREFIX = "dial-deep-research"
_PLACEHOLDER_TEMPLATE = "[image {direction} failed: {mime_type}, ~{size_kb} KB ({reason})]"


def _ext_for_mime(mime_type: str | None) -> str:
    if not mime_type:
        return "bin"
    ext = mimetypes.guess_extension(mime_type) or ""
    return ext.lstrip(".") or "bin"


def _approx_kb(num_bytes: int) -> int:
    return max(1, (num_bytes + 512) // 1024)


def _approx_decoded_size_bytes(b64: str) -> int:
    # Each 4 base64 chars encode 3 bytes; close enough for the placeholder hint.
    return len(b64) * 3 // 4


def _strip_url_query(url: str) -> str:
    # Scheme + host + path only: query strings may carry signatures (content rule).
    scheme, netloc, path, _, _ = urlsplit(url)
    return urlunsplit((scheme, netloc, path, "", ""))


def _iter_image_blocks(
    messages: list[BaseMessage],
) -> Iterator[tuple[BaseMessage, int, dict[str, Any]]]:
    """Yield `(message, content_index, block)` for every dict image block.

    Tolerant of `content` being `None`, a `str`, or a `list`; non-list content
    yields nothing. Yielded `block` is a live dict reference — mutations or
    `messages[i].content[j] = new_block` replacements are visible to the caller.
    """
    for msg in messages:
        content = msg.content
        if not isinstance(content, list):
            continue
        for content_idx, block in enumerate(content):
            if is_image_block(block):
                yield msg, content_idx, block


def _make_placeholder(
    mime_type: str | None, num_bytes: int, direction: str, reason: str
) -> dict[str, Any]:
    return {
        "type": "text",
        "text": _PLACEHOLDER_TEMPLATE.format(
            mime_type=mime_type or "unknown",
            size_kb=_approx_kb(num_bytes),
            direction=direction,
            reason=reason,
        ),
    }


def _replace_block(msg: BaseMessage, content_idx: int, new_block: dict[str, Any]) -> None:
    if isinstance(msg.content, list):
        msg.content[content_idx] = new_block


def _message_owner_id(msg: BaseMessage) -> str:
    if isinstance(msg, ToolMessage) and msg.tool_call_id:
        return msg.tool_call_id
    return getattr(msg, "id", None) or f"msg-{uuid.uuid4()}"


async def upload_image_blocks(
    messages: list[BaseMessage], dial: AsyncDial, *, reraise_bucket_failure: bool = False
) -> None:
    """Upload every image block carrying `base64` and rewrite it to carry `url`.

    Bucket resolution: prefer `appdata`, fall back to `bucket`.
    On failure the offending block is replaced by a text
    placeholder so the resulting message slice is always safe to serialise into
    `custom_content.state["messages"]`. A bucket lookup that fails gives every
    image the placeholder, logged once, unless `reraise_bucket_failure` is set:
    a research snapshot's caller sets it, so the snapshot is dropped instead.
    """
    candidates = [
        (msg, content_idx, block)
        for msg, content_idx, block in _iter_image_blocks(messages)
        if "base64" in block
    ]
    if not candidates:
        return

    try:
        bucket_resp = await dial.bucket.get_raw()
    except Exception as lookup_error:
        if reraise_bucket_failure:
            raise
        logger.warning(
            "Files bucket lookup failed at the state save; every image gets a placeholder: "
            "error=%s images=%d",
            type(lookup_error).__name__,
            len(candidates),
        )
        reason = str(lookup_error)
        for msg, content_idx, block in candidates:
            num_bytes = _approx_decoded_size_bytes(block.get("base64", ""))
            placeholder = _make_placeholder(block.get("mime_type"), num_bytes, "upload", reason)
            _replace_block(msg, content_idx, placeholder)
        return
    bucket = bucket_resp.appdata or bucket_resp.bucket

    results = await asyncio.gather(
        *(
            _upload_one(dial, bucket, msg, content_idx, block)
            for msg, content_idx, block in candidates
        )
    )
    for (msg, content_idx, block), exc in zip(candidates, results, strict=True):
        if exc is None:
            continue
        num_bytes = _approx_decoded_size_bytes(block.get("base64", ""))
        mime_type = block.get("mime_type")
        logger.warning(
            "Image upload to DIAL files failed; substituting placeholder (mime=%s, size~%dB).",
            mime_type,
            num_bytes,
            exc_info=exc,
        )
        _replace_block(
            msg, content_idx, _make_placeholder(mime_type, num_bytes, "upload", str(exc))
        )


async def _upload_one(
    dial: AsyncDial,
    bucket: str,
    msg: BaseMessage,
    content_idx: int,
    block: dict[str, Any],
) -> Exception | None:
    try:
        mime_type = block.get("mime_type")
        raw = base64.b64decode(block["base64"])
        ext = _ext_for_mime(mime_type)
        name = f"{_BUCKET_PREFIX}/{_message_owner_id(msg)}-{content_idx}.{ext}"
        metadata = await dial.files.upload(
            url=f"files/{bucket}/{name}",
            file=(name.rsplit("/", 1)[-1], raw, mime_type or "application/octet-stream"),
        )
        block.pop("base64", None)
        block["url"] = metadata.url
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


async def rehydrate_image_blocks(messages: list[BaseMessage], dial: AsyncDial) -> None:
    """Download every image block carrying only `url` and rewrite to carry `base64`.

    Restores the in-flight invariant required by the `multimodal-tool-output`
    spec: when a `ToolMessage` reaches the agent on a follow-up turn, its image
    blocks SHALL carry `base64` (DIAL files URLs are not LLM-fetchable).
    """
    candidates = [
        (msg, content_idx, block)
        for msg, content_idx, block in _iter_image_blocks(messages)
        if "url" in block and "base64" not in block
    ]
    if not candidates:
        return

    results = await asyncio.gather(*(_download_one(dial, block) for _, _, block in candidates))
    for (msg, content_idx, block), exc in zip(candidates, results, strict=True):
        if exc is None:
            continue
        mime_type = block.get("mime_type")
        logger.warning(
            "Image download from DIAL files failed; substituting placeholder (url=%s, mime=%s).",
            _strip_url_query(block.get("url", "")),
            mime_type,
            exc_info=exc,
        )
        _replace_block(msg, content_idx, _make_placeholder(mime_type, 0, "download", str(exc)))


async def _download_one(dial: AsyncDial, block: dict[str, Any]) -> Exception | None:
    try:
        download = await dial.files.download(block["url"])
        raw = await download.aget_content()
        block.pop("url", None)
        block["base64"] = base64.b64encode(raw).decode()
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


async def download_snapshot_images(messages: list[BaseMessage], dial: AsyncDial) -> None:
    """Download every image block carrying only `url` back to `base64`, or raise.

    Unlike `rehydrate_image_blocks`, a failed download never becomes a placeholder: a resumed
    research run would otherwise go on without an image research-agent already saw. Each image
    gets up to `STREAM_DROP_MAX_ATTEMPTS` tries with exponential backoff. A 404 is not retried,
    since the file is gone for good, and makes the snapshot unreadable
    (`SnapshotUnreadableError`, which wins when both kinds occur); an image still failing after
    its last attempt raises `SnapshotImageUnavailableError`, which a later request may get past.
    """
    blocks = [
        block
        for _, _, block in _iter_image_blocks(messages)
        if "url" in block and "base64" not in block
    ]
    results = await asyncio.gather(*(_download_with_retries(dial, block) for block in blocks))
    failures = [failure for failure in results if failure is not None]
    for failure in failures:
        if isinstance(failure, ResourceNotFoundError):
            raise SnapshotUnreadableError() from failure
    if failures:
        raise SnapshotImageUnavailableError() from failures[0]


async def _download_with_retries(dial: AsyncDial, block: dict[str, Any]) -> Exception | None:
    """Download one snapshot image; the failure of its last attempt, or `None` on success."""
    for attempt in range(1, STREAM_DROP_MAX_ATTEMPTS + 1):
        failure = await _download_one(dial, block)
        if failure is None or isinstance(failure, ResourceNotFoundError):
            return failure
        if attempt == STREAM_DROP_MAX_ATTEMPTS:
            return failure
        logger.warning(
            "Snapshot image download failed; retrying: attempt=%d error=%s url=%s",
            attempt,
            type(failure).__name__,
            _strip_url_query(block.get("url", "")),
        )
        await asyncio.sleep(STREAM_DROP_INITIAL_DELAY * 2 ** (attempt - 1))
    return None
