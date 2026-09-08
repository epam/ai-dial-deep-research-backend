"""The caller's PDF attachments, checked and paired with the documents the report cites.

The demo cites what the caller attached rather than files of its own. An attachment already
lives in the caller's storage, so its URL is one the caller can open and nothing has to be
copied anywhere: the annotation points straight at it.

Every reason an attachment cannot be used fails the turn with a message saying what to attach.
An incomplete demonstration would be read as the citation mechanism misbehaving, so the demo
says what is missing instead of answering with half its cases working.
"""

from __future__ import annotations

import logging
from io import BytesIO

import httpx
from aidial_sdk.chat_completion import Attachment, Request
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from dial_deep_research.app.annotations_demo.report import ATTACHED_DOCUMENT_IDS, MIN_PAGES
from dial_deep_research.app.error_resolution import AppConditionError
from dial_deep_research.app.research.citations import PDF_MIME_TYPE, is_pdf_url
from dial_deep_research.settings import settings

_log = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 60

_WANTED = len(ATTACHED_DOCUMENT_IDS)


class AnnotationsDemoUnavailableError(AppConditionError):
    """The demo cannot answer, because what the caller attached will not carry the report."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__()


def _how_to_call_the_demo(problem: str) -> str:
    return (
        f"{problem} Attach {_WANTED} PDF files of at least {MIN_PAGES} pages each and send any "
        "message. The demo cites them as documents 1 and 2; which file becomes which does not "
        "matter."
    )


async def resolve_documents(*, request: Request, client: httpx.AsyncClient) -> dict[int, str]:
    """The URL of each document the report cites an attachment for, by document id.

    Raises:
        AnnotationsDemoUnavailableError: if the last message carries fewer usable PDFs than the
            report needs, or if one of them has too few pages to hold the pages it cites.
    """
    headers = {"Api-Key": request.api_key_secret.get_secret_value()}
    attachments = _pdf_attachments(request)
    if len(attachments) < _WANTED:
        raise AnnotationsDemoUnavailableError(
            _how_to_call_the_demo(
                f"This demo needs {_WANTED} PDF attachments and your message carried "
                f"{len(attachments)}."
            )
        )

    urls: dict[int, str] = {}
    for document_id, attachment in zip(ATTACHED_DOCUMENT_IDS, attachments, strict=False):
        url = attachment.url
        assert url is not None  # _pdf_attachments keeps only attachments carrying a URL
        await _check_depth(attachment=attachment, url=url, client=client, headers=headers)
        urls[document_id] = url
    return urls


def _pdf_attachments(request: Request) -> list[Attachment]:
    """The attachments of the last message that a citation could point at.

    An attachment is kept only when it is a PDF, carries a URL rather than inline data, and that
    URL names a PDF — `convert_citations` reads the extension, so a URL it would reject has to be
    refused here instead of silently drawing no pill.
    """
    message = request.messages[-1]
    if message.custom_content is None or not message.custom_content.attachments:
        return []
    return [
        attachment
        for attachment in message.custom_content.attachments
        if attachment.type == PDF_MIME_TYPE and attachment.url and is_pdf_url(attachment.url)
    ]


async def _check_depth(
    *, attachment: Attachment, url: str, client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    """Fail the turn unless the attached PDF holds every page the report cites."""
    name = attachment.title or url.rsplit("/", 1)[-1]
    content = await _download(url=url, client=client, headers=headers)
    try:
        pages = len(PdfReader(BytesIO(content)).pages)
    except (PdfReadError, ValueError) as e:
        raise AnnotationsDemoUnavailableError(
            _how_to_call_the_demo(f"The attachment `{name}` could not be read as a PDF.")
        ) from e
    if pages < MIN_PAGES:
        raise AnnotationsDemoUnavailableError(
            _how_to_call_the_demo(
                f"The attachment `{name}` has {pages} page(s), and the report cites page "
                f"{MIN_PAGES}."
            )
        )


async def _download(*, url: str, client: httpx.AsyncClient, headers: dict[str, str]) -> bytes:
    """The attachment's bytes, read with the per-request key the caller's request carries."""
    dial_url = settings.dial_url.encoded_string().rstrip("/")
    absolute = url if url.startswith(("http://", "https://")) else f"{dial_url}/v1/{url}"
    response = await client.get(absolute, headers=headers, timeout=_DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    return response.content
