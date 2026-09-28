"""The glossary part of the data-sources fetch: the terms, their definitions, and the rendering.

The list-terms tool is called with up to three attempts. The definitions of the listed terms are
then requested from the term-definitions tool in batches no larger than the configured limit, all
batches of one round at once, in at most three rounds: each later round re-requests the terms the
round before left unresolved. What the models see is one string, `Glossary terms:` and a one-line
JSON array with a record per listed term (see the data-sources-discovery capability).

A term is matched by its trimmed, case-folded name, which is how the server looks a term up too.
The records are rendered from the raw answers, so every field the server sends reaches the prompt
in the server's order.

The log records carry counts and failure kinds only: a term name and a definition are the
client's content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dial_deep_research.app.data_source_calls import (
    CallFailedError,
    InvalidResultError,
    call_once,
    call_with_attempts,
    pause_before_retry,
)
from dial_deep_research.app_properties import GlossaryTools

logger = logging.getLogger(__name__)

GLOSSARY_HEADING = "Glossary terms:"
GLOSSARY_LIST_FAILED_TEXT = "failed to obtain list of terms"

# Definition rounds: the first requests every listed term, each later one the terms still missing.
MAX_DEFINITION_ROUNDS = 3


def normalize_term(name: str) -> str:
    """A term's name as it is matched: surrounding whitespace trimmed, then case-folded."""
    return name.strip().casefold()


class _TermRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    term: str


class _TermList(BaseModel):
    model_config = ConfigDict(extra="allow")

    terms: list[_TermRecord]


class _DefinitionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    term: str
    definition: str


