"""Image content blocks of a research record: placeholders, snapshot uploads and downloads.

The MCP→LangChain adapter emits image content as LangChain v1
`{type: "image", base64, mime_type}` blocks. Every later request carries the
states of all earlier turns, and DIAL Core rejects a request above its size
limit (64 MiB by default) with 413, so no state may keep image bytes.

Only a failed run's snapshot keeps its images, because a resume needs them: each one is uploaded
to the DIAL files API at save time, and its `base64` field is swapped for a `url` reference. A
resumed run downloads them again before it starts, so LLM endpoints still receive base64 image
blocks, not DIAL-internal URLs (`multimodal-tool-output`). Every image that is not stored, in a
completed run's record or after a failed upload, becomes a placeholder in its own slot, carrying
its MIME type and the SHA-256 of its bytes (see the research-resume spec).
"""

import asyncio
import base64
import hashlib
import logging
import mimetypes
import uuid
from collections.abc import Collection, Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aidial_client import AsyncDial, DialException, ResourceNotFoundError
from langchain_core.messages import BaseMessage, ToolMessage

from dial_deep_research.app.error_resolution import SnapshotImageUnavailableError
from dial_deep_research.utils.content import is_image_block

logger = logging.getLogger(__name__)

_BUCKET_PREFIX = "dial-deep-research"
_PLACEHOLDER_TEMPLATE = "[image not stored: {reason}, {mime_type}, sha256={digest}]"

REASON_SUCCESSFUL_RUN = "successful run"
REASON_UPLOAD_FAILED = "upload failed"

# Each retry waits twice as long as the one before: 1, 2, then 4 seconds.
_RETRY_INITIAL_DELAY = 1.0
_UPLOAD_ATTEMPTS = 4
_UPLOAD_RETRIED_STATUSES = frozenset({500, 502, 503, 504})
# Only these are likely to pass on the next attempt; `AsyncDial` already retries timeouts,
# transport errors and 429 inside each attempt.
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_RETRIED_STATUSES = frozenset({502, 503})


def _ext_for_mime(mime_type: str | None) -> str:
    if not mime_type:
        return "bin"
    ext = mimetypes.guess_extension(mime_type) or ""
    return ext.lstrip(".") or "bin"


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


def _inline_image_blocks(
    messages: list[BaseMessage],
) -> list[tuple[BaseMessage, int, dict[str, Any]]]:
    return [
        (msg, content_idx, block)
        for msg, content_idx, block in _iter_image_blocks(messages)
        if "base64" in block
    ]


def _placeholder(block: dict[str, Any], *, reason: str) -> dict[str, Any]:
    digest = hashlib.sha256(base64.b64decode(block["base64"])).hexdigest()
    return {
        "type": "text",
        "text": _PLACEHOLDER_TEMPLATE.format(
            reason=reason, mime_type=block.get("mime_type") or "unknown", digest=digest
        ),
    }


def _replace_block(msg: BaseMessage, content_idx: int, new_block: dict[str, Any]) -> None:
    if isinstance(msg.content, list):
        msg.content[content_idx] = new_block


def _message_owner_id(msg: BaseMessage) -> str:
    if isinstance(msg, ToolMessage) and msg.tool_call_id:
        return msg.tool_call_id
    return getattr(msg, "id", None) or f"msg-{uuid.uuid4()}"


def _is_retried(failure: Exception, statuses: Collection[int]) -> bool:
    return isinstance(failure, DialException) and failure.status_code in statuses


def replace_images_with_placeholders(messages: list[BaseMessage]) -> None:
    """Replace every image block carrying `base64` with the `successful run` placeholder.

    For a completed run's record: it makes no files call, so nothing on this path can fail.
    """
    for msg, content_idx, block in _inline_image_blocks(messages):
        _replace_block(msg, content_idx, _placeholder(block, reason=REASON_SUCCESSFUL_RUN))


