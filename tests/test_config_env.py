import pytest

from dial_deep_research.utils.config_env import replace_env_str


def test_full_match_placeholder_is_expanded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_VAR", "resolved")
    assert replace_env_str("$env:{MY_VAR}") == "resolved"


def test_embedded_placeholder_is_left_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    # Hardened to a full match: a placeholder surrounded by other text is not expanded.
    monkeypatch.setenv("MY_VAR", "resolved")
    assert replace_env_str("prefix-$env:{MY_VAR}-suffix") == "prefix-$env:{MY_VAR}-suffix"


def test_multiple_placeholders_are_not_expanded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two placeholders means the whole value is not a single placeholder -> no full match.
    monkeypatch.setenv("A", "1")
    monkeypatch.setenv("B", "2")
    assert replace_env_str("$env:{A}$env:{B}") == "$env:{A}$env:{B}"


def test_non_placeholder_value_is_returned_unchanged() -> None:
    assert replace_env_str("plain value") == "plain value"


def test_default_is_used_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    assert replace_env_str("$env:{MISSING|fallback}") == "fallback"


def test_env_takes_precedence_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRESENT", "from-env")
    assert replace_env_str("$env:{PRESENT|fallback}") == "from-env"


def test_missing_env_without_default_leaves_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    assert replace_env_str("$env:{MISSING}") == "$env:{MISSING}"


def test_missing_env_without_default_raises_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(ValueError, match="MISSING"):
        replace_env_str("$env:{MISSING}", raise_if_missing=True)


def test_raise_if_missing_does_not_raise_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRESENT", "value")
    assert replace_env_str("$env:{PRESENT}", raise_if_missing=True) == "value"


def test_raise_if_missing_uses_default_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    assert replace_env_str("$env:{MISSING|fallback}", raise_if_missing=True) == "fallback"


def test_raise_if_missing_ignores_non_placeholder() -> None:
    # A value that is not a placeholder never raises, regardless of the flag.
    assert replace_env_str("plain value", raise_if_missing=True) == "plain value"


def test_empty_default_is_used_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit empty default (trailing pipe) resolves to the empty string, not the placeholder.
    monkeypatch.delenv("MISSING", raising=False)
    assert replace_env_str("$env:{MISSING|}") == ""
