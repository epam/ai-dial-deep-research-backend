import os
import re

# A bare, non-empty placeholder: `$env:{VAR}`. `|` is excluded so the `$env:{VAR|default}`
# form does not match (it is not treated as a placeholder).
_ENV_PATTERN = re.compile(r"\$env:\{([^}|]+)\}")


def is_env_placeholder(value: str) -> bool:
    """Return whether `value` is exactly one `$env:{VAR}` placeholder."""
    return _ENV_PATTERN.fullmatch(value) is not None


def replace_env_str(value: str, raise_if_missing: bool = False) -> str:
    """Expand a `$env:{VAR}` value from the environment.

    The whole string must be a single placeholder (full match); otherwise it is returned
    unchanged. When it matches, the result is the env var's value. When the env var is unset:
    raise `ValueError` if `raise_if_missing`, otherwise leave the placeholder untouched.

    :param value: string to expand
    :param raise_if_missing: raise instead of returning the placeholder when the env var is unset
    :return: expanded string
    """
    match = _ENV_PATTERN.fullmatch(value)
    if match is None:
        return value

    env_name = match.group(1)
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value

    if raise_if_missing:
        raise ValueError(f"environment variable '{env_name}' is not set")

    # Env var missing: leave the placeholder untouched.
    return value
