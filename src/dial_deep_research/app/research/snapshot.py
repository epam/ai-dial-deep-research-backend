"""The snapshot a failed research run saves, so a later turn can resume it.

A snapshot is the app's own versioned JSON, stored under its own key of the failed turn's state
(`history.SNAPSHOT_STATE_KEY`). It names its resume point in the app's own terms, never by graph
node, so renaming a node does not break a pending resume: `RESUME_POINT_NODES` is the one place
the two meet. `read_snapshot` decides, header first, whether a snapshot found in the history is
resumed, discarded or refused (see the research-resume spec).
"""

from __future__ import annotations

import json
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
from pydantic import BaseModel, ConfigDict

from dial_deep_research.app.error_resolution import (
    SnapshotUnreadableError,
    SnapshotVersionUnsupportedError,
)
from dial_deep_research.app.history import SNAPSHOT_STATE_KEY, raw_dial_state
from dial_deep_research.utils.image_attachments import upload_image_blocks

from .data_queries import DataQueryRecord

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


class ResearchSnapshot(BaseModel):
    """A failed run's progress, as persisted.

    `plan_id`, `resumable` and `version` are the stable header: every format version keeps their
    names and meaning, so any release can tell whether a snapshot is to be resumed before it reads
    the rest. The channels mirror `ResearchState`, the transcript under `messages` as
    `messages_to_dict` writes it.
    """

    model_config = ConfigDict(extra="ignore")

    plan_id: str
    resumable: bool
    version: int
    resume_at: ResumePoint
    messages: list[dict[str, Any]]
    original_query: str
    plans: list[list[str]]
    research_iteration: int
    report: str | None
    report_version: int
    report_revision_instruction: str | None
    report_revision_failed: bool
    data_queries: str
    """The turn's data-query records as one JSON string (`encode_data_queries`). A client may
    rebuild a streamed answer with the DIAL SDK's chunk merge, which re-slots any list of objects
    carrying an `index` key at any depth; the records keep the server's elements whole, and a
    string is out of the merge's reach."""


class CapturedProgress(BaseModel):
    """What the research runner had seen of a run when it failed, before it becomes a snapshot."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    resume_at: ResumePoint
    messages: list[BaseMessage]
    channels: dict[str, Any]
    """The research graph's root state as the running node received it."""
    data_queries: dict[str, DataQueryRecord]


