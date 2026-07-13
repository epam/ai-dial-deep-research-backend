#!/usr/bin/env python3
"""Generate the local DIAL Core config files from their templates.

Two outputs, both under the gitignored `dial_conf/core/generated/`:

- `models.json` — model definitions fetched from a remote DIAL via the
  `aidial-client` library (deployments listing + per-model info); each
  chat/embedding model becomes a DIAL Core entry routed through the local
  `ai-dial-adapter-dial` service with the remote deployment as upstream,
  merged over the committed `dial_conf/core/models-template.json` with
  `roles.default.limits` rebuilt. Embeds `REMOTE_DIAL_API_KEY` in every
  upstream — that is why it is gitignored.
- `application-schemas.json` — the Deep Research application-type registration
  rendered from the committed `application-schemas-template.json`, with
  `$env:{APP_PORT}` substituted (default 5000) so DIAL Core routes to wherever
  the app actually binds (macOS occupies port 5000 with AirPlay Receiver).

Run via `make infra-config`. Requires `REMOTE_DIAL_URL` and
`REMOTE_DIAL_API_KEY` in the environment (`.env` is loaded).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import dotenv
import httpx
from aidial_client import AsyncDial, DialException
from aidial_client.types.deployment import Deployment, Features
from aidial_client.types.model import ModelInfo, ModelLimits, ModelPricing
from pydantic import Field, HttpUrl, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_CONF = REPO_ROOT / "dial_conf" / "core"
DEFAULT_TEMPLATE = CORE_CONF / "models-template.json"
DEFAULT_OUTPUT = CORE_CONF / "generated" / "models.json"
DEFAULT_SCHEMAS_TEMPLATE = CORE_CONF / "application-schemas-template.json"
DEFAULT_SCHEMAS_OUTPUT = CORE_CONF / "generated" / "application-schemas.json"

PLACEHOLDER_PATTERN = re.compile(r"\$env:\{([A-Za-z0-9_]+)}")

# Docker-network address of this repo's adapter service (see docker-compose.yml).
ADAPTER_BASE_URL = "http://ai-dial-adapter-dial:5000"

MODEL_TYPE_TO_PATH = {
    "chat": "/chat/completions",
    "embedding": "/embeddings",
}

# The deployments listing is one call; the per-model info fetches are bounded by this.
MODEL_INFO_CONCURRENCY = 8

_log = logging.getLogger(__name__)


class RemoteDialSettings(BaseSettings):
    """Remote DIAL connection used only by this script, never by the app."""

    model_config = SettingsConfigDict(env_prefix="REMOTE_DIAL_")

    url: HttpUrl
    api_key: SecretStr = Field(min_length=1)


def substitute_placeholders(text: str, values: dict[str, str]) -> str:
    """Replace `$env:{VAR}` tokens; an unknown token is an error, not a silent pass-through."""

    def _resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"no value for placeholder $env:{{{name}}}")
        return values[name]

    return PLACEHOLDER_PATTERN.sub(_resolve, text)


def render_application_schemas(template_text: str, *, app_port: str) -> str:
    rendered = substitute_placeholders(template_text, {"APP_PORT": app_port})
    json.loads(rendered)  # the rendered registration must still be valid JSON
    return rendered


async def fetch_remote_models(
    *, remote_url: str, remote_api_key: str
) -> list[tuple[Deployment, ModelInfo]]:
    """List remote deployments and fetch each model's info (capabilities, limits, pricing)."""
    async with AsyncDial(base_url=remote_url, api_key=remote_api_key) as client:
        deployments = sorted(await client.deployments.list(), key=lambda d: d.id)
        semaphore = asyncio.Semaphore(MODEL_INFO_CONCURRENCY)

        async def fetch_info(deployment: Deployment) -> tuple[Deployment, ModelInfo] | None:
            async with semaphore:
                try:
                    return deployment, await client.model.get(deployment.id)
                except DialException:
                    _log.exception("skipping %s: failed to fetch model info", deployment.id)
                    return None

        results = await asyncio.gather(*(fetch_info(deployment) for deployment in deployments))
    return [result for result in results if result]


def limits_to_config(limits: ModelLimits | None) -> dict[str, Any]:
    """Map token limits to the camelCase keys DIAL Core's config expects."""
    if limits is None:
        return {}
    values = {
        "maxTotalTokens": limits.max_total_tokens,
        "maxPromptTokens": limits.max_prompt_tokens,
        "maxCompletionTokens": limits.max_completion_tokens,
    }
    return {key: value for key, value in values.items() if value is not None}


def pricing_to_config(pricing: ModelPricing | None) -> dict[str, Any]:
    if pricing is None:
        return {}
    values = {"unit": pricing.unit, "prompt": pricing.prompt, "completion": pricing.completion}
    return {key: value for key, value in values.items() if value is not None}


