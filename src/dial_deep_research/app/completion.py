import logging
import uuid
from typing import NoReturn

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from aidial_sdk.exceptions import HTTPException as DialHTTPException
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from dial_deep_research.app.error_resolution import (
    ApplicationNotConfiguredError,
    ResearchAlreadyHandedOffError,
    ResolvedError,
    resolve_exception,
)
from dial_deep_research.app.history import (
    PrepState,
    create_dial_state,
    load_last_prep_state,
)
from dial_deep_research.app.preparation.runner import PrepAgentRunner
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.settings import PLACEHOLDER_API_KEY, settings
from dial_deep_research.utils.llm import LLMModelConfig
from dial_deep_research.utils.tracing import build_opik_tracer, extract_thread_id

_log = logging.getLogger(__name__)

# Statuses that pass through the outgoing-status policy unchanged. Everything else becomes 500 so
# the app never emits a status DIAL Core's balancer treats as retriable (429/502/503/504) — for an
# application Core cannot retry, so it would discard the error body. 409 is included for the
# research-already-handed-off condition; it is non-retriable by the balancer, so it is safe.
_CLIENT_ERROR_STATUS_CODES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _outgoing_status_code(resolved: ResolvedError) -> int:
    status = resolved.details.status_code
    if status in _CLIENT_ERROR_STATUS_CODES:
        return status
    return 500


def _raise_dial_error(e: Exception) -> NoReturn:
    """Log the failure with a correlation reference and raise it as a DIAL protocol error.

    Must be called from within an active ``except`` block so ``logger.exception`` captures the
    stack trace. The SDK delivers the raised exception as a non-200 response (non-streaming
    requests, failures before the choice opens) or an in-stream error chunk (streaming requests).
    """
    error_reference = uuid.uuid4().hex[:8]
    resolved = resolve_exception(e)
    _log.exception(
        "deep-research turn failed (error_reference=%s, retryable=%s, details=%s)",
        error_reference,
        resolved.retryable,
        resolved.details,
    )
    display = f"{resolved.message} (error reference: {error_reference})"
    status_code = _outgoing_status_code(resolved)
    # OpenAI-protocol convention when the upstream supplied no type: client-attributable
    # 4xx -> invalid_request_error, everything else -> runtime_error.
    default_type = "invalid_request_error" if status_code < 500 else "runtime_error"
    # `message` mirrors `display_message`: internal detail stays in the server log, reachable via
    # the reference. DIAL Chat surfaces only `display_message` on the in-stream path.
    raise DialHTTPException(
        status_code=status_code,
        message=display,
        display_message=display,
        code=resolved.details.code,
        type=resolved.details.error_type or default_type,
    )


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
        with response.create_single_choice() as choice:
            try:
                await self._run_turn(request, choice)
            except Exception as e:
                _raise_dial_error(e)

    async def _run_turn(self, request: Request, choice: Choice) -> None:
        properties = await self._load_properties(request)

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
            # The per-request bearer token (when present) is forwarded to the RAG MCP for
            # per-user access; the api-key is handled by header propagation.
            research_messages = await ResearchRunner(choice).run(
                prep_state,
                properties=properties,
                opik_tracer=opik_tracer,
                bearer_token=request.bearer_token,
            )
            messages.extend(research_messages)

        await self._persist(choice, messages, prep_state, dial)

    @staticmethod
    async def _load_properties(request: Request) -> ApplicationProperties:
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

    async def _persist(
        self, choice: Choice, messages: list[BaseMessage], prep_state: PrepState, dial: AsyncDial
    ) -> None:
        state = await create_dial_state(messages=messages, preparation=prep_state, dial=dial)
        choice.set_state(state)
