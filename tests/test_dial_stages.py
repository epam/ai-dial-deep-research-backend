from datetime import datetime

from dial_deep_research.utils.dial_stages import DialStageToolCallFormatter, timed_stage_title


def test_timed_stage_title_format() -> None:
    start = datetime(2026, 4, 28, 14, 30, 5)
    end = datetime(2026, 4, 28, 14, 30, 7)
    assert timed_stage_title("foo", start, end) == "foo (2.00s, start: 14:30:05, end: 14:30:07)"


def test_result_stage_title_success() -> None:
    start = datetime(2026, 4, 28, 14, 30, 5)
    end = datetime(2026, 4, 28, 14, 30, 6)
    assert (
        DialStageToolCallFormatter.format_title("search_docs", start, end)
        == '[TOOL] "search_docs" - result ✅ (1.00s, start: 14:30:05, end: 14:30:06)'
    )


def test_result_stage_title_error() -> None:
    start = datetime(2026, 4, 28, 14, 30, 5)
    end = datetime(2026, 4, 28, 14, 30, 6)
    assert (
        DialStageToolCallFormatter.format_title("search_docs", start, end, is_error=True)
        == '[TOOL] "search_docs" - error ❌ (1.00s, start: 14:30:05, end: 14:30:06)'
    )
