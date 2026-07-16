"""The request-skeleton bookends shared by every chat completion.

Owns event 1 (request received) and the success variant of event 7 (request
completed) of the logging-policy INFO skeleton, plus the error wiring that threads
the turn start time into `raise_dial_error` — which emits the failure variant of
event 7 next to the turn's single ERROR record.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from aidial_sdk.chat_completion import Choice, Request, Response

from dial_deep_research.app.error_resolution import raise_dial_error

_log = logging.getLogger(__name__)


async def run_logged_turn(
    *,
    deployment: str,
    request: Request,
    response: Response,
    run_turn: Callable[[Request, Choice], Awaitable[None]],
) -> None:
    """Run one turn on a single choice, inside the request-skeleton bookends."""
    started_at = time.monotonic()
    _log.info("Request received: deployment=%s messages=%d", deployment, len(request.messages))
    with response.create_single_choice() as choice:
        try:
            await run_turn(request, choice)
        except Exception as e:
            raise_dial_error(e, started_at=started_at)
    _log.info("Request completed: outcome=completed duration=%.1fs", time.monotonic() - started_at)
