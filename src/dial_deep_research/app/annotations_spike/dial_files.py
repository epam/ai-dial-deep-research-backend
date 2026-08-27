"""Make a cited document readable by the person who asked the question.

A citation may only point at a file in the **caller's** bucket, under `appdata/{deployment-id}`.
A file in the application's own bucket is not readable by the caller, and clicking its pill fails
with HTTP 403.

This mirrors what Generic RAG does on its chat-completion path (`DialClient.copy_file_to_user`):
resolve the caller's `appdata` folder from `GET /v1/bucket` with the per-request key, then copy
the document there with `POST /v1/ops/resource/copy` — a server-side copy, so the bytes never pass
through this application. The copy is skipped when source and destination already have the same
etag, which makes a repeated citation of the same document cost two metadata calls and no
transfer.

The spike also seeds its source documents into the application bucket on first use, standing in
for the indexing step that would have put them there in production.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from pydantic import BaseModel

_log = logging.getLogger(__name__)

PDF_MIME_TYPE = "application/pdf"


class BucketIds(BaseModel):
    """The two storage locations a per-request key resolves to.

    `bucket` is the application's own bucket. `appdata` is a folder inside the **caller's**
    bucket that the application may write to; it is present only for a per-request key.
    """

    bucket: str
    appdata: str | None = None


class DialFiles:
    """The subset of the DIAL file API the spike needs, authenticated per request."""

    def __init__(self, *, dial_url: str, api_key: str, client: httpx.AsyncClient):
        self._dial_url = dial_url.rstrip("/")
        self._headers = {"Api-Key": api_key}
        self._client = client

    async def get_bucket_ids(self) -> BucketIds:
        response = await self._client.get(
            f"{self._dial_url}/v1/bucket", headers=self._headers, timeout=30
        )
        response.raise_for_status()
        return BucketIds.model_validate(response.json())

    async def get_etag(self, url: str) -> str | None:
        """The file's etag, or None when it does not exist."""
        response = await self._client.get(
            f"{self._dial_url}/v1/metadata/{url}", headers=self._headers, timeout=30
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json().get("etag")

    async def upload(self, *, url: str, source: Path) -> None:
        with source.open("rb") as handle:
            response = await self._client.put(
                f"{self._dial_url}/v1/{url}",
                headers=self._headers,
                files={"file": (source.name, handle, PDF_MIME_TYPE)},
                timeout=300,
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
            timeout=300,
        )
        response.raise_for_status()

    async def seed_into_app_bucket(self, *, bucket: str, source: Path) -> str:
        """Put a local document into the application bucket, standing in for indexing.

        Returns the document's DIAL path. Uploads only when the document is not already there.
        """
        url = f"files/{bucket}/{source.name}"
        if await self.get_etag(url) is None:
            _log.info("Seeding spike document into the app bucket: %s", source.name)
            await self.upload(url=url, source=source)
        return url

    async def copy_to_caller(self, *, source_url: str, appdata: str, name: str) -> str:
        """Copy a document into the caller's appdata folder and return its path there.

        Raises:
            RuntimeError: if the caller's appdata folder is unknown, which means the request did
                not carry a per-request key.
        """
        destination_url = f"files/{appdata}/{name}"

        source_etag = await self.get_etag(source_url)
        destination_etag = await self.get_etag(destination_url)
        if source_etag is None or source_etag != destination_etag:
            _log.info("Copying cited document to the caller: %s", name)
            await self.copy(source_url=source_url, destination_url=destination_url)

        return destination_url