def features_to_config(features: Features | None, *, deployment_id: str) -> dict[str, Any]:
    if features is None:
        return {}
    config: dict[str, Any] = {
        "systemPromptSupported": features.system_prompt,
        "toolsSupported": features.tools,
        "urlAttachmentsSupported": features.url_attachments,
        "folderAttachmentsSupported": features.folder_attachments,
    }
    config = {key: value for key, value in config.items() if value}
    if features.configuration:
        config["configurationEndpoint"] = (
            f"{ADAPTER_BASE_URL}/openai/deployments/{deployment_id}/configuration"
        )
    return config


def to_config_model(
    deployment: Deployment,
    info: ModelInfo,
    *,
    remote_url: str,
    remote_api_key: str,
) -> tuple[str, dict[str, Any]] | None:
    """Convert one remote model into a (deployment id, Core model entry) pair.

    Returns None for models that are neither chat nor embedding — those are skipped.
    """
    capabilities = info.capabilities
    if capabilities is not None and capabilities.chat_completion:
        model_type = "chat"
    elif capabilities is not None and capabilities.embeddings:
        model_type = "embedding"
    else:
        _log.info("skipping model %s: neither chat nor embedding", deployment.id)
        return None

    path = MODEL_TYPE_TO_PATH[model_type]
    entry: dict[str, Any] = {
        "type": model_type,
        "endpoint": f"{ADAPTER_BASE_URL}/openai/deployments/{deployment.id}{path}",
        "upstreams": [
            {
                "endpoint": f"{remote_url}/openai/deployments/{deployment.id}{path}",
                "key": remote_api_key,
            }
        ],
    }
    # Optional metadata, mapped to the camelCase keys DIAL Core's config expects.
    optional = {
        "displayName": deployment.display_name,
        "displayVersion": deployment.display_version,
        "description": deployment.description,
        "iconUrl": deployment.icon_url,
        "inputAttachmentTypes": deployment.input_attachment_types,
        "defaults": deployment.defaults,
        "tokenizerModel": info.tokenizer_model,
        "limits": limits_to_config(info.limits),
        "pricing": pricing_to_config(info.pricing),
        "features": features_to_config(deployment.features, deployment_id=deployment.id),
    }
    entry.update({key: value for key, value in optional.items() if value})
    return deployment.id, entry


def build_config(
    template: dict[str, Any],
    remote_models: list[tuple[Deployment, ModelInfo]],
    *,
    remote_url: str,
    remote_api_key: str,
) -> dict[str, Any]:
    """Merge converted remote models over the template and rebuild default-role limits."""
    config = json.loads(json.dumps(template))  # deep copy; keeps the input template intact
    converted = (
        to_config_model(deployment, info, remote_url=remote_url, remote_api_key=remote_api_key)
        for deployment, info in remote_models
    )
    config["models"].update(dict(entry for entry in converted if entry))
    # Grant the default role access to every model. Application instances get their
    # own limits fragment in dial_conf/core/applications.json.
    config["roles"]["default"]["limits"] = {model_id: {} for model_id in config["models"]}
    return config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schemas-template", type=Path, default=DEFAULT_SCHEMAS_TEMPLATE)
    parser.add_argument("--schemas-output", type=Path, default=DEFAULT_SCHEMAS_OUTPUT)
    args = parser.parse_args()

    dotenv.load_dotenv(REPO_ROOT / ".env")
    try:
        settings = RemoteDialSettings()
    except ValidationError as exc:
        names = ", ".join(f"REMOTE_DIAL_{error['loc'][0]}".upper() for error in exc.errors())
        raise SystemExit(
            f"missing or invalid environment variables: {names} (set them in .env)"
        ) from None

    remote_url = str(settings.url).rstrip("/")
    remote_api_key = settings.api_key.get_secret_value()

    app_port = os.environ.get("APP_PORT", "5000")
    schemas = render_application_schemas(
        args.schemas_template.read_text(encoding="utf-8"), app_port=app_port
    )
    args.schemas_output.parent.mkdir(parents=True, exist_ok=True)
    args.schemas_output.write_text(schemas, encoding="utf-8")
    print(f"rendered the app-type registration for app port {app_port} to {args.schemas_output}")

    template = json.loads(args.template.read_text(encoding="utf-8"))
    try:
        remote_models = asyncio.run(
            fetch_remote_models(remote_url=remote_url, remote_api_key=remote_api_key)
        )
    except (DialException, httpx.HTTPError) as exc:
        raise SystemExit(f"failed to fetch models from {remote_url}: {exc}") from None
    config = build_config(
        template, remote_models, remote_url=remote_url, remote_api_key=remote_api_key
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(config['models'])} models to {args.output}")


if __name__ == "__main__":
    main()
