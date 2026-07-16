"""DIAL chat completion for the playground: a single tool-calling agent, no research flow.

A debug surface for exercising the MCP tools configured on an instance. It reuses the same
application properties as the research deployment (only `mcp_servers` matters here) and the
same error delivery. It is **stateless**: nothing is persisted per turn, so follow-up turns
reach the agent as visible text only (see `reconstruct_plain_history`).
"""

from __future__ import annotations

from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response

from dial_deep_research.app.playground.runner import PlaygroundRunner
from dial_deep_research.app.properties import load_application_properties
from dial_deep_research.app.turn_lifecycle import run_logged_turn
from dial_deep_research.app_properties import PLAYGROUND_DEPLOYMENT_NAME
from dial_deep_research.settings import settings
from dial_deep_research.utils.tracing import build_opik_tracer, extract_thread_id


class PlaygroundCompletion(ChatCompletion):
    """DIAL chat completion running one tool-calling agent over the configured MCP servers.

    Any turn-aborting failure is resolved to a user-safe message and delivered through the DIAL
    error protocol (see `error_resolution`), never as fake-success HTTP 200 content.
    """

    async def chat_completion(self, request: Request, response: Response) -> None:
        await run_logged_turn(
            deployment=PLAYGROUND_DEPLOYMENT_NAME,
            request=request,
            response=response,
            run_turn=self._run_turn,
        )

    async def _run_turn(self, request: Request, choice: Choice) -> None:
        properties = await load_application_properties(request)
        opik_tracer = build_opik_tracer(
            tracing_enabled=settings.opik_tracing_enabled, thread_id=extract_thread_id(request)
        )
        await PlaygroundRunner(choice).run(
            request=request,
            properties=properties,
            bearer_token=request.bearer_token,
            opik_tracer=opik_tracer,
        )
