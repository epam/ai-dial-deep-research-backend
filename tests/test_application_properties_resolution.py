"""Per-request application-properties resolution through the HTTP surface.

Tests inject properties via the `X-DIAL-APPLICATION-PROPERTIES` header — the SDK
honors it when present, so no DIAL Core round-trip is needed. Missing/invalid
properties must produce the friendly configuration error without running any agent.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import dial_deep_research.app.completion as completion_module
from dial_deep_research.app_properties import Prompts

COMPLETIONS_URL = "/openai/deployments/deep-research/chat/completions"
SCHEMA_URL = "/v1/configuration-support/application-schema"

VALID_PROPERTIES: dict = {
    "max_research_iterations": 3,
    "prompts": {
        "client_name": "Test Corp",
        "agent_name": "Test Deep Research",
        "data_sources_descriptions": "## report\n\nA report.",
    },
}


def _post_completion(client: TestClient, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.post(
        COMPLETIONS_URL,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
        headers={"Api-Key": "test-key", **(headers or {})},
    )


def _content(response: httpx.Response) -> str:
    return response.json()["choices"][0]["message"]["content"]


def test_missing_properties_returns_friendly_error(client: TestClient) -> None:
    response = _post_completion(client)
    assert response.status_code == 200
    assert "not configured" in _content(response)


def test_invalid_properties_returns_friendly_error(client: TestClient) -> None:
    invalid = {"prompts": {**VALID_PROPERTIES["prompts"], "client_name": ""}}
    response = _post_completion(
        client, headers={"X-DIAL-APPLICATION-PROPERTIES": json.dumps(invalid)}
    )
    assert response.status_code == 200
    assert "not configured" in _content(response)


def test_valid_properties_reach_the_prep_agent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    class _FakeRunner:
        def __init__(self, choice) -> None:
            self._choice = choice

        async def run(self, *, request, dial, prep_state, prompts: Prompts, opik_tracer=None):
            captured["prompts"] = prompts
            self._choice.append_content("prep ran")
            return []

    monkeypatch.setattr(completion_module, "PrepAgentRunner", _FakeRunner)
    response = _post_completion(
        client, headers={"X-DIAL-APPLICATION-PROPERTIES": json.dumps(VALID_PROPERTIES)}
    )
    assert response.status_code == 200
    assert _content(response) == "prep ran"
    assert captured["prompts"].agent_name == "Test Deep Research"
    assert captured["prompts"].client_name == "Test Corp"


def test_schema_endpoint_serves_unwrapped_schema(client: TestClient) -> None:
    response = client.get(SCHEMA_URL)
    assert response.status_code == 200
    schema = response.json()
    assert set(schema["properties"]) == {"max_research_iterations", "prompts"}
    assert schema["properties"]["prompts"]["dial:meta"]["dial:propertyKind"] == "server"
    assert "$id" not in schema
    assert "$schema" not in schema
