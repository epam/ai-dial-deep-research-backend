"""Structure-only rendering of pydantic validation errors for log records.

Pydantic renders input values into `ValidationError` text, so logging the exception (or
its traceback) leaks the validated payload — persisted conversation state, application
properties with client prompts. The logging-policy spec requires such records to carry
structure only: error count, locations, error types.
"""

from pydantic import ValidationError


def validation_error_summary(exc: ValidationError) -> str:
    """Render a `ValidationError` as ``N error(s): loc(type), …`` — no input values."""
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}({err['type']})"
        for err in exc.errors(include_url=False, include_input=False)
    ]
    return f"{exc.error_count()} error(s): {', '.join(parts)}"
