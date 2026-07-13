"""The DIAL SDK reads PYDANTIC_V2 at import time; the package forces it on so the SDK uses
pydantic v2 models. The override case needs a fresh interpreter, so those tests probe a
subprocess."""

import os
import subprocess
import sys

import pydantic


def test_sdk_uses_pydantic_v2_after_package_import() -> None:
    """Importing the package (as conftest already did) puts the SDK into pydantic v2 mode."""
    import aidial_sdk._pydantic as sdk_pydantic
    from aidial_sdk.chat_completion import Request

    import dial_deep_research  # noqa: F401  (import side effect sets PYDANTIC_V2)

    assert os.environ["PYDANTIC_V2"] == "True"
    assert sdk_pydantic.PYDANTIC_V2 is True
    assert issubclass(Request, pydantic.BaseModel)


# Import the package (its __init__ runs the setdefault) before importing the SDK, then report the
# resulting env value and the SDK's resolved flag.
_PROBE = (
    "import os, dial_deep_research;"
    "import aidial_sdk._pydantic as p;"
    "print(os.environ.get('PYDANTIC_V2'), p.PYDANTIC_V2)"
)


def _probe(pydantic_v2_value: str | None) -> tuple[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYDANTIC_V2"}
    if pydantic_v2_value is not None:
        env["PYDANTIC_V2"] = pydantic_v2_value
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    env_value, sdk_flag = result.stdout.split()
    return env_value, sdk_flag


def test_flag_defaults_to_true_when_unset() -> None:
    """A fresh process with PYDANTIC_V2 unset (as in tests and scripts) still gets v2 mode."""
    env_value, sdk_flag = _probe(pydantic_v2_value=None)
    assert env_value == "True"
    assert sdk_flag == "True"


def test_explicit_env_value_is_not_overwritten() -> None:
    """setdefault leaves an explicit PYDANTIC_V2 override in place."""
    env_value, sdk_flag = _probe(pydantic_v2_value="False")
    assert env_value == "False"
    assert sdk_flag == "False"
