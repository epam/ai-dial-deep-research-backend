"""The research record every research turn saves, and the snapshot a later turn resumes.

A record is the app's own versioned JSON, stored under its own key of the turn's state
(`history.SNAPSHOT_STATE_KEY`). A failed run's record is its snapshot; a completed run's record
has the same shape and is never resumed. A record names its resume point in the app's own terms,
never by graph node, so renaming a node does not break a pending resume: `RESUME_POINT_NODES` is
the one place the two meet. `read_snapshot` decides, header first, whether the latest record in
the history is resumed or discarded (see the research-resume spec).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Role
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from dial_deep_research.app.history import SNAPSHOT_STATE_KEY, raw_dial_state
from dial_deep_research.utils.image_attachments import (
    replace_images_with_placeholders,
    upload_snapshot_images,
)
from dial_deep_research.utils.pydantic_errors import validation_error_summary

from .data_queries import DataQueryRecord
from .prompts import ResearchReview
from .state import ReportReviewRound

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1
"""Bumped by a format change that a reader of the current version could not read. A change that
only adds fields with defaults keeps it, because the reader ignores fields it does not know."""


class ResumePoint(StrEnum):
    """The node a resumed run re-enters at, in the app's own terms."""

    RESEARCH = "research"
    RESEARCH_REVIEW = "research_review"
    REPORT = "report"
    REPORT_REVIEW = "report_review"


RESUME_POINT_NODES: dict[ResumePoint, str] = {
    ResumePoint.RESEARCH: "research-agent",
    ResumePoint.RESEARCH_REVIEW: "research-review",
    ResumePoint.REPORT: "report",
    ResumePoint.REPORT_REVIEW: "report-review",
}
"""The research graph's node for each resume point."""


class NotResumableReason(StrEnum):
    """Why a research record will not be resumed."""

    COMPLETED = "completed"
    REPEATING_FAILURE = "repeating_failure"
    IMAGE_UPLOAD_FAILED = "image_upload_failed"


class ResearchSnapshot(BaseModel):
    """A research record, as persisted: a failed run's snapshot, or a completed run's record.

    `plan_id`, `resumable` and `version` are the stable header: every format version keeps their
    names and meaning, so any release can tell whether a record is to be resumed before it reads
    the rest. `not_resumable_reason` is set exactly when `resumable` is false, and `resume_at` is
    `None` only on a completed run's record. The other fields mirror `ResearchState`, field for
    field, the research-agent messages as `messages_to_dict` writes them; the reviews are declared
    with their models, so a resumed run holds the same types as a fresh one.
    """

    model_config = ConfigDict(extra="ignore")

    plan_id: str
    resumable: bool
    not_resumable_reason: NotResumableReason | None = None
    version: int
    resume_at: ResumePoint | None
    research_query: str
    approved_plan: list[str]
    research_agent_messages: list[dict[str, Any]]
    research_iteration: int
    research_reviews: list[ResearchReview]
    reports: list[str]
    report_reviews: list[ReportReviewRound]
    report_revision_failed: bool
    data_queries: str
    """The turn's data-query records as one JSON string (`encode_data_queries`). A client may
    rebuild a streamed answer with the DIAL SDK's chunk merge, which re-slots any list of objects
    carrying an `index` key at any depth; the records keep the server's elements whole, and a
    string is out of the merge's reach."""


class CapturedProgress(BaseModel):
    """What the research runner had seen of a run, before it becomes a research record."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    resume_at: ResumePoint | None
    """The node that was running when the run failed; `None` for a run that completed."""
    messages: list[BaseMessage]
    """Research-agent's messages to store."""
    channels: dict[str, Any]
    """The research graph's root state: as the running node received it, or as the run ended."""
    data_queries: dict[str, DataQueryRecord]


