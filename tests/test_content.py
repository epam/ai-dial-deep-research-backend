"""Unit tests for reading message content and for the one word-count definition.

`count_words` is what every length statement in the report loop is measured with — the
prompts, the review stage, the log records and the over-ceiling routing gate — so its
definition is pinned here: whitespace-separated tokens, Markdown syntax included.
"""

from __future__ import annotations

from types import SimpleNamespace

from dial_deep_research.utils.content import (
    count_image_blocks,
    count_words,
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


def test_count_words_counts_whitespace_separated_tokens() -> None:
    # Runs of spaces, newlines and tabs all separate exactly one word from the next.
    assert count_words("one two  three\nfour\tfive\n\nsix") == 6


def test_count_words_of_text_without_words_is_zero() -> None:
    assert count_words("") == 0
    assert count_words("   \n\t ") == 0


def test_count_words_counts_markdown_syntax_as_words() -> None:
    # Deliberate: the count overstates prose length, most of all for tables. Every caller
    # measures the same way, so the prompt, the stage and the log agree on the number.
    assert count_words("## Key Findings") == 3
    assert count_words("| doc id | title |\n| --- | --- |") == 11
    assert count_words("- a bullet") == 3


def test_count_image_blocks() -> None:
    assert count_image_blocks([{"type": "image"}, {"type": "text"}, {"type": "image"}]) == 2
    assert count_image_blocks([]) == 0
    # Non-list content (a bare string, or None) carries no blocks at all.
    assert count_image_blocks("plain text") == 0
    assert count_image_blocks(None) == 0
