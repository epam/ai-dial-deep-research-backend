"""Stand-ins for the DIAL `Choice` and `Stage` the runners write to.

`StageSpy` supports both forms the app uses: a `with` block, for stages that open and close
together, and manual `open()` / `close(status)`, for the activity stage that outlives the code
creating it. It records the lifecycle so a test can assert what the user would have seen —
including a stage left open, which is invisible in the content but spins forever in the client.

Two behaviors of the real `Stage` are reproduced on purpose, because the app has to work around
them: closing an already-closed stage raises, and `__exit__` closes unconditionally once an
exception is in flight. Together those turn a manual close inside a `with` block into an error
that masks the original exception.
"""

from __future__ import annotations

from types import TracebackType

from aidial_sdk.chat_completion import Status


class StageSpy:
    def __init__(self, title: str, events: list[tuple[str, str]] | None = None) -> None:
        self.title = title
        self.body = ""
        self.opened = False
        self.status: Status | None = None
        # Shared with the choice, so a test can see the order stages opened and closed in —
        # which is how "this stage stayed open while those ran" is checked at all.
        self._events = events if events is not None else []

    @property
    def closed(self) -> bool:
        return self.status is not None

    def append_content(self, text: str) -> None:
        self.body += text

    def append_name(self, name: str) -> None:
        # The SDK merges name deltas by concatenation, so a name can only grow.
        self.title += name

    def open(self) -> None:
        if self.opened:
            raise RuntimeError("the stage is already open")
        self.opened = True
        self._events.append(("open", self.title))

    def close(self, status: Status = Status.COMPLETED) -> None:
        if self.closed:
            raise RuntimeError("the stage is already closed")
        self.status = status
        self._events.append(("close", self.title))

    def __enter__(self) -> StageSpy:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is None:
            if not self.closed:
                self.close(Status.COMPLETED)
        else:
            self.close(Status.FAILED)
        return False


class ChoiceSpy:
    def __init__(self) -> None:
        self.content = ""
        self.stages: list[StageSpy] = []
        self.events: list[tuple[str, str]] = []

    @property
    def stage_titles(self) -> list[str]:
        return [stage.title for stage in self.stages]

    @property
    def open_stages(self) -> list[StageSpy]:
        """Stages that were opened and never closed — each one a spinner left behind."""
        return [stage for stage in self.stages if stage.opened and not stage.closed]

    def append_content(self, text: str) -> None:
        self.content += text

    def create_stage(self, title: str) -> StageSpy:
        stage = StageSpy(title, self.events)
        self.stages.append(stage)
        return stage

    def flashed_stages(self) -> list[str]:
        """Titles of stages whose close immediately followed their own open.

        Such a stage renders as a step that completed the moment it started, which is what the
        activity stage must never do.
        """
        pairs = zip(self.events, self.events[1:], strict=False)
        return [a[1] for a, b in pairs if a[0] == "open" and b == ("close", a[1])]
