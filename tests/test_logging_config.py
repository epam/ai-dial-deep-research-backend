import io
import logging
import logging.config
import re

import pytest
import uvicorn.logging

from dial_deep_research.utils.logging_config import (
    MANAGED_LOGGER_NAMES,
    OtelAwareFormatter,
    configure_logging,
)

_DEFAULT_KWARGS = {
    "log_level": "INFO",
    "app_log_level": "INFO",
    "log_format": (
        "%(levelprefix)s | %(asctime)s | %(process)d | %(name)s | %(otel_context)s%(message)s"
    ),
    "log_date_format": "%Y-%m-%d %H:%M:%S",
}

_TOUCHED_LOGGERS = ("", *MANAGED_LOGGER_NAMES)


def _make_record(name: str = "dial_deep_research.test", message: str = "hi") -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )


def _build_formatter() -> OtelAwareFormatter:
    return OtelAwareFormatter(
        fmt=_DEFAULT_KWARGS["log_format"],
        datefmt=_DEFAULT_KWARGS["log_date_format"],
        use_colors=False,
    )


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def reset_logging_state():
    """Snapshot/restore every logger configure_logging touches.

    Logging state is global — without this fixture, calling configure_logging in
    a test leaks modified `propagate` flags, handlers, and levels into every
    later test that depends on caplog or default propagation.
    """
    snapshots = []
    for name in _TOUCHED_LOGGERS:
        logger = logging.getLogger(name)
        snapshots.append(
            (
                logger,
                list(logger.handlers),
                logger.level,
                logger.propagate,
                list(logger.filters),
            )
        )

    yield

    for logger, handlers, level, propagate, filters in snapshots:
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.filters = filters


class TestOtelAwareFormatter:
    def test_omits_block_when_attribute_missing(self) -> None:
        output = _build_formatter().format(_make_record(message="plain"))

        assert "trace_id=" not in output
        assert output.endswith("plain")

    def test_omits_block_when_trace_id_is_zero(self) -> None:
        record = _make_record(message="zero-trace")
        record.otelTraceID = "0"
        record.otelSpanID = "0"
        record.otelServiceName = ""
        record.otelTraceSampled = False

        output = _build_formatter().format(record)

        assert "trace_id=" not in output
        assert output.endswith("zero-trace")

    def test_renders_block_when_trace_active(self) -> None:
        record = _make_record(message="with-trace")
        record.otelTraceID = "3fdd3958e0a9ed92c563f5af15009c15"
        record.otelSpanID = "4cc359214676ab9a"
        record.otelServiceName = "deep-research"
        record.otelTraceSampled = True

        output = _build_formatter().format(record)

        assert (
            "[trace_id=3fdd3958e0a9ed92c563f5af15009c15 "
            "span_id=4cc359214676ab9a "
            "resource.service.name=deep-research "
            "trace_sampled=True] | with-trace"
        ) in output


class TestConsoleHandler:
    def test_root_owns_the_single_console_handler(self, reset_logging_state) -> None:
        configure_logging(**_DEFAULT_KWARGS)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, OtelAwareFormatter)
        assert isinstance(handler.formatter, uvicorn.logging.DefaultFormatter)
        assert root.level == logging.INFO

    def test_record_is_emitted_exactly_once(self, capsys, reset_logging_state) -> None:
        configure_logging(**_DEFAULT_KWARGS)

        logging.getLogger("dial_deep_research.x").info("only-once")

        assert capsys.readouterr().err.count("only-once") == 1

    def test_log_date_format_override(self, reset_logging_state) -> None:
        configure_logging(**{**_DEFAULT_KWARGS, "log_date_format": "%H:%M"})

        handler = logging.getLogger().handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        buf = io.StringIO()
        handler.stream = buf
        logging.getLogger("dial_deep_research.x").info("date-test")

        # The pipe-separated layout puts the timestamp in the second field.
        fields = [f.strip() for f in _strip_ansi(buf.getvalue()).split("|")]
        assert re.fullmatch(r"\d{2}:\d{2}", fields[1])


class TestRecordRouting:
    """Managed loggers must propagate to root, where the console handler and
    the OTLP handler aidial-sdk attaches (when OTEL_LOGS_EXPORTER is set) both live."""

    def test_sdk_import_time_config_is_overridden(self, reset_logging_state) -> None:
        # aidial_sdk applies this dictConfig at import time (application.py):
        # uvicorn gets propagate=False and aidial_sdk a WARNING level with a
        # private handler. configure_logging must undo both.
        from aidial_sdk.utils.log_config import LogConfig

        logging.config.dictConfig(LogConfig().model_dump())

        configure_logging(**_DEFAULT_KWARGS)

        for name in ("uvicorn", "aidial_sdk"):
            managed = logging.getLogger(name)
            assert managed.handlers == []
            assert managed.propagate is True
        assert logging.getLogger("aidial_sdk").level == logging.INFO

    def test_managed_loggers_route_to_root_handler_exactly_once(self, reset_logging_state) -> None:
        configure_logging(**_DEFAULT_KWARGS)

        # Mirrors how aidial-sdk attaches its OTLP LoggingHandler to root
        # after configure_logging has run.
        recorder = _RecordingHandler()
        logging.getLogger().addHandler(recorder)

        emitting_loggers = (
            "dial_deep_research.x",
            *(n for n in MANAGED_LOGGER_NAMES if n != "dial_deep_research"),
        )
        for name in emitting_loggers:
            logging.getLogger(name).info("routing-check")

        arrived = [record.name for record in recorder.records]
        assert sorted(arrived) == sorted(emitting_loggers)

    def test_app_level_pin_filters_debug(self, reset_logging_state) -> None:
        configure_logging(**_DEFAULT_KWARGS)

        recorder = _RecordingHandler()
        logging.getLogger().addHandler(recorder)

        # The level pin filters at the emitting logger, even though the root
        # handlers themselves accept everything.
        logging.getLogger("dial_deep_research.x").debug("filtered-out")

        assert recorder.records == []

    def test_app_level_is_independent_of_global_level(self, reset_logging_state) -> None:
        configure_logging(**{**_DEFAULT_KWARGS, "app_log_level": "DEBUG"})

        recorder = _RecordingHandler()
        logging.getLogger().addHandler(recorder)

        logging.getLogger("dial_deep_research.x").debug("app-debug")
        logging.getLogger("httpx").debug("httpx-debug")

        assert [record.getMessage() for record in recorder.records] == ["app-debug"]
