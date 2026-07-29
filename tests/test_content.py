"""extract_text_from_content unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from dial_deep_research.utils.content import (
    count_image_blocks,
    extract_text_from_content,
    is_image_block,
)


def test_attribute_style_text_block_extracted() -> None:
    block = SimpleNamespace(type="text", text="hello")
    assert extract_text_from_content([block]) == "hello"


def test_attribute_style_non_text_block_skipped() -> None:
    text = SimpleNamespace(type="text", text="visible")
    thinking = SimpleNamespace(type="thinking", text="<hidden>")
    image = SimpleNamespace(type="image", text=None)
    assert extract_text_from_content([text, thinking, image]) == "visible"


def test_dict_text_block_requires_explicit_type() -> None:
    untyped = {"text": "no type field, dropped"}
    typed = {"type": "text", "text": "kept"}
    assert extract_text_from_content([untyped, typed]) == "kept"


def test_is_image_block() -> None:
    assert is_image_block({"type": "image", "base64": "aGk="})
    assert not is_image_block({"type": "text", "text": "x"})
    assert not is_image_block("a bare string")
    # Attribute-style blocks are out of scope: every producer we read emits dicts.
    assert not is_image_block(SimpleNamespace(type="image"))


def test_count_image_blocks() -> None:
    assert count_image_blocks([{"type": "image"}, {"type": "text"}, {"type": "image"}]) == 2
    assert count_image_blocks([]) == 0
    # Non-list content (a bare string, or None) carries no blocks at all.
    assert count_image_blocks("plain text") == 0
    assert count_image_blocks(None) == 0
