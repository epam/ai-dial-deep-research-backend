import json
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response
from langchain_core.messages import BaseMessage

from dial_deep_research.app.data_sources import fetch_data_sources
from dial_deep_research.app.error_resolution import (
    ResearchAlreadyHandedOffError,
    SnapshotUnreadableError,
    SnapshotVersionUnsupportedError,
    repeating_failure,
)
from dial_deep_research.app.history import (
    FAILURE_STATE_KEY,
    SNAPSHOT_STATE_KEY,
    DialState,
    PrepState,
    create_dial_state,
    load_last_prep_state,
)
from dial_deep_research.app.preparation.runner import PrepAgentRunner
from dial_deep_research.app.properties import load_application_properties
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.research.snapshot import (
    DiscardedSnapshot,
    ResumableSnapshot,
    build_snapshot,
    find_latest_snapshot,
    read_snapshot,
)
from dial_deep_research.app.turn_lifecycle import run_logged_turn
from dial_deep_research.app_properties import DEPLOYMENT_NAME
from dial_deep_research.settings import PLACEHOLDER_API_KEY, settings
from dial_deep_research.utils.llm import LLMModelConfig
from dial_deep_research.utils.tracing import build_opik_tracer, extract_thread_id

_log = logging.getLogger(__name__)

# The two refusals of a snapshot that cannot be read. Each happens before the research graph
# streams any state, so it is told apart before the turn would look for research progress.
_SNAPSHOT_REFUSALS = (SnapshotVersionUnsupportedError, SnapshotUnreadableError)

# "[DEBUG]" is only part of the title: the stages are always emitted, and a client that hides
# Deep Research's debug stages hides them.
_SNAPSHOT_REUSED_STAGE = "[DEBUG] reusing snapshot"
_SNAPSHOT_DISCARDED_STAGE = "[DEBUG] existing snapshot discarded"


def _render_facts(facts: list[tuple[str, str]]) -> str:
    return " ".join(f"{key}={value}" for key, value in facts)


def _show_snapshot_stage(choice: Choice, *, title: str, facts: list[tuple[str, str]]) -> None:
    with choice.create_stage(title) as stage:
        stage.append_content("\n\n".join(f"**{key}** {value}" for key, value in facts))


class _FailureRecordReason(StrEnum):
    """Why a failed turn saved its failure record without a snapshot."""

    PREPARATION_FAILED = "preparation_failed"
    SNAPSHOT_REFUSED = "snapshot_refused"
    NO_GRAPH_STATE = "no_graph_state"
    SNAPSHOT_FAILED = "snapshot_failed"


class _SavedInstead(StrEnum):
    """What a turn whose report was written saved when its full state could not be saved."""

    CLOSING_STATE = "closing_state"
    NOTHING = "nothing"


@dataclass
class _TurnProgress:
    """How far a turn got, which decides what it persists if it fails."""

    prep_state: PrepState
    prep_messages: list[BaseMessage] | None = None
    research: ResearchRunner | None = None
    # The SDK allows one state write per turn and has no accessor that says whether one was made.
    state_saved: bool = False

    def save_state(self, choice: Choice, state: dict[str, Any]) -> bytes:
        """Encode `state` as JSON, then make the turn's one state write; return the encoding.

        A state that cannot be encoded raises before the write, so the write stays free for a
        smaller state: the SDK counts the state as set before it encodes it, so a state that
        failed there would use the write up.
        """
        encoded = _encode_strictly(state)
        # Marked before the call: the SDK counts the state as set even when sending it raises.
        self.state_saved = True
        choice.set_state(state)
        return encoded


def _encode_strictly(value: Any) -> bytes:
    """`value` as UTF-8 JSON, the way Starlette's `JSONResponse` renders a non-streaming response.

    It is the strictest encoder the SDK sends a response with: it refuses `NaN` and infinities,
    and a lone surrogate fails its UTF-8 encoding, while the streaming path escapes both to ASCII.
    """
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _save_closing_state(turn: _TurnProgress, choice: Choice) -> _SavedInstead:
    """Save the turn's `PrepState` with research started and no transcript, after its report.

    It closes the conversation as the full state would: the next request is refused before its
    history is rebuilt, so no later turn reads the transcript it lacks.
    """
    try:
        turn.save_state(choice, DialState(messages=[], preparation=turn.prep_state).to_dict())
    except Exception:
        return _SavedInstead.NOTHING
    return _SavedInstead.CLOSING_STATE


