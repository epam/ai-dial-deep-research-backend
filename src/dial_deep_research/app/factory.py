import logging
from typing import Any

from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import MetricsConfig, TelemetryConfig, TracingConfig

from dial_deep_research.app.annotations_spike.completion import AnnotationsSpikeCompletion
from dial_deep_research.app.completion import DeepResearchCompletion
from dial_deep_research.app.playground.completion import PlaygroundCompletion
from dial_deep_research.app_properties import (
    ANNOTATIONS_SPIKE_DEPLOYMENT_NAME,
    DEPLOYMENT_NAME,
    PLAYGROUND_DEPLOYMENT_NAME,
    ApplicationProperties,
)
from dial_deep_research.settings import settings
from dial_deep_research.utils.tracing import configure_opik

_log = logging.getLogger(__name__)


def create_app() -> DIALApp:
    _log.info(
        "Creating DIAL app name=%s deployment=%s",
        settings.dial_app_name,
        DEPLOYMENT_NAME,
    )

    configure_opik(
        tracing_enabled=settings.opik_tracing_enabled,
        project_name=settings.opik_project_name,
    )

    # The preparation agent is built per request (no process-wide graph or
    # checkpointer to construct eagerly).

    app = DIALApp(
        dial_url=settings.dial_url.encoded_string(),
        # Rewrite the outgoing api-key to the per-request key on every call under dial_url
        # (LLM, DIAL files, the Core-hosted MCP). See utils/llm.py and app/completion.py.
        propagate_auth_headers=True,
        add_healthcheck=True,
        telemetry_config=TelemetryConfig(
            service_name=settings.dial_app_name,
            tracing=TracingConfig(),
            metrics=MetricsConfig(),
        ),
    )

    app.add_chat_completion(
        DEPLOYMENT_NAME,
        DeepResearchCompletion(),
        heartbeat_interval=settings.heartbeat_interval,
    )

    if settings.enable_playground_channel:
        _log.info(
            "Registering playground chat completion deployment=%s", PLAYGROUND_DEPLOYMENT_NAME
        )
        app.add_chat_completion(
            PLAYGROUND_DEPLOYMENT_NAME,
            PlaygroundCompletion(),
            heartbeat_interval=settings.heartbeat_interval,
        )

    if settings.enable_annotations_spike:
        _log.info(
            "Registering annotations spike chat completion deployment=%s",
            ANNOTATIONS_SPIKE_DEPLOYMENT_NAME,
        )
        app.add_chat_completion(
            ANNOTATIONS_SPIKE_DEPLOYMENT_NAME,
            AnnotationsSpikeCompletion(),
            heartbeat_interval=settings.heartbeat_interval,
        )

    @app.get("/v1/configuration-support/application-schema")
    async def application_schema() -> dict[str, Any]:
        """The property schema DIAL Core fetches via `dial:applicationTypeSchemaEndpoint`.

        Served without the type-identity root keywords — Core supplies those from its
        `applicationTypeSchemas` entry.
        """
        return ApplicationProperties.model_json_schema(include_dial_fields=False)

    return app
