from types import SimpleNamespace
from typing import Any

from dial_deep_research.utils.tracing import extract_thread_id


def _request_with_header(value: str | None) -> Any:
    headers: dict[str, str] = {} if value is None else {"x-conversation-id": value}
    return SimpleNamespace(headers=headers)


def test_extract_returns_value_when_header_present() -> None:
    assert extract_thread_id(_request_with_header("abc-123")) == "abc-123"


def test_extract_strips_surrounding_whitespace() -> None:
    assert extract_thread_id(_request_with_header("  abc-123  ")) == "abc-123"


def test_extract_returns_none_when_header_absent() -> None:
    assert extract_thread_id(_request_with_header(None)) is None


def test_extract_returns_none_when_header_empty() -> None:
    assert extract_thread_id(_request_with_header("")) is None


def test_extract_returns_none_when_header_whitespace_only() -> None:
    assert extract_thread_id(_request_with_header("   ")) is None


def test_extract_returns_none_on_unexpected_request_shape() -> None:
    class ExplodingHeaders:
        def get(self, _key: str) -> str:
            raise RuntimeError("boom")

    request = SimpleNamespace(headers=ExplodingHeaders())
    assert extract_thread_id(request) is None


def test_extract_returns_none_when_request_has_no_headers() -> None:
    assert extract_thread_id(SimpleNamespace()) is None