class DeepResearchCompletion(ChatCompletion):
    """DIAL chat completion: a preparation agent that hands off to the research graph.

    One turn runs the preparation agent; if it approves the plan (`start_research`),
    the research graph runs in the same turn and streams the report. The whole turn's
    transcript plus the final `PrepState` are persisted once, and once the report is written
    nothing fails the turn. Every state is encoded before that one write, and a state that cannot
    be built or encoded falls back to a smaller one (see the research-resume spec).

    Any turn-aborting failure — an exception, an unconfigured instance, or a conversation whose
    report was already delivered — is resolved to a user-safe message and delivered through the
    DIAL error protocol (see `error_resolution`), never as fake-success HTTP 200 content. A turn
    that fails after its conversation's state was loaded and checked first persists a state that
    carries the failure flag, so later turns get the failed-turn note: a failed research run's
    snapshot when the run got far enough to save one, otherwise the failure record (see the
    research-resume spec).
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
            # The report was delivered on an earlier turn; nothing to do this turn.
            raise ResearchAlreadyHandedOffError()

        turn = _TurnProgress(prep_state=prep_state)
        try:
            # One fetch serves the whole turn: preparation plans with it, and research, when it
            # starts in this turn, researches and writes with the same data sources. The bearer
            # token gives the fetch the same per-user access as the turn's other MCP traffic.
            data_sources = await fetch_data_sources(properties, bearer_token=request.bearer_token)

            prep_started_at = time.monotonic()
            prep_runner = PrepAgentRunner(choice)
            prep_messages = await prep_runner.run(
                request=request,
                dial=dial,
                prep_state=prep_state,
                prompts=properties.prompts,
                data_sources=data_sources,
                opik_tracer=opik_tracer,
            )
            turn.prep_messages = list(prep_messages)
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
                resumed = self._find_resumable_snapshot(request, choice, prep_state)
                turn.research = ResearchRunner(
                    choice, content_already_streamed=prep_runner.appended_content
                )
                research_messages = await turn.research.run(
                    prep_state,
                    properties=properties,
                    data_sources=data_sources,
                    opik_tracer=opik_tracer,
                    bearer_token=request.bearer_token,
                    resumed=resumed,
                    dial=dial,
                )
                messages.extend(research_messages)

            await self._persist(
                turn, choice, messages, dial, report_written=prep_state.research_started
            )
        except Exception as failure:
            await self._persist_failure(
                request=request, choice=choice, dial=dial, turn=turn, failure=failure
            )
            raise

    @staticmethod
    def _find_resumable_snapshot(
        request: Request, choice: Choice, prep_state: PrepState
    ) -> ResumableSnapshot | None:
        """The latest snapshot in the history, when it is a resumable one of the current plan.

        When a snapshot is found, a closed stage says whether it is reused or discarded, and one
        INFO record carries the same facts. A snapshot that cannot be read raises its refusal.
        """
        raw = find_latest_snapshot(request.messages)
        if raw is None:
            return None
        if prep_state.plan_id is None:
            raise ValueError("Research started without a plan id")
        outcome = read_snapshot(raw, current_plan_id=prep_state.plan_id)
        if isinstance(outcome, DiscardedSnapshot):
            facts = outcome.facts(current_plan_id=prep_state.plan_id)
            _show_snapshot_stage(choice, title=_SNAPSHOT_DISCARDED_STAGE, facts=facts)
            _log.info("Snapshot discarded: %s", _render_facts(facts))
            return None
        facts = outcome.facts()
        _show_snapshot_stage(choice, title=_SNAPSHOT_REUSED_STAGE, facts=facts)
        _log.info("Snapshot reused: %s", _render_facts(facts))
        return outcome

    async def _persist(
        self,
        turn: _TurnProgress,
        choice: Choice,
        messages: list[BaseMessage],
        dial: AsyncDial,
        *,
        report_written: bool,
    ) -> None:
        """Save the completed turn's state.

        An image that cannot be uploaded, the files bucket that cannot be resolved included, is
        saved as a placeholder. Once the report is written, a state that cannot be built or
        encoded is replaced by the closing state, and the turn completes with one WARNING: a
        report costs a whole research run, and failing the turn would cost the user the report.
        """
        try:
            state = await create_dial_state(
                messages=messages, preparation=turn.prep_state, dial=dial
            )
            turn.save_state(choice, state)
        except Exception as error:
            if not report_written:
                raise
            # After the encoding check, a write raises only on a choice that refuses state, so
            # the closing state cannot follow it.
            saved = _SavedInstead.NOTHING if turn.state_saved else _save_closing_state(turn, choice)
            _log.warning(
                "Report delivery step failed after the report was written: step=save_state "
                "error=%s saved=%s",
                type(error).__name__,
                saved,
            )

    async def _persist_failure(
        self,
        *,
        request: Request,
        choice: Choice,
        dial: AsyncDial,
        turn: _TurnProgress,
        failure: Exception,
    ) -> None:
        """Persist what a failed turn leaves behind, before its error is delivered.

        A research run that streamed state saves its snapshot; any other failed turn, and one
        whose snapshot could not be saved, saves the failure record. Nothing here raises, so the
        error delivered is always the turn's own.
        """
        if turn.state_saved:
            return
        if isinstance(failure, _SNAPSHOT_REFUSALS):
            reason = _FailureRecordReason.SNAPSHOT_REFUSED
        elif turn.research is None:
            reason = _FailureRecordReason.PREPARATION_FAILED
        else:
            outcome = await self._persist_snapshot(
                choice=choice, dial=dial, turn=turn, research=turn.research, failure=failure
            )
            if outcome is None:
                return
            reason = outcome
        self._persist_failure_record(request=request, choice=choice, turn=turn, reason=reason)

    async def _persist_snapshot(
        self,
        *,
        choice: Choice,
        dial: AsyncDial,
        turn: _TurnProgress,
        research: ResearchRunner,
        failure: Exception,
    ) -> _FailureRecordReason | None:
        """Save the failed research run's snapshot beside the turn's preparation messages and its
        `PrepState` with approval and research-started reset, so the conversation stays open.

        Returns `None` when nothing is left to save, else why the failure record is saved instead.
        """
        failure_class = repeating_failure(failure)
        try:
            progress = research.captured_progress()
            if progress is None:
                return _FailureRecordReason.NO_GRAPH_STATE
            plan_id = turn.prep_state.plan_id
            if plan_id is None:
                raise ValueError("Research started without a plan id")
            snapshot = await build_snapshot(
                progress, plan_id=plan_id, resumable=failure_class is None, dial=dial
            )
            saved_prep = turn.prep_state.model_copy(
                update={"plan_approved": False, "research_started": False}
            )
            state = await create_dial_state(
                messages=list(turn.prep_messages or []), preparation=saved_prep, dial=dial
            )
            snapshot_dict = snapshot.model_dump(mode="json")
            state[SNAPSHOT_STATE_KEY] = snapshot_dict
            state[FAILURE_STATE_KEY] = True
            encoded_state = turn.save_state(choice, state)
        except Exception as error:
            _log.warning(
                "Snapshot could not be saved; saving the failure record instead: error=%s",
                type(error).__name__,
            )
            # A state write that raised still counts as made, so no failure record can follow.
            return None if turn.state_saved else _FailureRecordReason.SNAPSHOT_FAILED
        _log.info(
            "Snapshot saved: plan_id=%s resumable=%s%s resume_at=%s research_iteration=%d "
            "messages=%d report_version=%d data_queries=%d snapshot_bytes=%d state_bytes=%d",
            plan_id,
            snapshot.resumable,
            f" failure_class={failure_class}" if failure_class is not None else "",
            snapshot.resume_at,
            snapshot.research_iteration,
            len(snapshot.messages),
            snapshot.report_version,
            len(progress.data_queries),
            len(_encode_strictly(snapshot_dict)),
            len(encoded_state),
        )
        return None

    @staticmethod
    def _persist_failure_record(
        *, request: Request, choice: Choice, turn: _TurnProgress, reason: _FailureRecordReason
    ) -> None:
        """Save an empty `messages`, the failure flag, and the `PrepState` the turn started from.

        The `PrepState` is read again from the request because preparation mutates the loaded one
        in place, and a tool call of a turn that failed must not survive into the next turn.
        """
        try:
            preparation = load_last_prep_state(request)
            state = DialState(messages=[], preparation=preparation).to_dict()
            state[FAILURE_STATE_KEY] = True
            turn.save_state(choice, state)
        except Exception as error:
            _log.warning("Failure record could not be saved: error=%s", type(error).__name__)
            return
        _log.info("Failure recorded: reason=%s", reason)
