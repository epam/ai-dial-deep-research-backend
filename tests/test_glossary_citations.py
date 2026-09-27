"""Glossary citations: the readable form a run's glossary markers become, the glossary table of
the References section, and the fixed order of its tables."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage

from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.glossary import GlossaryFetch
from dial_deep_research.app.research.citations import (
    DatasetSource,
    cited_glossary_terms,
    convert_citations,
    find_citation_markers,
)
from dial_deep_research.app.research.references import glossary_rows
from dial_deep_research.app.research.report_length import count_report_words
from dial_deep_research.app_properties import (
    ApplicationProperties,
    GlossaryTools,
    ServerGlossary,
)
from tests.test_report_delivery import _deliver, _make_runner, _settle

_WEO = "IMF:WEO(1.0.0)"
_DOTS = "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"
_SOURCES = {
    _WEO: DatasetSource(url="https://portal.example.org/weo", name="World Economic Outlook"),
    _DOTS: DatasetSource(url="https://portal.example.org/dots", name="Direction of Trade"),
}


def _tag_ids() -> Any:
    counter = iter(range(100))
    return lambda: f"t{next(counter)}"


def _convert(text: str, *, glossary: bool = True) -> Any:
    return convert_citations(
        text,
        document_urls={},
        dataset_sources=_SOURCES,
        make_tag_id=_tag_ids(),
        glossary=glossary,
    )


# --- the readable form -------------------------------------------------------------------------


def test_a_glossary_marker_is_delivered_in_the_readable_form() -> None:
    converted = _convert("Prices rose [glossary World Economic Outlook].")

    assert converted.text == "Prices rose (World Economic Outlook - glossary term)."
    assert converted.annotations == []
    assert converted.markers_left == 0


def test_a_glossary_marker_inside_a_run_does_not_split_the_pill() -> None:
    converted = _convert(
        f"… 2.9% [dataset {_WEO}] [glossary Primary Commodity Prices] [dataset {_DOTS}]."
    )

    assert converted.text == (
        '… 2.9% <cit data-id="t0"></cit> (Primary Commodity Prices - glossary term).'
    )
    assert len(converted.annotations) == 2


def test_several_glossary_terms_in_one_run_form_one_group() -> None:
    converted = _convert(
        "A fact [glossary World Economic Outlook] [glossary Primary Commodity Prices]"
        " [glossary world economic outlook ]."
    )

    assert converted.text == (
        'A fact ("World Economic Outlook", "Primary Commodity Prices" - glossary terms).'
    )


def test_the_keyword_is_read_case_insensitively() -> None:
    converted = _convert("A fact [Glossary  World Economic Outlook ].")

    assert converted.text == "A fact (World Economic Outlook - glossary term)."


def test_markers_that_keep_their_text_keep_their_separators() -> None:
    converted = _convert("A fact [dataset IMF:UNKNOWN], [glossary Term] [dataset IMF:OTHER].")

    assert (
        converted.text
        == "A fact [dataset IMF:UNKNOWN], [dataset IMF:OTHER] (Term - glossary term)."
    )
    assert converted.markers_left == 2


def test_a_channel_without_a_glossary_leaves_the_marker_as_text() -> None:
    text = f"A fact [dataset {_WEO}] [glossary World Economic Outlook] [dataset {_DOTS}]."

    converted = _convert(text, glossary=False)

    assert "[glossary World Economic Outlook]" in converted.text
    assert converted.text.count("<cit ") == 2, "the text splits the run, as written"
    assert find_citation_markers("[glossary X]") == []


def test_cited_terms_are_distinct_and_in_report_order() -> None:
    text = "[glossary B] then [glossary A] then [glossary  b ]"
    assert cited_glossary_terms(text) == ["B", "A"]


def test_a_glossary_marker_counts_as_an_inline_citation() -> None:
    assert count_report_words("Prices rose [glossary Primary Commodity Prices].") == 2


# --- the glossary table ------------------------------------------------------------------------


def test_the_record_comes_from_the_first_source_that_holds_one_with_a_definition() -> None:
    rows = glossary_rows(
        ["World Economic Outlook", "Primary Commodity Prices", "Market Outlook 2025"],
        sources=[
            [{"term": "World Economic Outlook", "definition": "From the fetch."}],
            [{"term": "WORLD ECONOMIC OUTLOOK", "definition": "From the agent."}],
            [
                {"term": "Primary Commodity Prices"},
                {"term": "primary commodity prices ", "definition": "Only here."},
            ],
        ],
    )

    assert [row.identifier for row in rows] == [
        "World Economic Outlook",
        "Primary Commodity Prices",
        "Market Outlook 2025",
    ]
    assert rows[0].fields["definition"] == "From the fetch."
    assert rows[1].fields["definition"] == "Only here."
    assert rows[2].fields == {}
    assert all(row.target is None for row in rows)


def test_a_record_with_a_definition_wins_over_an_earlier_one_without() -> None:
    rows = glossary_rows(
        ["Term"],
        sources=[[{"term": "Term", "definition": None}], [{"term": "Term", "definition": "Yes."}]],
    )
    assert rows[0].fields["definition"] == "Yes."


_GLOSSARY = ServerGlossary(
    server_name="datasets",
    tools=GlossaryTools.model_validate(
        {
            "list_terms_tool": "list_terms",
            "definitions_tool": "define_terms",
            "max_terms_per_definitions_call": 10,
            "references_table": {
                "title": "Glossary",
                "columns": [
                    {"heading": "Term", "key": "term"},
                    {"heading": "Definition", "key": "definition"},
                ],
            },
        }
    ),
)


def _data_sources(records: list[dict[str, Any]] | None) -> DataSources:
    return DataSources(
        text="The topics map.",
        glossary=GlossaryFetch(text="Glossary terms:\n...", records=records),
    )


async def test_a_report_citing_only_a_glossary_term_lists_it() -> None:
    runner, choice = _make_runner()
    _settle(runner, "## Overview\n\nPrices rose [glossary World Economic Outlook].")

    await _deliver(
        runner,
        configured_tool_name=None,
        glossary=_GLOSSARY,
        data_sources=_data_sources([{"term": "World Economic Outlook", "definition": "The WEO."}]),
    )

    assert "(World Economic Outlook - glossary term)." in choice.content
    assert choice.content.endswith(
        "## References\n\n### Glossary\n\n| Term | Definition |\n| --- | --- |\n"
        "| World Economic Outlook | The WEO. |"
    )


async def test_a_term_only_the_agent_resolved_takes_the_agents_definition() -> None:
    runner, choice = _make_runner()
    transcript = [
        HumanMessage(content="q"),
        ToolMessage(
            content="as JSON",
            artifact={
                "structured_content": {
                    "definitions": [
                        {"term": "Primary Commodity Prices", "definition": "Agent's definition."}
                    ]
                }
            },
            tool_call_id="c1",
            name="define_terms",
        ),
        ToolMessage(
            content="failed",
            artifact={
                "structured_content": {
                    "definitions": [{"term": "Primary Commodity Prices", "definition": "Wrong."}]
                }
            },
            tool_call_id="c2",
            name="define_terms",
            status="error",
        ),
    ]
    _settle(
        runner,
        "## Overview\n\nA fact [glossary Primary Commodity Prices] and [glossary Unknown Term].",
        transcript=transcript,
    )

    await _deliver(
        runner,
        configured_tool_name=None,
        glossary=_GLOSSARY,
        data_sources=_data_sources([{"term": "Primary Commodity Prices"}]),
    )

    assert "| Primary Commodity Prices | Agent's definition. |" in choice.content
    assert "| Unknown Term |  |" in choice.content
    assert "Wrong." not in choice.content


async def test_a_channel_without_a_glossary_has_no_glossary_table() -> None:
    runner, choice = _make_runner()
    _settle(runner, "## Overview\n\nA fact [glossary World Economic Outlook].")

    await _deliver(runner, configured_tool_name=None)

    assert "[glossary World Economic Outlook]" in choice.content
    assert "### Glossary" not in choice.content


# --- the order of the tables -------------------------------------------------------------------


def test_the_dataset_table_comes_before_the_document_table() -> None:
    properties = ApplicationProperties.model_validate(
        {
            "prompts": {"client_name": "A", "agent_name": "B", "data_sources_descriptions": "C"},
            "mcp_servers": [
                {
                    "server_name": "documents",
                    "server_type": "generic_rag",
                    "deployment_id": "rag",
                    "file_sharing_tool": "get_citation_url",
                    "document_metadata_resource": "documents://metadata/{document_ids}",
                    "document_title_key": "publication_title",
                    "references_table": {
                        "title": "Documents",
                        "columns": [{"heading": "T", "key": "t"}],
                    },
                },
                {
                    "server_name": "datasets",
                    "server_type": "statgpt",
                    "deployment_id": "statgpt",
                    "list_datasets_tool": "list_datasets",
                    "data_query_meta_key": "acme.example.org/client",
                    "references_table": {
                        "title": "Datasets",
                        "columns": [{"heading": "N", "key": "name"}],
                    },
                },
            ],
        }
    )

    assert [entry.table.title for entry in properties.references_tables] == [
        "Datasets",
        "Documents",
    ]
