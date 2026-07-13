"""Flatten LangChain message/chunk content (str or list-of-blocks) to plain text."""

from __future__ import annotations

from typing import Any


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
