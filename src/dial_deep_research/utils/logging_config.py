import logging
import logging.config
from typing import override

# aidial_sdk applies its own dictConfig at import time (aidial_sdk/application.py),
# setting uvicorn to propagate=False and aidial_sdk to WARNING with a private
# handler. Importing it here guarantees that side effect lands before our
# dictConfig below, so configure_logging always has the last word regardless of
# the caller's import order.
import aidial_sdk  # noqa: F401
import uvicorn.logging

# Loggers whose levels configure_logging pins explicitly. They carry no handlers
# of their own and propagate to the root logger, which owns the single "console"
# handler — and, when OTEL_LOGS_EXPORTER is set, the OTLP export handler that
# aidial-sdk attaches to root. Exposed so tests can snapshot/restore identical
# state.
MANAGED_LOGGER_NAMES: tuple[str, ...] = (
    "dial_deep_research",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "httpx",
    "httpcore",
    "openai",
    "aidial_sdk",
)

# Managed loggers that emit request/wire payloads at DEBUG (the openai client logs complete
# chat-completion request bodies). Capped at INFO unless LOG_PAYLOADS opts in, so raising
# LOG_LEVEL alone never brings payloads into the log pipeline (see the logging-policy spec).
PAYLOAD_CAPABLE_LOGGER_NAMES: tuple[str, ...] = ("httpx", "httpcore", "openai")


class OtelAwareFormatter(uvicorn.logging.DefaultFormatter):
    """Render the OTEL trace block only when a real trace is active.

    LoggingInstrumentor (enabled by aidial-sdk when OTEL_PYTHON_LOG_CORRELATION=true)
    stamps `otelTraceID` / `otelSpanID` / `otelServiceName` / `otelTraceSampled`
    onto every LogRecord. With no active span the trace ID is the literal string
    "0"; when the instrumentor never ran the attribute is absent. In both cases,
    suppress the block to keep logs readable.
    """

    @override
    def formatMessage(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "otelTraceID", None)
        if trace_id and trace_id != "0":
            record.otel_context = (
                f"[trace_id={trace_id} "
                f"span_id={getattr(record, 'otelSpanID', '0')} "
                f"resource.service.name={getattr(record, 'otelServiceName', '')} "
                f"trace_sampled={getattr(record, 'otelTraceSampled', False)}] | "
            )
        else:
            record.otel_context = ""
        return super().formatMessage(record)


def configure_logging(
    *,
    log_level: str,
    app_log_level: str,
    log_format: str,
    log_date_format: str,
    log_payloads: bool = False,
) -> None:
    """Own the process logging config: one console handler on root, managed loggers propagate.

    dictConfig strips any existing root handlers, and aidial-sdk appends its OTLP
    LoggingHandler to root during DIALApp construction — so this must run before
    the app is built.
    """

    def _level_for(name: str) -> int:
        level = logging.getLevelNamesMapping()[
            app_log_level if name == "dial_deep_research" else log_level
        ]
        if name in PAYLOAD_CAPABLE_LOGGER_NAMES and not log_payloads:
            # Cap at INFO: the more severe of LOG_LEVEL and INFO, so a stricter
            # global level (e.g. WARNING) is never lowered.
            return max(level, logging.INFO)
        return level

    per_logger_config = {
        name: {
            "handlers": [],
            "level": _level_for(name),
            # Must stay explicit: dictConfig leaves `propagate` untouched when
            # the key is absent, and both aidial-sdk's import-time config and
            # the uvicorn CLI's default config set it to False — which would
            # cut these loggers off from root and OTLP export.
            "propagate": True,
        }
        for name in MANAGED_LOGGER_NAMES
    }
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": OtelAwareFormatter,
                    "fmt": log_format,
                    "datefmt": log_date_format,
                    "use_colors": True,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": log_level,
            },
            "loggers": per_logger_config,
        }
    )
