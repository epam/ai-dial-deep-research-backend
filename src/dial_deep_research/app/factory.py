import logging

from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import MetricsConfig, TelemetryConfig, TracingConfig

from dial_deep_research.app.completion import DeepResearchCompletion
from dial_deep_research.settings import settings
from dial_deep_research.utils.tracing import configure_opik

_log = logging.getLogger(__name__)


def create_app() -> DIALApp:
    _log.info(
        "Creating DIAL app name=%s channel=%s",
        settings.dial_app_name,
        settings.channel.channel_name,
    )

    configure_opik(
        tracing_enabled=settings.opik_tracing_enabled,
        project_name=settings.channel.opik_project_name,
    )

    # The preparation agent is built per request (no process-wide graph or
    # checkpointer to construct eagerly).

    app = DIALApp(
        dial_url=settings.dial_url.encoded_string(),
        add_healthcheck=True,
        telemetry_config=TelemetryConfig(
            service_name=settings.dial_app_name,
            tracing=TracingConfig(),
            metrics=MetricsConfig(),
        ),
    )

    app.add_chat_completion(
        settings.channel.channel_name,
        DeepResearchCompletion(),
        heartbeat_interval=settings.heartbeat_interval,
    )

    return app