async def upload_snapshot_images(messages: list[BaseMessage], dial: AsyncDial) -> int:
    """Upload every image block carrying `base64` and rewrite it to carry `url`; return how many
    images could not be stored.

    Bucket resolution: prefer `appdata`, fall back to `bucket`. The uploads run concurrently, and
    each is retried on HTTP 500, 502, 503 and 504. An image that still fails, and every image when
    the bucket lookup fails, is replaced by the `upload failed` placeholder, so the state never
    carries image bytes; the caller then marks the snapshot not resumable.
    """
    candidates = _inline_image_blocks(messages)
    if not candidates:
        return 0

    try:
        bucket_resp = await dial.bucket.get_raw()
    except Exception as lookup_error:
        logger.warning(
            "Files bucket lookup failed at the snapshot save; every image gets a placeholder: "
            "error=%s images=%d",
            type(lookup_error).__name__,
            len(candidates),
        )
        for msg, content_idx, block in candidates:
            _replace_block(msg, content_idx, _placeholder(block, reason=REASON_UPLOAD_FAILED))
        return len(candidates)
    bucket = bucket_resp.appdata or bucket_resp.bucket

    results = await asyncio.gather(
        *(
            _upload_with_retries(dial, bucket, msg, content_idx, block)
            for msg, content_idx, block in candidates
        )
    )
    not_stored = 0
    for (msg, content_idx, block), failure in zip(candidates, results, strict=True):
        if failure is None:
            continue
        not_stored += 1
        logger.warning(
            "Snapshot image upload failed after its last attempt; substituting a placeholder: "
            "mime=%s size=%dB error=%s",
            block.get("mime_type"),
            len(block["base64"]) * 3 // 4,
            type(failure).__name__,
        )
        _replace_block(msg, content_idx, _placeholder(block, reason=REASON_UPLOAD_FAILED))
    return not_stored


async def _upload_with_retries(
    dial: AsyncDial, bucket: str, msg: BaseMessage, content_idx: int, block: dict[str, Any]
) -> Exception | None:
    """Upload one snapshot image; the failure of its last attempt, or `None` on success."""
    for attempt in range(1, _UPLOAD_ATTEMPTS + 1):
        failure = await _upload_one(dial, bucket, msg, content_idx, block)
        if failure is None:
            return None
        if attempt == _UPLOAD_ATTEMPTS or not _is_retried(failure, _UPLOAD_RETRIED_STATUSES):
            return failure
        logger.warning(
            "Snapshot image upload failed; retrying: attempt=%d error=%s",
            attempt,
            type(failure).__name__,
        )
        await asyncio.sleep(_RETRY_INITIAL_DELAY * 2 ** (attempt - 1))
    return None


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
        # Read before the block changes, so a failed read leaves the block as it was.
        url = metadata.url
        block.pop("base64", None)
        block["url"] = url
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


async def download_snapshot_images(messages: list[BaseMessage], dial: AsyncDial) -> int:
    """Download every image block carrying only `url` back to `base64`; return how many images
    are gone (answered 404).

    The downloads run concurrently. A failed download never becomes a placeholder: a resumed
    research run would otherwise go on without an image research-agent already saw. HTTP 502
    and 503 are retried; a 404 is not, since the file is gone for good, and it is logged and
    counted, so the caller discards the snapshot. When no image is gone, an image that still
    fails raises `SnapshotImageUnavailableError`, which a later request may get past.
    """
    blocks = [
        block
        for _, _, block in _iter_image_blocks(messages)
        if "url" in block and "base64" not in block
    ]
    urls = [_strip_url_query(block["url"]) for block in blocks]
    results = await asyncio.gather(*(_download_with_retries(dial, block) for block in blocks))
    missing = 0
    for url, failure in zip(urls, results, strict=True):
        if isinstance(failure, ResourceNotFoundError):
            missing += 1
            logger.warning("Snapshot image is gone: url=%s", url)
    if missing:
        return missing
    failures = [failure for failure in results if failure is not None]
    if failures:
        raise SnapshotImageUnavailableError() from failures[0]
    return 0


async def _download_with_retries(dial: AsyncDial, block: dict[str, Any]) -> Exception | None:
    """Download one snapshot image; the failure of its last attempt, or `None` on success."""
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        failure = await _download_one(dial, block)
        if failure is None:
            return None
        if attempt == _DOWNLOAD_ATTEMPTS or not _is_retried(failure, _DOWNLOAD_RETRIED_STATUSES):
            return failure
        logger.warning(
            "Snapshot image download failed; retrying: attempt=%d error=%s url=%s",
            attempt,
            type(failure).__name__,
            _strip_url_query(block.get("url", "")),
        )
        await asyncio.sleep(_RETRY_INITIAL_DELAY * 2 ** (attempt - 1))
    return None


async def _download_one(dial: AsyncDial, block: dict[str, Any]) -> Exception | None:
    try:
        download = await dial.files.download(block["url"])
        raw = await download.aget_content()
        block.pop("url", None)
        block["base64"] = base64.b64encode(raw).decode()
    except Exception as exc:  # noqa: BLE001
        return exc
    return None