async def build_snapshot(
    progress: CapturedProgress, *, plan_id: str, repeating_failure: bool, dial: AsyncDial
) -> ResearchSnapshot:
    """Upload the transcript's images to DIAL files, then build the failed run's snapshot.

    Rewrites the image blocks of `progress.messages` in place. A snapshot with an image that
    could not be stored is still built, marked not resumable: resuming without what research-agent
    saw could mislead the report. A failure a resume would repeat names that reason instead,
    because a resume could never get past it.
    """
    not_stored = await upload_snapshot_images(messages=progress.messages, dial=dial)
    if repeating_failure:
        reason: NotResumableReason | None = NotResumableReason.REPEATING_FAILURE
    elif not_stored:
        reason = NotResumableReason.IMAGE_UPLOAD_FAILED
    else:
        reason = None
    return _research_record(progress=progress, plan_id=plan_id, not_resumable_reason=reason)


def build_completed_record(progress: CapturedProgress, *, plan_id: str) -> ResearchSnapshot:
    """The record of a run that delivered its report: never resumed, every image a placeholder,
    and no files call made."""
    replace_images_with_placeholders(messages=progress.messages)
    return _research_record(
        progress=progress, plan_id=plan_id, not_resumable_reason=NotResumableReason.COMPLETED
    )


def _research_record(
    progress: CapturedProgress, *, plan_id: str, not_resumable_reason: NotResumableReason | None
) -> ResearchSnapshot:
    channels = progress.channels
    return ResearchSnapshot(
        plan_id=plan_id,
        resumable=not_resumable_reason is None,
        not_resumable_reason=not_resumable_reason,
        version=SNAPSHOT_VERSION,
        resume_at=progress.resume_at,
        research_query=channels["research_query"],
        approved_plan=channels["approved_plan"],
        research_agent_messages=messages_to_dict(progress.messages),
        research_iteration=channels["research_iteration"],
        research_reviews=channels["research_reviews"],
        reports=channels["reports"],
        report_reviews=channels["report_reviews"],
        report_revision_failed=channels["report_revision_failed"],
        data_queries=encode_data_queries(progress.data_queries),
    )


def encode_data_queries(records: Mapping[str, DataQueryRecord]) -> str:
    return json.dumps(
        {
            query_id: record.model_dump(mode="json", by_alias=True)
            for query_id, record in records.items()
        }
    )


def decode_data_queries(text: str) -> dict[str, DataQueryRecord]:
    return {
        query_id: DataQueryRecord.model_validate(record)
        for query_id, record in json.loads(text).items()
    }


class DiscardReason(StrEnum):
    PLAN_CHANGED = "plan_changed"
    NOT_RESUMABLE = "not_resumable"
    IMAGE_MISSING = "image_missing"
    VERSION_UNSUPPORTED = "version_unsupported"
    UNREADABLE = "unreadable"


class DiscardedSnapshot(BaseModel):
    """A record found in the history that will not be resumed.

    One discarded for `plan_changed`, `not_resumable`, `version_unsupported` or `unreadable` is
    not read whole, so `resume_at` is set only when it reads as a known value, and
    `not_resumable_reason` only for `not_resumable`, when it reads as a known reason. `plan_id` is
    `None` only for an `unreadable` record whose plan id is not a string. One discarded for
    `image_missing` was read whole, and names its resume point.
    """

    plan_id: str | None
    reason: DiscardReason
    resume_at: ResumePoint | None
    not_resumable_reason: NotResumableReason | None = None

    def facts(self, *, current_plan_id: str) -> list[tuple[str, str]]:
        """What the "existing snapshot discarded" stage and log record say: ids and names only."""
        facts = [("plan_id", self.plan_id)] if self.plan_id is not None else []
        facts += [
            ("current_plan_id", current_plan_id),
            ("reason", self.reason.value),
        ]
        if self.not_resumable_reason is not None:
            facts.append(("not_resumable_reason", self.not_resumable_reason.value))
        if self.resume_at is not None:
            facts.append(("resume_at", self.resume_at.value))
        return facts


