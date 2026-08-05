import logging
import time

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from langchain_core.messages import BaseMessage

from dial_deep_research.app.error_resolution import ResearchAlreadyHandedOffError
from dial_deep_research.app.history import (
    PrepState,
    create_dial_state,
    load_last_prep_state,
)
from dial_deep_research.app.preparation.runner import PrepAgentRunner
from dial_deep_research.app.properties import load_application_properties
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.turn_lifecycle import run_logged_turn
from dial_deep_research.app_properties import DEPLOYMENT_NAME
from dial_deep_research.settings import PLACEHOLDER_API_KEY, settings
from dial_deep_research.utils.llm import LLMModelConfig
from dial_deep_research.utils.tracing import build_opik_tracer, extract_thread_id

_log = logging.getLogger(__name__)


class DeepResearchCompletion(ChatCompletion):
    """DIAL chat completion: a preparation agent that hands off to the research graph.

    One turn runs the preparation agent; if it approves the plan (`start_research`),
    the research graph runs in the same turn and streams the report. The whole turn's
    transcript plus the final `PrepState` are persisted once.

    Any turn-aborting failure — an exception, an unconfigured instance, or a conversation whose
    research was already handed off — is resolved to a user-safe message and delivered through the
    DIAL error protocol (see `error_resolution`), never as fake-success HTTP 200 content.
    """

    def __init__(self, model_config: LLMModelConfig | None = None) -> None:
        self._model_config = model_config or LLMModelConfig()

    async def chat_completion(self, request: Request, response: Response) -> None:
        await run_logged_turn(
            deployment=DEPLOYMENT_NAME,
            request=request,
            response=response,
            run_turn=self._run_turn,
        )

    async def _run_turn(self, request: Request, choice: Choice) -> None:
        properties = await load_application_properties(request)

        opik_tracer = build_opik_tracer(
            tracing_enabled=settings.opik_tracing_enabled, thread_id=extract_thread_id(request)
        )
        dial = AsyncDial(
            base_url=settings.dial_url.encoded_string(),
            # Per-request api-key is injected by the SDK's header propagation; this
            # placeholder only satisfies the client's construction-time requirement.
            api_key=PLACEHOLDER_API_KEY,
        )
        prep_state = load_last_prep_state(request)

        if prep_state.research_started:
            # Research already ran on an earlier turn; nothing to do this turn.
            raise ResearchAlreadyHandedOffError()

        prep_started_at = time.monotonic()
        prep_runner = PrepAgentRunner(choice)
        prep_messages = await prep_runner.run(
            request=request,
            dial=dial,
            prep_state=prep_state,
            prompts=properties.prompts,
            opik_tracer=opik_tracer,
        )
        messages: list[BaseMessage] = list(prep_messages)
        _log.info(
            "Preparation completed: duration=%.1fs research_started=%s plan_steps=%d "
            "outstanding_questions=%d",
            time.monotonic() - prep_started_at,
            prep_state.research_started,
            len(prep_state.plan.steps) if prep_state.plan else 0,
            len(prep_state.clarification.questions) if prep_state.clarification else 0,
        )

        if prep_state.research_started:
            # start_research fired this turn — run the research graph on the same choice.
            # The per-request bearer token (when present) is forwarded to the RAG MCP for
            # per-user access; the api-key is handled by header propagation.
            research_messages = await ResearchRunner(
                choice, content_already_streamed=prep_runner.appended_content
            ).run(
                prep_state,
                properties=properties,
                opik_tracer=opik_tracer,
                bearer_token=request.bearer_token,
            )
            messages.extend(research_messages)

        await self._persist(choice, messages, prep_state, dial)

    async def _persist(
        self, choice: Choice, messages: list[BaseMessage], prep_state: PrepState, dial: AsyncDial
    ) -> None:
        state = await create_dial_state(messages=messages, preparation=prep_state, dial=dial)
        choice.set_state(state)
