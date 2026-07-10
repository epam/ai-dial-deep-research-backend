import logging

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from langchain_core.messages import AIMessage, BaseMessage

from dial_deep_research.app.history import (
    PrepState,
    create_dial_state,
    load_last_prep_state,
)
from dial_deep_research.app.preparation.runner import PrepAgentRunner
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.settings import settings
from dial_deep_research.utils.llm import LLMModelConfig
from dial_deep_research.utils.tracing import build_opik_tracer, extract_thread_id

_log = logging.getLogger(__name__)

_RESEARCH_STARTED = (
    "This research request has already been prepared and handed off. "
    "Start a new conversation to prepare another research."
)
_NOT_CONFIGURED = (
    "This application is not configured. Ask your DIAL administrator to set up the "
    "application's properties."
)
_FRIENDLY_ERROR = (
    "\n\nSorry, something went wrong while processing your request. The error has been logged."
)


class DeepResearchCompletion(ChatCompletion):
    """DIAL chat completion: a preparation agent that hands off to the research graph.

    One turn runs the preparation agent; if it approves the plan (`start_research`),
    the research graph runs in the same turn and streams the report. The whole turn's
    transcript plus the final `PrepState` are persisted once.
    """

    def __init__(self, model_config: LLMModelConfig | None = None) -> None:
        self._model_config = model_config or LLMModelConfig()

    async def chat_completion(self, request: Request, response: Response) -> None:
        with response.create_single_choice() as choice:
            try:
                await self._run_turn(request, choice)
            except Exception:
                _log.exception("deep-research chat completion failed")
                choice.append_content(_FRIENDLY_ERROR)

    async def _run_turn(self, request: Request, choice: Choice) -> None:
        properties = await self._load_properties(request)
        if properties is None:
            # No agent runs without a valid instance configuration.
            choice.append_content(_NOT_CONFIGURED)
            return

        opik_tracer = build_opik_tracer(
            tracing_enabled=settings.opik_tracing_enabled, thread_id=extract_thread_id(request)
        )
        dial = AsyncDial(
            base_url=settings.dial_url.encoded_string(),
            api_key=settings.dial_api_key.get_secret_value(),
        )
        prep_state = load_last_prep_state(request)

        if prep_state.research_started:
            # Research already ran on an earlier turn; do not run anything again.
            choice.append_content(_RESEARCH_STARTED)
            await self._persist(choice, [AIMessage(content=_RESEARCH_STARTED)], prep_state, dial)
            return

        prep_messages = await PrepAgentRunner(choice).run(
            request=request,
            dial=dial,
            prep_state=prep_state,
            prompts=properties.prompts,
            opik_tracer=opik_tracer,
        )
        messages: list[BaseMessage] = list(prep_messages)

        if prep_state.research_started:
            # start_research fired this turn — run the research graph on the same choice.
            research_messages = await ResearchRunner(choice).run(
                prep_state, properties=properties, opik_tracer=opik_tracer
            )
            messages.extend(research_messages)

        await self._persist(choice, messages, prep_state, dial)

    @staticmethod
    async def _load_properties(request: Request) -> ApplicationProperties | None:
        """Resolve and validate the instance's DIAL application properties.

        The SDK reads them from the `X-DIAL-APPLICATION-PROPERTIES` header when present,
        otherwise fetches them from DIAL Core by the request's application id. Returns
        `None` when they cannot be resolved or fail validation.
        """
        try:
            raw = await request.request_dial_application_properties()
            return ApplicationProperties.model_validate(raw)
        except Exception:
            _log.exception("failed to resolve application properties")
            return None

    async def _persist(
        self, choice: Choice, messages: list[BaseMessage], prep_state: PrepState, dial: AsyncDial
    ) -> None:
        state = await create_dial_state(messages=messages, preparation=prep_state, dial=dial)
        choice.set_state(state)
