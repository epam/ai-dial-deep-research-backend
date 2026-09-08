"""DIAL chat completion for the inline-citations demo.

It ignores what the user wrote and answers with a fixed report whose every paragraph demonstrates
one behaviour of the citation step (see `report.py`). It reads no application properties, runs no
research and calls no model, so a reader can check how a client renders a citation without
waiting for a research turn and without a live retrieval server.

Everything decidable from the text — the marker parsing, the run folding, the hyperlink removal,
the tag replacement, the payload and its emission — is the shared citation code
(`app/research/citations.py` and `utils/dial_annotations.py`). The one deliberate difference is
where the file URLs come from: the demo cites the PDFs the caller attached, while a research turn
will ask the configured file-sharing tool for them (see `attachments.py`).

Registered only when `ENABLE_ANNOTATIONS_DEMO` is set.
"""

from __future__ import annotations

import logging
import time

import httpx
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response

from dial_deep_research.app.annotations_demo.attachments import resolve_documents
from dial_deep_research.app.annotations_demo.report import demo_report
from dial_deep_research.app.research.citations import (
    cited_document_ids,
    convert_citations,
    log_citations_resolved,
    remove_hyperlinks,
)
from dial_deep_research.app.turn_lifecycle import run_logged_turn
from dial_deep_research.app_properties import ANNOTATIONS_DEMO_DEPLOYMENT_NAME
from dial_deep_research.utils.dial_annotations import send_annotations

_log = logging.getLogger(__name__)


class AnnotationsDemoCompletion(ChatCompletion):
    """Replies with the fixed report, its citations converted and its annotations emitted."""

    async def chat_completion(self, request: Request, response: Response) -> None:
        await run_logged_turn(
            deployment=ANNOTATIONS_DEMO_DEPLOYMENT_NAME,
            request=request,
            response=response,
            run_turn=self._run_turn,
        )

    async def _run_turn(self, request: Request, choice: Choice) -> None:
        started_at = time.monotonic()

        # The same order the research turn's delivery step will use: the links go first, then the
        # citations are read out of the text that pass produced.
        without_links = remove_hyperlinks(demo_report())
        document_ids = cited_document_ids(without_links.text)

        async with httpx.AsyncClient() as client:
            document_urls = await resolve_documents(request=request, client=client)

        converted = convert_citations(without_links.text, document_urls=document_urls)
        choice.append_content(converted.text)
        send_annotations(choice=choice, annotations=converted.annotations)

        log_citations_resolved(
            _log,
            documents_requested=len(document_ids),
            documents_resolved=len(document_urls),
            annotations=len(converted.annotations),
            markers_left=converted.markers_left,
            hyperlinks_removed=without_links.removed,
            duration_seconds=time.monotonic() - started_at,
        )
