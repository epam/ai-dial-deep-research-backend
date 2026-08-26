"""DIAL chat completion for the inline-annotations spike.

Ignores the user's message and replies with a fixed report citing two PDFs, so the rendering of
inline citation pills can be exercised without running a real research turn. Local only: the
deployment is registered when `ENABLE_ANNOTATIONS_SPIKE` is set.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from aidial_sdk.chat_completion.chunks import ArbitraryChunk

from dial_deep_research.app.annotations_spike.annotations import (
    SpikePdf,
    build_annotations,
    build_citations,
    build_reference_attachments,
)
from dial_deep_research.app.annotations_spike.report import build_report

_log = logging.getLogger(__name__)

# Written by `scripts/upload_spike_pdfs.py`, which uploads the two papers to DIAL file storage
# and records the paths it got back. Read per request so a re-upload needs no app restart.
_PDF_CONFIG_PATH = Path("data/annotations_spike_files.json")


class AnnotationsSpikeCompletion(ChatCompletion):
    """Replies with a fixed, citation-carrying report."""

    async def chat_completion(self, request: Request, response: Response) -> None:
        plan_pdf, scaling_pdf = self._load_pdfs()

        report = build_report()
        citations = build_citations(plan_pdf=plan_pdf, scaling_pdf=scaling_pdf)
        annotations = build_annotations(citations=citations, offsets=report.offsets)

        with response.create_single_choice() as choice:
            choice.append_content(report.text)
            self._send_annotations(choice=choice, annotations=annotations)

            # A markdown copy of the report, to see how the canvas renders it (it carries no
            # pills — annotation offsets index the message text, not an attachment).
            choice.add_attachment(
                type="text/markdown",
                title="Report (canvas copy)",
                data=report.text,
            )

            for attachment in build_reference_attachments(citations=citations):
                choice.add_attachment(**attachment)

        _log.info(
            "annotations spike replied report_chars=%d annotations=%d",
            len(report.text),
            len(annotations),
        )

    @staticmethod
    def _send_annotations(*, choice: Choice, annotations: list[dict]) -> None:
        """Emit `custom_content.annotations`.

        The DIAL SDK has no annotations API, so the delta is sent as a raw chunk. `send_chunk`
        is public and `ArbitraryChunk` forwards its dict unchanged, which is the same shape the
        SDK's own `StateChunk` and `AttachmentChunk` produce.
        """
        choice.send_chunk(
            ArbitraryChunk(
                {
                    "choices": [
                        {
                            "index": choice.index,
                            "finish_reason": None,
                            "delta": {"custom_content": {"annotations": annotations}},
                        }
                    ],
                    "usage": None,
                }
            )
        )

    @staticmethod
    def _load_pdfs() -> tuple[SpikePdf, SpikePdf]:
        """Read the uploaded PDFs' DIAL paths.

        Raises:
            FileNotFoundError: if the PDFs have not been uploaded yet.
        """
        if not _PDF_CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"{_PDF_CONFIG_PATH} is missing — run scripts/upload_spike_pdfs.py first"
            )

        config = json.loads(_PDF_CONFIG_PATH.read_text())
        return SpikePdf(**config["plan"]), SpikePdf(**config["scaling"])
