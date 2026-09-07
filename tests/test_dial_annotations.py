"""Emitting `custom_content.annotations` on an open choice.

What is protected here: the chunk's shape, which no typed SDK API covers, and that one helper is
the only place it is built — a second builder could drift from this one and would only be caught
by a human looking at a rendered reply.
"""

from __future__ import annotations

from pathlib import Path

from dial_deep_research.app.research.citations import convert_citations
from dial_deep_research.utils.dial_annotations import send_annotations

from .dial_spies import ChoiceSpy

_SRC = Path(__file__).resolve().parent.parent / "src"


def _annotations():
    converted = convert_citations(
        "A claim. [doc 101, page 3]",
        document_urls={101: "files/bucket/appdata/deep-research/doc-101.pdf"},
        make_tag_id=lambda: "tag-0",
    )
    return converted.annotations


def test_the_array_goes_out_as_one_delta_on_the_open_choice() -> None:
    choice = ChoiceSpy()

    send_annotations(choice=choice, annotations=_annotations())

    assert len(choice.chunks) == 1
    assert choice.chunks[0] == {
        "choices": [
            {
                "index": 0,
                "finish_reason": None,
                "delta": {
                    "custom_content": {
                        "annotations": [
                            {
                                "index": 0,
                                "target": {
                                    "selector": {
                                        "type": "html_tag",
                                        "tag": "cit",
                                        "id": "tag-0",
                                    }
                                },
                                "body": {
                                    "title": "doc 101, page 3",
                                    "source": {
                                        "type": "attachment",
                                        "attachment": {
                                            "type": "application/pdf",
                                            "url": (
                                                "files/bucket/appdata/deep-research/doc-101.pdf"
                                            ),
                                            "title": "doc 101, page 3",
                                        },
                                    },
                                    "selector": {
                                        "type": "pdf_bbox",
                                        "page": 3,
                                        "x1": 0,
                                        "y1": 0,
                                        "x2": 0,
                                        "y2": 0,
                                    },
                                },
                            }
                        ]
                    }
                },
            }
        ],
        "usage": None,
    }


def test_an_empty_array_is_still_a_well_formed_chunk() -> None:
    choice = ChoiceSpy()

    send_annotations(choice=choice, annotations=[])

    assert choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"] == []


def test_the_helper_is_the_only_place_that_builds_the_chunk() -> None:
    users = sorted(
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "ArbitraryChunk" in path.read_text()
    )
    assert users == ["dial_deep_research/utils/dial_annotations.py"]
