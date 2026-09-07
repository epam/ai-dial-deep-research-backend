"""DIAL chat completion for the inline-citations demo.

It ignores the user's message and answers with a fixed report whose every paragraph demonstrates
one behaviour of the citation step (see `report.py`). It reads no application properties, runs no
research and calls no model, so a reader can check how a client renders a citation without
waiting for a research turn and without a live retrieval server.

Everything decidable from the text — the marker parsing, the run folding, the hyperlink removal,
the tag replacement, the payload and its emission — is the code a research turn runs
(`app/research/citations.py` and `utils/dial_annotations.py`). The one deliberate difference is
where the file URLs come from: the demo copies its own fixtures into the caller's `appdata`
folder instead of calling a configured file-sharing tool (see `dial_files.py`).

Registered only when `ENABLE_ANNOTATIONS_DEMO` is set.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response

from dial_deep_research.app.annotations_demo.dial_files import DialFiles
from dial_deep_research.app.annotations_demo.report import (
    FIXTURES,
    FIXTURES_DIR,
    MIN_FIXTURE_PAGES,
    demo_report,
)
from dial_deep_research.app.error_resolution import AppConditionError
from dial_deep_research.app.research.citations import (
    cited_document_ids,
    convert_citations,
    log_citations_resolved,
    remove_hyperlinks,
)
from dial_deep_research.app.turn_lifecycle import run_logged_turn
from dial_deep_research.app_properties import ANNOTATIONS_DEMO_DEPLOYMENT_NAME
from dial_deep_research.settings import settings
from dial_deep_research.utils.dial_annotations import send_annotations

_log = logging.getLogger(__name__)

_NO_APPDATA_MESSAGE = (
    "This demo could not resolve the caller's appdata folder, so its cited files cannot be "
    "made readable for you. Call the demo through DIAL Core, which passes a per-request key; "
    "a direct call to the application with an ordinary api-key resolves no appdata folder."
)


class AnnotationsDemoUnavailableError(AppConditionError):
    """The demo cannot answer: a fixture is missing, or the request carried no per-request key.

    Both fail the turn on purpose. An incomplete demonstration would be read as the mechanism
    misbehaving, so the demo says what is missing instead.
    """

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__()


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

        # The same order the research turn's delivery step uses: the links go first, then the
        # citations are read out of the text that pass produced.
        without_links = remove_hyperlinks(demo_report())
        document_ids = cited_document_ids(without_links.text)

        async with httpx.AsyncClient() as client:
            document_urls = await self._share_fixtures(
                request=request, client=client, document_ids=document_ids
            )

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

    @staticmethod
    async def _share_fixtures(
        *, request: Request, client: httpx.AsyncClient, document_ids: list[int]
    ) -> dict[int, str]:
        """Copy the fixture of each cited document into the caller's appdata folder.

        A cited document with no fixture — the report cites one on purpose — is simply absent
        from the result, which is what the citation step reads as "no URL resolved for it".

        Raises:
            AnnotationsDemoUnavailableError: if the request carried no per-request key, or if a
                fixture file is missing from its expected location.
        """
        files = DialFiles(
            dial_url=settings.dial_url.encoded_string(),
            api_key=request.api_key_secret.get_secret_value(),
            client=client,
        )
        buckets = await files.get_bucket_ids()
        if buckets.appdata is None:
            raise AnnotationsDemoUnavailableError(_NO_APPDATA_MESSAGE)

        urls: dict[int, str] = {}
        for document_id in document_ids:
            file_name = FIXTURES.get(document_id)
            if file_name is None:
                continue
            source = Path(FIXTURES_DIR) / file_name
            if not source.is_file():
                raise AnnotationsDemoUnavailableError(_missing_fixture_message(file_name))
            source_url = await files.seed_into_app_bucket(bucket=buckets.bucket, source=source)
            urls[document_id] = await files.copy_to_caller(
                source_url=source_url, appdata=buckets.appdata, name=file_name
            )
        return urls


def _missing_fixture_message(file_name: str) -> str:
    return (
        f"This demo needs the file `{file_name}`, which is missing. Put a PDF of at least "
        f"{MIN_FIXTURE_PAGES} pages at `{FIXTURES_DIR}/{file_name}` in the application's "
        "working directory and call the demo again. The fixtures are kept out of git, so each "
        "checkout supplies its own."
    )
