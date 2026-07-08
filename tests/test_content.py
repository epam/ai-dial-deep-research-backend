"""extract_text_from_content unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from dial_deep_research.utils.content import extract_text_from_content


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
