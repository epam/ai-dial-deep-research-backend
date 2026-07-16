import logging
from datetime import datetime, timedelta

import pytest

from dial_deep_research.utils.dial_stages import (
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
    timed_stage_title,
)


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


class TestToolCallEvent:
    """The tool-call event of the logging-policy INFO skeleton."""

    def test_success_event_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        log = logging.getLogger("dial_deep_research.test.tool_events")
        caplog.set_level(logging.DEBUG, logger=log.name)
        start = datetime(2026, 1, 1, 12, 0, 0)
        tool_call = PendingToolCall(start=start, tool_name="search_docs", args_json="{}")

        log_tool_call_completed(
            log,
            tool_call=tool_call,
            tool_call_id="call_1",
            end=start + timedelta(seconds=2),
            is_error=False,
        )

        [record] = caplog.records
        assert record.levelno == logging.INFO
        text = record.getMessage()
        assert "tool=search_docs" in text
        assert "tool_call_id=call_1" in text
        assert "duration=2.0s" in text
        assert "outcome=success" in text

    def test_error_outcome_and_level_override(self, caplog: pytest.LogCaptureFixture) -> None:
        log = logging.getLogger("dial_deep_research.test.tool_events")
        caplog.set_level(logging.DEBUG, logger=log.name)
        start = datetime(2026, 1, 1, 12, 0, 0)
        tool_call = PendingToolCall(start=start, tool_name="finish_iteration", args_json="{}")

        log_tool_call_completed(
            log,
            tool_call=tool_call,
            tool_call_id="call_2",
            end=start + timedelta(seconds=1),
            is_error=True,
            level=logging.DEBUG,
        )

        [record] = caplog.records
        assert record.levelno == logging.DEBUG
        assert "outcome=error" in record.getMessage()