class ResumableSnapshot(BaseModel):
    """A snapshot of the current plan that a resumed run starts from, fully read."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    snapshot: ResearchSnapshot
    messages: list[BaseMessage]
    data_queries: dict[str, DataQueryRecord]

    @property
    def resume_at(self) -> ResumePoint:
        """Where the resumed run enters; `read_snapshot` discards a resumable record without one."""
        if self.snapshot.resume_at is None:
            raise ValueError("A resumable snapshot names no resume point")
        return self.snapshot.resume_at

    @property
    def draft_number(self) -> int:
        """The latest draft's number, 0 while no draft exists."""
        return len(self.snapshot.reports)

    @property
    def restored_model_calls_in_iteration(self) -> int | None:
        """For resume point research: the interrupted iteration's model calls the snapshot
        restores, which the resumed run does not make again. They are the `AIMessage`s after the
        iteration's instruction, the last `HumanMessage`."""
        if self.snapshot.resume_at is not ResumePoint.RESEARCH:
            return None
        model_calls = 0
        for message in reversed(self.messages):
            if isinstance(message, HumanMessage):
                break
            if isinstance(message, AIMessage):
                model_calls += 1
        return model_calls

    @property
    def report_review_round(self) -> int | None:
        """For resume point report review: the round to run, which reviews the latest draft."""
        if self.snapshot.resume_at is not ResumePoint.REPORT_REVIEW:
            return None
        return self.draft_number

    def facts(self) -> list[tuple[str, str]]:
        """What the "reusing snapshot" stage and log record say: ids, names and counts only."""
        snapshot = self.snapshot
        facts = [
            ("plan_id", snapshot.plan_id),
            ("resume_at", self.resume_at.value),
            ("research_iteration", str(snapshot.research_iteration)),
            ("messages", str(len(self.messages))),
            ("draft_number", str(self.draft_number)),
        ]
        if (model_calls := self.restored_model_calls_in_iteration) is not None:
            facts.append(("restored_model_calls_in_iteration", str(model_calls)))
        if (review_round := self.report_review_round) is not None:
            facts.append(("report_review_round", str(review_round)))
        return facts


def find_latest_snapshot(messages: Sequence[Message]) -> Any:
    """The raw research record of the latest assistant message whose state carries one, else
    `None`.

    Only the latest counts. Plan ids are only ever replaced by fresh ones, so when its id differs
    from the current one no older record can match, and a newer record marked not resumable hides
    older ones on purpose, whatever its reason: research then reruns from the start, and that
    turn's own record becomes the latest.
    """
    for message in reversed(messages):
        if message.role != Role.ASSISTANT:
            continue
        state = raw_dial_state(message)
        if state is not None and (snapshot := state.get(SNAPSHOT_STATE_KEY)) is not None:
            return snapshot
    return None


def read_snapshot(raw: Any, *, current_plan_id: str) -> ResumableSnapshot | DiscardedSnapshot:
    """Decide whether `raw` is resumed or discarded, reading its header first.

    The plan id is compared first, then the resumable mark is read, then the version, so a record
    of another plan or one marked not resumable is discarded whatever its version or contents.
    Only a matching resumable snapshot of this version is read whole; its images are downloaded
    afterwards, by the caller. Nothing a record contains raises: a record that cannot be read is
    discarded, with one WARNING that names what failed, and research runs fresh.
    """
    unreadable = DiscardReason.UNREADABLE
    if not isinstance(raw, dict):
        return _discard_unreadable(
            raw, plan_id=None, reason=unreadable, cause={"field": "record", "type": _json_type(raw)}
        )
    plan_id = raw.get("plan_id")
    if not isinstance(plan_id, str):
        cause = {"field": "plan_id", "type": _json_type(plan_id)}
        return _discard_unreadable(raw, plan_id=None, reason=unreadable, cause=cause)
    if plan_id != current_plan_id:
        return _discarded(raw, plan_id=plan_id, reason=DiscardReason.PLAN_CHANGED)
    resumable = raw.get("resumable")
    if not isinstance(resumable, bool):
        cause = {"field": "resumable", "type": _json_type(resumable)}
        return _discard_unreadable(raw, plan_id=plan_id, reason=unreadable, cause=cause)
    if not resumable:
        return _discarded(raw, plan_id=plan_id, reason=DiscardReason.NOT_RESUMABLE)
    version = raw.get("version")
    if version != SNAPSHOT_VERSION:
        # The field is read before validation and could hold anything, so only a number is logged
        # as itself; any other value is logged by its JSON type.
        cause = (
            {"version": str(version)}
            if type(version) is int
            else {"version_type": _json_type(version)}
        )
        return _discard_unreadable(
            raw, plan_id=plan_id, reason=DiscardReason.VERSION_UNSUPPORTED, cause=cause
        )
    try:
        snapshot = ResearchSnapshot.model_validate(raw)
        if snapshot.resume_at is None:
            raise ValueError("A resumable snapshot names no resume point")
    except Exception as failure:
        return _discard_unreadable_body(raw, plan_id=plan_id, part="validation", failure=failure)
    try:
        messages = messages_from_dict(snapshot.research_agent_messages)
    except Exception as failure:
        return _discard_unreadable_body(
            raw, plan_id=plan_id, part="research_agent_messages", failure=failure
        )
    try:
        data_queries = decode_data_queries(snapshot.data_queries)
    except Exception as failure:
        return _discard_unreadable_body(raw, plan_id=plan_id, part="data_queries", failure=failure)
    return ResumableSnapshot(snapshot=snapshot, messages=messages, data_queries=data_queries)


