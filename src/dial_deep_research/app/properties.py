"""Load and validate an instance's DIAL application properties from the request.

Shared by every chat completion (research, playground): each turn resolves the
instance's `applicationProperties` the same way.
"""

from __future__ import annotations

import logging

from aidial_sdk.chat_completion import Request
from pydantic import ValidationError

from dial_deep_research.app.error_resolution import ApplicationNotConfiguredError
from dial_deep_research.app_properties import ApplicationProperties

_log = logging.getLogger(__name__)


async def load_application_properties(request: Request) -> ApplicationProperties:
    """Resolve and validate the instance's DIAL application properties.

    The SDK reads them from the `X-DIAL-APPLICATION-PROPERTIES` header when present, otherwise
    fetches them from DIAL Core by the request's application id. A **fetch** failure (Core
    unreachable, missing app-id header, etc.) propagates to the top-level handler and resolves
    as a service error. A **validation** failure means the app is misconfigured and raises
    `ApplicationNotConfiguredError`, which the handler delivers as a protocol error.
    """
    raw = await request.request_dial_application_properties()
    try:
        return ApplicationProperties.model_validate(raw)
    except ValidationError as exc:
        _log.warning("application properties failed validation: %s", exc)
        raise ApplicationNotConfiguredError() from exc
