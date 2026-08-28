"""DIAL chat completion for the inline-annotations spike.

Ignores the user's message and replies with a fixed report citing two PDFs, so the rendering of
inline citation pills can be exercised without running a real research turn. Local only: the
deployment is registered when `ENABLE_ANNOTATIONS_SPIKE` is set.

Document handling follows the production shape rather than the shortest path: the source PDFs
live in the application bucket, and each cited document is copied into the caller's appdata
folder before it is cited, so the pill points at a file the reader can actually open. See
`dial_files.py`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from aidial_sdk.chat_completion.chunks import ArbitraryChunk

from dial_deep_research.app.annotations_spike.annotations import (
    SpikePdf,
    build_annotations,
    build_citations,
)
from dial_deep_research.app.annotations_spike.dial_files import DialFiles
from dial_deep_research.app.annotations_spike.report import build_report
from dial_deep_research.settings import settings

_log = logging.getLogger(__name__)

# The two papers the spike cites, kept out of git under `data/`.
_DOCUMENTS_DIR = Path("data/annotations_spike")
_DOCUMENTS = {
    "plan": ("plan.pdf", "Learning When to Plan"),
    "scaling": ("scaling.pdf", "Scaling Test-Time Compute"),
}


class AnnotationsSpikeCompletion(ChatCompletion):
    """Replies with a fixed, citation-carrying report."""

    async def chat_completion(self, request: Request, response: Response) -> None:
        async with httpx.AsyncClient() as client:
            pdfs = await self._prepare_documents(request=request, client=client)

        # The report's markers are the resolved urls, so it can only be built once the documents
        # have been copied into the caller's bucket and their paths are known.
        report = build_report(
            plan_url=pdfs["plan"].url,
            scaling_url=pdfs["scaling"].url,
            solo_url=pdfs["plan_solo"].url,
            quote_url=pdfs["scaling_quote"].url,
        )
        citations = build_citations(
            plan_pdf=pdfs["plan"],
            scaling_pdf=pdfs["scaling"],
            solo_pdf=pdfs["plan_solo"],
            quote_pdf=pdfs["scaling_quote"],
        )
        annotations = build_annotations(citations=citations, markers=report.markers)

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

        _log.info(
            "annotations spike replied report_chars=%d annotations=%d",
            len(report.text),
            len(annotations),
        )

    @staticmethod
    async def _prepare_documents(
        *, request: Request, client: httpx.AsyncClient
    ) -> dict[str, SpikePdf]:
        """Seed the PDFs into the app bucket, then copy each into the caller's appdata folder.

        plan.pdf and scaling.pdf are each also copied a second time, under a different
        destination name, so the report can cite a document that shares no url with any other
        citation and therefore forms its own singleton pill group.

        Raises:
            FileNotFoundError: if a source PDF is missing from `data/annotations_spike/`.
            RuntimeError: if the request carried no per-request key, so the caller's appdata
                folder cannot be resolved.
        """
        files = DialFiles(
            dial_url=settings.dial_url.encoded_string(),
            api_key=request.api_key_secret.get_secret_value(),
            client=client,
        )
        bucket_ids = await files.get_bucket_ids()
        if bucket_ids.appdata is None:
            raise RuntimeError(
                "no appdata folder for this request — a citation can only point at a file in "
                "the caller's bucket, which needs a per-request key"
            )

        prepared: dict[str, SpikePdf] = {}
        app_bucket_urls: dict[str, str] = {}
        for key, (file_name, title) in _DOCUMENTS.items():
            source = _DOCUMENTS_DIR / file_name
            if not source.exists():
                raise FileNotFoundError(f"spike document is missing: {source}")

            source_url = await files.seed_into_app_bucket(bucket=bucket_ids.bucket, source=source)
            app_bucket_urls[key] = source_url
            shared_url = await files.copy_to_caller(
                source_url=source_url, appdata=bucket_ids.appdata, name=file_name
            )
            prepared[key] = SpikePdf(url=shared_url, title=title)

        # A second copy of plan.pdf, filed at a different destination name in the caller's
        # appdata folder — same paper, same bytes, a genuinely distinct url.
        solo_url = await files.copy_to_caller(
            source_url=app_bucket_urls["plan"], appdata=bucket_ids.appdata, name="plan-2.pdf"
        )
        prepared["plan_solo"] = SpikePdf(
            url=solo_url,
            title="Learning When to Plan",
            attachment_title="Learning When to Plan (copy)",
        )

        # A second copy of scaling.pdf, filed at yet another destination name — the singleton
        # citation that carries a real `body.quote`.
        quote_url = await files.copy_to_caller(
            source_url=app_bucket_urls["scaling"],
            appdata=bucket_ids.appdata,
            name="scaling-2.pdf",
        )
        prepared["scaling_quote"] = SpikePdf(
            url=quote_url,
            title="Scaling Test-Time Compute",
            attachment_title="Scaling Test-Time Compute (copy)",
        )

        return prepared

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