class _Definitions(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    definitions: list[_DefinitionRecord]
    not_found: list[str] | None = Field(default=None, alias="notFound")


def read_term_list(structured: Any) -> list[dict[str, Any]]:
    """The list-terms answer's records as the server sent them, once their shape is checked.

    Raises `InvalidResultError` for an answer without a `terms` array of records with a `term` string.
    """
    try:
        _TermList.model_validate(structured)
    except ValidationError as error:
        raise InvalidResultError() from error
    return list(structured["terms"])


def read_definitions(structured: Any) -> list[dict[str, Any]]:
    """The term-definitions answer's records as the server sent them, once their shape is checked.

    `notFound` is checked but not returned: a term it names is simply one the answer does not
    resolve, which is also true of a term the answer names nowhere.

    Raises `InvalidResultError` for an answer without a `definitions` array of records with `term` and
    `definition` strings, or with a `notFound` that is not a list of strings.
    """
    try:
        _Definitions.model_validate(structured)
    except ValidationError as error:
        raise InvalidResultError() from error
    return list(structured["definitions"])


class GlossaryFetch(BaseModel):
    """The glossary part's result: the rendered string, and what the rest of the turn reads.

    `records` is one record per listed term, in list order: its definitions record when the term
    resolved, and its list-terms record otherwise. `None` when the list failed. The References
    section's glossary table reads it.
    """

    text: str
    records: list[dict[str, Any]] | None
    unresolved: int = 0

    @property
    def listed(self) -> int | None:
        """How many terms the list reported, or `None` when the list failed."""
        return None if self.records is None else len(self.records)


def render_glossary(
    listed: Sequence[dict[str, Any]] | None, *, resolved: dict[str, dict[str, Any]]
) -> str:
    """`Glossary terms:` and the one-line JSON array, or the failure text for a failed list.

    Each object starts with its 1-based `index`. A resolved term carries its definitions record's
    fields; an unresolved one its list-terms record's, with `"definition": null` after `term`.
    """
    if listed is None:
        return f"{GLOSSARY_HEADING}\n{GLOSSARY_LIST_FAILED_TEXT}"
    rendered: list[dict[str, Any]] = []
    for index, record in enumerate(listed, start=1):
        definition = resolved.get(normalize_term(record["term"]))
        fields = definition if definition is not None else _with_null_definition(record)
        rendered.append({"index": index, **{k: v for k, v in fields.items() if k != "index"}})
    return f"{GLOSSARY_HEADING}\n{json.dumps(rendered, ensure_ascii=False)}"


def _with_null_definition(record: dict[str, Any]) -> dict[str, Any]:
    """The list-terms record with `"definition": null` directly after `term`."""
    fields: dict[str, Any] = {}
    for key, value in record.items():
        if key == "definition":
            continue
        fields[key] = value
        if key == "term":
            fields["definition"] = None
    return fields


async def fetch_glossary(
    client: MultiServerMCPClient, *, server_name: str, tools: GlossaryTools
) -> GlossaryFetch:
    """Fetch and render the glossary. No failure raises: a failed list becomes its failure text,
    and a term that did not resolve stays listed without a definition. Cancellation propagates."""
    started_at = time.monotonic()
    listing = await call_with_attempts(
        client,
        server_name=server_name,
        tool_name=tools.list_terms_tool,
        arguments={},
        read=read_term_list,
    )
    if listing.value is None:
        logger.warning(
            "Glossary terms could not be listed: server=%s failure=%s attempts=%d",
            server_name,
            listing.failure_kind,
            listing.attempts,
        )
        _log_fetched(
            server_name=server_name,
            list_attempts=listing.attempts,
            listed=None,
            resolved=0,
            unresolved=0,
            rounds=0,
            started_at=started_at,
        )
        return GlossaryFetch(text=render_glossary(None, resolved={}), records=None)

    listed = listing.value
    resolved, rounds = await _resolve_definitions(
        client, server_name=server_name, tools=tools, names=[r["term"] for r in listed]
    )
    records = [resolved.get(normalize_term(record["term"]), record) for record in listed]
    unresolved = sum(1 for record in listed if normalize_term(record["term"]) not in resolved)
    if unresolved:
        logger.warning(
            "Glossary terms left without a definition: server=%s unresolved=%d",
            server_name,
            unresolved,
        )
    _log_fetched(
        server_name=server_name,
        list_attempts=listing.attempts,
        listed=len(listed),
        resolved=len(listed) - unresolved,
        unresolved=unresolved,
        rounds=rounds,
        started_at=started_at,
    )
    return GlossaryFetch(
        text=render_glossary(listed, resolved=resolved), records=records, unresolved=unresolved
    )


async def _resolve_definitions(
    client: MultiServerMCPClient, *, server_name: str, tools: GlossaryTools, names: Sequence[str]
) -> tuple[dict[str, dict[str, Any]], int]:
    """The definitions record of every term that resolved, by normalized name, and the rounds run.

    Names are deduplicated by their normalized form before batching, so two listed spellings of one
    term are requested once and resolve together.
    """
    pending: dict[str, str] = {}
    for name in names:
        pending.setdefault(normalize_term(name), name)
    resolved: dict[str, dict[str, Any]] = {}
    rounds = 0
    while pending and rounds < MAX_DEFINITION_ROUNDS:
        if rounds:
            await pause_before_retry(rounds - 1)
        rounds += 1
        requested = list(pending.items())
        size = tools.max_terms_per_definitions_call
        batches = [requested[i : i + size] for i in range(0, len(requested), size)]
        answers = await asyncio.gather(
            *(
                _request_batch(client, server_name=server_name, tools=tools, batch=batch)
                for batch in batches
            )
        )
        for answer in answers:
            resolved.update(answer)
        pending = {norm: name for norm, name in pending.items() if norm not in resolved}
    return resolved, rounds


async def _request_batch(
    client: MultiServerMCPClient,
    *,
    server_name: str,
    tools: GlossaryTools,
    batch: Sequence[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """The records of one batch call that match a term it requested, by normalized name.

    A failed call resolves nothing, and a record matching no requested term is ignored.
    """
    try:
        definitions = await call_once(
            client,
            server_name=server_name,
            tool_name=tools.definitions_tool,
            arguments={"terms": [name for _, name in batch]},
            read=read_definitions,
        )
    except CallFailedError:
        return {}
    requested = {norm for norm, _ in batch}
    matched: dict[str, dict[str, Any]] = {}
    for record in definitions:
        norm = normalize_term(record["term"])
        if norm in requested:
            matched.setdefault(norm, record)
    return matched


def _log_fetched(
    *,
    server_name: str,
    list_attempts: int,
    listed: int | None,
    resolved: int,
    unresolved: int,
    rounds: int,
    started_at: float,
) -> None:
    logger.info(
        "Glossary fetched: server=%s list_attempts=%d listed=%s resolved=%d unresolved=%d "
        "rounds=%d duration=%.1fs",
        server_name,
        list_attempts,
        listed,
        resolved,
        unresolved,
        rounds,
        time.monotonic() - started_at,
    )
