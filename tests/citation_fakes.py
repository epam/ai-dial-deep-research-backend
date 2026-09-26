"""Citation lookups for tests that build the report rules or nodes but check no identifier."""

from __future__ import annotations

from typing import cast

from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.app.research.citation_lookups import CitationLookups
from dial_deep_research.app.research.data_queries import DataQueryStore


def no_lookups(data_queries: DataQueryStore | None = None) -> CitationLookups:
    """Lookups of a channel with no dataset or document server: every identifier rule is silent."""
    return CitationLookups(
        dataset_tool=None,
        client=cast(MultiServerMCPClient, None),
        document_source=None,
        data_queries=data_queries or DataQueryStore(),
    )
