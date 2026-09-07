"""Make the demo's fixture PDFs readable by the person who asked the question.

A citation may only point at a file in the **caller's** bucket, under `appdata/{deployment-id}`:
DIAL Core grants a user session access only to resources in that user's own bucket, so a pill
pointing at a file in the application's bucket fails with HTTP 403 for everyone but the
application.

This is the one place the demo differs from a research turn. There the retrieval server's
file-sharing tool performs the copy and returns the URL; here the demo ships the files and copies
them itself, so its reply is the same on every environment and depends on no live server. The
route is the same one Generic RAG uses on its own chat-completion path: resolve the caller's
`appdata` folder from `GET /v1/bucket` with the per-request key, then copy the file there with
`POST /v1/ops/resource/copy` — a server-side copy, so the bytes never pass through this
application. The copy is skipped when source and destination already carry the same etag, which
makes every turn after the first cost two metadata calls and no transfer.

The fixtures are seeded into the application's own bucket on first use, standing in for the
indexing step that would have put a real document there.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from pydantic import BaseModel

_log = logging.getLogger(__name__)

PDF_MIME_TYPE = "application/pdf"

_METADATA_TIMEOUT = 30
_TRANSFER_TIMEOUT = 300


class BucketIds(BaseModel):
    """The two storage locations a per-request key resolves to.

    `bucket` is the application's own bucket. `appdata` is the folder inside the **caller's**
    bucket that the application may write to; DIAL Core reports it only for a per-request key.
    """

    bucket: str
    appdata: str | None = None


class DialFiles:
    """The subset of the DIAL file API the demo needs, authenticated per request."""

    def __init__(self, *, dial_url: str, api_key: str, client: httpx.AsyncClient):
        self._dial_url = dial_url.rstrip("/")
        self._headers = {"Api-Key": api_key}
        self._client = client

    async def get_bucket_ids(self) -> BucketIds:
        response = await self._client.get(
            f"{self._dial_url}/v1/bucket", headers=self._headers, timeout=_METADATA_TIMEOUT
        )
        response.raise_for_status()
        return BucketIds.model_validate(response.json())

    async def get_etag(self, url: str) -> str | None:
        """The file's etag, or None when it does not exist."""
        response = await self._client.get(
            f"{self._dial_url}/v1/metadata/{url}",
            headers=self._headers,
            timeout=_METADATA_TIMEOUT,
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        etag = response.json().get("etag")
        return str(etag) if etag is not None else None

    async def upload(self, *, url: str, source: Path) -> None:
        with source.open("rb") as handle:
            response = await self._client.put(
                f"{self._dial_url}/v1/{url}",
                headers=self._headers,
                files={"file": (source.name, handle, PDF_MIME_TYPE)},
                timeout=_TRANSFER_TIMEOUT,
            )
        response.raise_for_status()

    async def copy(self, *, source_url: str, destination_url: str) -> None:
        response = await self._client.post(
            f"{self._dial_url}/v1/ops/resource/copy",
            headers=self._headers,
            json={
                "sourceUrl": source_url,
                "destinationUrl": destination_url,
                "overwrite": True,
            },
            timeout=_TRANSFER_TIMEOUT,
        )
        response.raise_for_status()

    async def seed_into_app_bucket(self, *, bucket: str, source: Path) -> str:
        """Put a fixture into the application bucket, standing in for indexing.

        Returns the fixture's DIAL path. Uploads only when it is not already there.
        """
        url = f"files/{bucket}/{source.name}"
        if await self.get_etag(url) is None:
            _log.debug("Seeding the demo fixture into the app bucket: %s", source.name)
            await self.upload(url=url, source=source)
        return url

    async def copy_to_caller(self, *, source_url: str, appdata: str, name: str) -> str:
        """Copy a fixture into the caller's appdata folder and return its path there."""
        destination_url = f"files/{appdata}/{name}"

        source_etag = await self.get_etag(source_url)
        destination_etag = await self.get_etag(destination_url)
        if source_etag is None or source_etag != destination_etag:
            _log.debug("Copying the demo fixture to the caller: %s", name)
            await self.copy(source_url=source_url, destination_url=destination_url)

        return destination_url
