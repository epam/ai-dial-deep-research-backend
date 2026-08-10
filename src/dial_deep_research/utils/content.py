"""Read LangChain message/chunk content, which may be a `str` or a list of blocks."""

from __future__ import annotations

from typing import Any, TypeGuard


def is_image_block(block: Any) -> TypeGuard[dict[str, Any]]:
    """True for a LangChain v1 image content block.

    Dict-only on purpose: the MCP adapter builds these blocks as `TypedDict`s, and a
    round-trip through `custom_content.state` is JSON, so they stay dicts either way.
    A `TypeGuard` so callers that go on to read the block keep their dict narrowing.
    """
    return isinstance(block, dict) and block.get("type") == "image"


def count_image_blocks(content: Any) -> int:
    """Number of image blocks in message content; 0 when content is not a list."""
    if not isinstance(content, list):
        return 0
    return sum(1 for block in content if is_image_block(block))


def count_words(text: str) -> int:
    """Word count as whitespace-separated tokens.

    The primitive every length in the app is built from. It counts Markdown syntax as words
    (every table pipe, heading hash and bullet dash), so it overstates prose length by an
    amount that grows with how many tables a text carries. A report's length is this count
    over a reduced text — see `count_report_words`, which is what the word ceiling bounds.
    """
    return len(text.split())


def extract_text_from_content(content: Any) -> str:
    """Flatten message content to plain text, keeping only `text`-typed blocks.

    `content` may be `None`, a bare `str`, or a list of content blocks. For a
    list, the `text` payload of every `text`-typed block is concatenated and all
    other block types (thinking, image, tool-use, unknown) are dropped — so
    reasoning/structured blocks never leak into user-visible output.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = _block_text(block)
            if text is not None:
                parts.append(text)
        return "".join(parts)
    return str(content)


def _block_text(block: Any) -> str | None:
    """Return a block's text if it is a `text`-typed block, else `None`.

    Handles both dict-style blocks (LiteLLM/JSON shape) and attribute-style
    blocks (Pydantic content-block objects); both must carry `type == "text"`.
    """
    if isinstance(block, dict):
        block_type = block.get("type")
        value = block.get("text")
    else:
        block_type = getattr(block, "type", None)
        value = getattr(block, "text", None)
    if block_type != "text":
        return None
    return value if isinstance(value, str) else None
