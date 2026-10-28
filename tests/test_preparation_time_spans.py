"""The preparation prompts count a span of years back from today so that it ends with the
current year, and their examples carry the years of the date the prompt is rendered on."""

from __future__ import annotations

from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.preparation import prompts as prep_prompts
from dial_deep_research.app.preparation.agent import render_prep_agent_system

_TEXT = "Publications: the quarterly economic bulletin."


def test_the_examples_are_counted_from_the_year_of_the_given_date() -> None:
    assert prep_prompts.year_span_examples("2031-01-02") == {
        "current_year": "2031",
        "last_two_years": "2030–2031",
        "last_ten_years": "2022–2031",
    }


def test_the_agent_prompt_ends_a_span_of_years_with_the_current_year() -> None:
    prompt = render_prep_agent_system(
        agent_name="ACME", today_date="2026-10-28", data_sources=DataSources(text=_TEXT)
    )
    assert 'in 2026, "the last 2 years" is 2025–2026' in prompt
    assert "Never shift such a span back to the" in prompt
    assert "the last 10 years (2017–2026); tell me if you'd like a different range" in prompt


def test_the_query_check_prompt_ends_a_span_of_years_with_the_current_year() -> None:
    prompt = prep_prompts.QUERY_REVIEW_SYSTEM.format(
        today_date="2026-10-28",
        data_sources=_TEXT,
        **prep_prompts.year_span_examples("2026-10-28"),
    )
    assert '"the last 10 years" is 2017–2026, never the last N' in prompt
    assert "defaults to the last 10 years (2017–2026)" in prompt
