"""Expand a `$env:{...}` placeholder in a config string from the environment.

Adapted from the statgpt-backend repo (`statgpt/common/config/utils.py`) so committed
config (e.g. application properties) can reference secrets by env-var name instead of
embedding them. Hardened here to a **full match**: only a value that is entirely one
placeholder is expanded — a placeholder embedded in surrounding text is left untouched.
This avoids partial substitution and keeps secret expansion predictable.
"""

import os
import re

_ENV_PATTERN = re.compile(r"\$env:{([^}|]*)(\|([^}|]*))?}")


def replace_env_str(value: str, raise_if_missing: bool = False) -> str:
    """Expand a `$env:{VAR}` / `$env:{VAR|default}` value from the environment.

    The whole string must be a single placeholder (full match); otherwise it is returned
    unchanged. When it matches, the result is the env var's value, else the default if one
    is given. When the env var is unset and no default is given: raise `ValueError` if
    `raise_if_missing`, otherwise leave the placeholder untouched.

    :param value: string to expand
    :param raise_if_missing: raise instead of returning the placeholder when the env var is
        unset and no default is given
    :return: expanded string
    """
    match = _ENV_PATTERN.fullmatch(value)
    if match is None:
        return value

    env_name = match.group(1)  # group(1): the variable name
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value

    default_value = match.group(3)  # group(3): the default if provided, otherwise None
    if default_value is not None:
        return default_value

    if raise_if_missing:
        raise ValueError(f"environment variable '{env_name}' is not set and has no default")

    # Env var missing and no default provided: leave the placeholder untouched.
    return value