async def build_snapshot(
    progress: CapturedProgress, *, plan_id: str, resumable: bool, dial: AsyncDial
) -> ResearchSnapshot:
    """Upload the transcript's images to DIAL files, then build the snapshot to persist.

    Rewrites the image blocks of `progress.messages` in place. A failed bucket lookup re-raises
    rather than leaving placeholders, because a snapshot without its images would resume research
    without what research-agent saw.
    """
    await upload_image_blocks(progress.messages, dial, reraise_bucket_failure=True)
    channels = progress.channels
    return ResearchSnapshot(
        plan_id=plan_id,
        resumable=resumable,
        version=SNAPSHOT_VERSION,
        resume_at=progress.resume_at,
        messages=messages_to_dict(progress.messages),
        original_query=channels["original_query"],
        plans=channels["plans"],
        research_iteration=channels["research_iteration"],
        report=channels["report"],
        report_version=channels["report_version"],
        report_revision_instruction=channels["report_revision_instruction"],
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


class DiscardedSnapshot(BaseModel):
    """A snapshot found in the history that will not be resumed. Read no further than its header,
    so `resume_at` is set only when the snapshot names a known resume point."""

    plan_id: str
    reason: DiscardReason
    resume_at: ResumePoint | None

    def facts(self, *, current_plan_id: str) -> list[tuple[str, str]]:
        """What the "existing snapshot discarded" stage and log record say: ids and names only."""
        facts = [
            ("plan_id", self.plan_id),
            ("current_plan_id", current_plan_id),
            ("reason", self.reason.value),
        ]
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
    def agent_turns_completed(self) -> int | None:
        """For resume point research: the model calls the failed iteration completed, which are
        the `AIMessage`s after its instruction, the last `HumanMessage`."""
        if self.snapshot.resume_at is not ResumePoint.RESEARCH:
            return None
        turns = 0
        for message in reversed(self.messages):
            if isinstance(message, HumanMessage):
                break
            if isinstance(message, AIMessage):
                turns += 1
        return turns

    @property
    def report_review_round(self) -> int | None:
        """For resume point report review: the round to run, which reviews draft `report_version`."""
        if self.snapshot.resume_at is not ResumePoint.REPORT_REVIEW:
            return None
        return self.snapshot.report_version

    def facts(self) -> list[tuple[str, str]]:
        """What the "reusing snapshot" stage and log record say: ids, names and counts only."""
        snapshot = self.snapshot
        facts = [
            ("plan_id", snapshot.plan_id),
            ("resume_at", snapshot.resume_at.value),
            ("research_iteration", str(snapshot.research_iteration)),
            ("messages", str(len(self.messages))),
            ("report_version", str(snapshot.report_version)),
        ]
        if (turns := self.agent_turns_completed) is not None:
            facts.append(("agent_turns_completed", str(turns)))
        if (review_round := self.report_review_round) is not None:
            facts.append(("report_review_round", str(review_round)))
        return facts


def find_latest_snapshot(messages: Sequence[Message]) -> Any:
    """The raw snapshot of the latest assistant message whose state carries one, else `None`.

    Only the latest counts. Plan ids are only ever replaced by fresh ones, so when its id differs
    from the current one no older snapshot can match, and a newer snapshot marked not resumable
    shadows older ones on purpose: they belong to a run that failed in a way a resume repeats.
    """
    for message in reversed(messages):
        if message.role != Role.ASSISTANT:
            continue
        state = raw_dial_state(message)
        if state is not None and (snapshot := state.get(SNAPSHOT_STATE_KEY)) is not None:
            return snapshot
    return None


def read_snapshot(raw: Any, *, current_plan_id: str) -> ResumableSnapshot | DiscardedSnapshot:
    """Decide whether `raw` is resumed, discarded or refused, reading its header first.

    The plan id is compared first, then the resumable mark is read, so a snapshot of another plan
    or one marked not resumable is discarded whatever its version or contents. Only a matching
    resumable snapshot is read whole. Raises `SnapshotVersionUnsupportedError` for a version this
    code does not read, and `SnapshotUnreadableError` for anything else that cannot be read,
    chained to the original failure so the turn's error record carries both stack traces.
    """
    plan_id = raw.get("plan_id") if isinstance(raw, dict) else None
    if not isinstance(plan_id, str):
        raise SnapshotUnreadableError()
    if plan_id != current_plan_id:
        return _discarded(raw, plan_id=plan_id, reason=DiscardReason.PLAN_CHANGED)
    resumable = raw.get("resumable")
    if not isinstance(resumable, bool):
        raise SnapshotUnreadableError()
    if not resumable:
        return _discarded(raw, plan_id=plan_id, reason=DiscardReason.NOT_RESUMABLE)
    if raw.get("version") != SNAPSHOT_VERSION:
        raise SnapshotVersionUnsupportedError()
    try:
        snapshot = ResearchSnapshot.model_validate(raw)
        return ResumableSnapshot(
            snapshot=snapshot,
            messages=messages_from_dict(snapshot.messages),
            data_queries=decode_data_queries(snapshot.data_queries),
        )
    except Exception as failure:
        raise SnapshotUnreadableError() from failure


def _discarded(raw: dict, *, plan_id: str, reason: DiscardReason) -> DiscardedSnapshot:
    value = raw.get("resume_at")
    resume_at = ResumePoint(value) if isinstance(value, str) and value in ResumePoint else None
    return DiscardedSnapshot(plan_id=plan_id, reason=reason, resume_at=resume_at)