def discard_for_missing_image(resumed: ResumableSnapshot) -> DiscardedSnapshot:
    """The discard of a resumable snapshot one of whose images is gone."""
    return DiscardedSnapshot(
        plan_id=resumed.snapshot.plan_id,
        reason=DiscardReason.IMAGE_MISSING,
        resume_at=resumed.resume_at,
    )


def _json_type(value: Any) -> str:
    """The JSON type name of a decoded JSON value, for a log record that must not carry it."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _discard_unreadable_body(
    raw: dict, *, plan_id: str, part: str, failure: Exception
) -> DiscardedSnapshot:
    """The discard of a matching resumable snapshot whose `part` failed to read."""
    return _discard_unreadable(
        raw,
        plan_id=plan_id,
        reason=DiscardReason.UNREADABLE,
        cause={"part": part, "error": type(failure).__name__},
        failure=failure,
    )


def _discard_unreadable(
    raw: Any,
    *,
    plan_id: str | None,
    reason: DiscardReason,
    cause: dict[str, str],
    failure: Exception | None = None,
) -> DiscardedSnapshot:
    """The discard of a record this code cannot resume from, and its one WARNING.

    `cause` names what failed, as `key=value` facts after the reason. A `ValidationError` over a
    stored record adds only its error count, `loc` paths and error types, never its rendered text
    or traceback, which quote the stored values; any other `failure` adds its stack trace.
    """
    facts = {"reason": reason.value, **cause}
    if isinstance(failure, ValidationError):
        facts["errors"] = validation_error_summary(failure)
        failure = None
    logger.warning(
        "Snapshot cannot be read; discarding it: %s",
        " ".join(f"{key}={value}" for key, value in facts.items()),
        exc_info=failure,
    )
    if not isinstance(raw, dict):
        return DiscardedSnapshot(plan_id=None, reason=reason, resume_at=None)
    return _discarded(raw, plan_id=plan_id, reason=reason)


def _discarded(raw: dict, *, plan_id: str | None, reason: DiscardReason) -> DiscardedSnapshot:
    return DiscardedSnapshot(
        plan_id=plan_id,
        reason=reason,
        resume_at=_known(raw.get("resume_at"), ResumePoint),
        # Shown only when it is why the record is discarded.
        not_resumable_reason=(
            _known(raw.get("not_resumable_reason"), NotResumableReason)
            if reason is DiscardReason.NOT_RESUMABLE
            else None
        ),
    )


def _known[E: StrEnum](value: Any, enum: type[E]) -> E | None:
    """`value` as a member of `enum`, or `None` when another release may have written it."""
    return enum(value) if isinstance(value, str) and value in enum else None
