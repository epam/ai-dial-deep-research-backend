import logging
from datetime import datetime, timedelta

import pytest

from dial_deep_research.utils.dial_stages import (
    DialStageReportReviewFormatter,
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


class TestReportReviewStage:
    """The report-review stage: its own title shape, and the one place violations are shown."""

    def test_title_carries_the_draft_number_the_action_and_the_time(self) -> None:
        title = DialStageReportReviewFormatter.format_title(
            draft_number=2, revising=True, review_failed=False, duration_seconds=1.5
        )
        # Its own prefix, not the tool-call one: a review is not a tool call. A revision is
        # the loop working, not an error — the cross is reserved for a failed review call.
        assert title == "[REPORT REVIEW] draft 2 - revise ⚠️ (1.50s)"

    def test_delivered_draft_is_titled_as_a_success(self) -> None:
        title = DialStageReportReviewFormatter.format_title(
            draft_number=1, revising=False, review_failed=False, duration_seconds=0.5
        )
        assert title == "[REPORT REVIEW] draft 1 - deliver ✅ (0.50s)"

    def test_failed_review_titles_carry_the_cross_whatever_the_action(self) -> None:
        deliver = DialStageReportReviewFormatter.format_title(
            draft_number=1, revising=False, review_failed=True, duration_seconds=0.5
        )
        revise = DialStageReportReviewFormatter.format_title(
            draft_number=1, revising=True, review_failed=True, duration_seconds=0.5
        )
        assert deliver == "[REPORT REVIEW] draft 1 - deliver ❌ (0.50s)"
        assert revise == "[REPORT REVIEW] draft 1 - revise ❌ (0.50s)"

    def test_body_carries_both_counts_and_the_violations(self) -> None:
        body = DialStageReportReviewFormatter.format_body(
            draft_number=1,
            word_count=3910,
            max_words=2750,
            length_exemptions="the inline citations and the References section",
            violations=["The draft is over the ceiling.", "Two lines:\nthe second one."],
            error=None,
        )
        assert "**Draft** 1" in body
        assert "3910 words, excluding the inline citations and the References section" in body
        assert "(ceiling 2750)" in body
        assert "1. The draft is over the ceiling." in body
        assert "2. Two lines:\nthe second one." in body
        # No fencing: stage content renders as markdown, so the list renders as a list.
        assert "```" not in body

    def test_body_records_an_approval_when_there_are_no_violations(self) -> None:
        body = DialStageReportReviewFormatter.format_body(
            draft_number=1,
            word_count=900,
            max_words=2750,
            length_exemptions="the inline citations and the References section",
            violations=[],
            error=None,
        )
        assert "900 words, excluding the inline citations and the References section" in body
        assert "(ceiling 2750)" in body
        assert "satisfies every check" in body

    def test_body_records_a_failed_call_without_claiming_an_approval(self) -> None:
        body = DialStageReportReviewFormatter.format_body(
            draft_number=1,
            word_count=900,
            max_words=2750,
            length_exemptions="the inline citations and the References section",
            violations=[],
            error="RuntimeError",
        )
        assert "❌ **Error** the LLM review call failed (RuntimeError)" in body
        assert "satisfies every check" not in body

    def test_body_shows_both_the_failure_and_the_length_violation(self) -> None:
        body = DialStageReportReviewFormatter.format_body(
            draft_number=1,
            word_count=3910,
            max_words=2750,
            length_exemptions="the inline citations and the References section",
            violations=["The draft is 3910 words, over the 2750-word ceiling."],
            error="RuntimeError",
        )
        assert "❌ **Error** the LLM review call failed (RuntimeError)" in body
        assert "1. The draft is 3910 words" in body

    def test_unreviewed_delivery_has_its_own_title_without_a_duration(self) -> None:
        title = DialStageReportReviewFormatter.format_unreviewed_title(draft_number=3)
        assert title == "[REPORT REVIEW] draft 3 - delivered without review ⚠️"

    def test_unreviewed_delivery_body_names_the_exhausted_budget(self) -> None:
        body = DialStageReportReviewFormatter.format_unreviewed_body(
            draft_number=3,
            word_count=2100,
            max_words=2750,
            length_exemptions="the inline citations and the References section",
            max_versions=3,
        )
        assert "**Draft** 3" in body
        assert "2100 words, excluding the inline citations and the References section" in body
        assert "(ceiling 2750)" in body
        assert "budget (3)" in body
        assert "delivered without review" in body


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
