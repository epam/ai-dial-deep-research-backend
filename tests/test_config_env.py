import pytest

from dial_deep_research.utils.config_env import is_env_placeholder, replace_env_str


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


def test_default_form_is_not_recognized(monkeypatch: pytest.MonkeyPatch) -> None:
    # The `$env:{VAR|default}` form is no longer supported: with a `|` it is not a valid
    # placeholder, so it never full-matches and is returned unchanged (not expanded).
    monkeypatch.setenv("PRESENT", "from-env")
    assert replace_env_str("$env:{PRESENT|fallback}") == "$env:{PRESENT|fallback}"


def test_default_form_does_not_raise_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not a placeholder -> never raises, regardless of the flag (the inline default is inert).
    monkeypatch.delenv("MISSING", raising=False)
    assert (
        replace_env_str("$env:{MISSING|fallback}", raise_if_missing=True)
        == "$env:{MISSING|fallback}"
    )


def test_missing_env_leaves_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    assert replace_env_str("$env:{MISSING}") == "$env:{MISSING}"


def test_missing_env_raises_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(ValueError, match="MISSING"):
        replace_env_str("$env:{MISSING}", raise_if_missing=True)


def test_raise_if_missing_does_not_raise_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRESENT", "value")
    assert replace_env_str("$env:{PRESENT}", raise_if_missing=True) == "value"


def test_raise_if_missing_ignores_non_placeholder() -> None:
    # A value that is not a placeholder never raises, regardless of the flag.
    assert replace_env_str("plain value", raise_if_missing=True) == "plain value"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("$env:{VAR}", True),
        ("$env:{A_B_1}", True),
        ("$env:{VAR|default}", False),  # inline default form is not a valid placeholder
        ("$env:{}", False),  # empty name
        ("plain", False),
        ("prefix-$env:{VAR}", False),  # not a full match
    ],
)
def test_is_env_placeholder(value: str, expected: bool) -> None:
    assert is_env_placeholder(value) is expected
