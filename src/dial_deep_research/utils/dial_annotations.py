"""Sending `custom_content.annotations` on an open DIAL choice.

The one place the annotations chunk is built, so the research turn and the annotations demo
cannot emit different shapes. The array goes out once, after the report text has been appended,
as a single streamed delta on the same choice while it is still open.
"""

from __future__ import annotations

from collections.abc import Sequence

from aidial_sdk.chat_completion import Choice

# Unexported import path: `ArbitraryChunk` and its `BaseChunk` are outside `aidial_sdk`'s
# `__all__`, so this could change without deprecation. It is used because the SDK has no
# annotations API, and this is the same mechanism its own state and attachment chunks go out
# through. The alternative, `choice.add_attachment`, assigns attachment indices from its own
# counter and would renumber the annotations.
from aidial_sdk.chat_completion.chunks import ArbitraryChunk

from dial_deep_research.app.research.citations import Annotation


def send_annotations(*, choice: Choice, annotations: Sequence[Annotation]) -> None:
    """Emit the annotations array as one delta on `choice`.

    Called after the report content has been appended. The client resolves annotations only once
    the message has finished streaming, hiding every marker tag until then. On the finished
    message a tag an annotation claims becomes a pill, and a tag no annotation claims is rendered
    as literal text.
    """
    choice.send_chunk(
        ArbitraryChunk(
            {
                "choices": [
                    {
                        "index": choice.index,
                        "finish_reason": None,
                        "delta": {
                            "custom_content": {
                                "annotations": [
                                    annotation.model_dump() for annotation in annotations
                                ]
                            }
                        },
                    }
                ],
                "usage": None,
            }
        )
    )
