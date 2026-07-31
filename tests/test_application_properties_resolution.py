"""Per-request application-properties resolution through the HTTP surface.

Tests inject properties via the `X-DIAL-APPLICATION-PROPERTIES` header — the SDK honors it when
present, so no DIAL Core round-trip is needed. A **validation** failure means the app is
misconfigured and is delivered as a protocol error; a **fetch** failure (Core unreachable) is
delivered as a service error, not masked as "not configured".
"""

import json
import logging

import httpx
import pytest
from aidial_sdk.chat_completion import Request
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
    "mcp_servers": [{"server_name": "rag", "deployment_id": "generic-rag-mcp"}],
}


def _post_completion(client: TestClient, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.post(
        COMPLETIONS_URL,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
        headers={"Api-Key": "test-key", **(headers or {})},
    )


def _content(response: httpx.Response) -> str:
    return response.json()["choices"][0]["message"]["content"]


def _error(response: httpx.Response) -> dict:
    return response.json()["error"]


def test_invalid_properties_delivered_as_protocol_error(client: TestClient) -> None:
    invalid = {"prompts": {**VALID_PROPERTIES["prompts"], "client_name": ""}}
    response = _post_completion(
        client, headers={"X-DIAL-APPLICATION-PROPERTIES": json.dumps(invalid)}
    )
    # Not a 200 completion carrying content — a real protocol error.
    assert response.status_code == 500
    assert "choices" not in response.json()
    assert "not configured" in _error(response)["display_message"]


def test_invalid_properties_record_carries_no_property_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # Content rule: property values may include client prompt content, so the validation
    # WARNING logs error locations and types only.
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.properties")
    secret_prompt = "confidential client prompt text"
    invalid = {
        "prompts": {
            **VALID_PROPERTIES["prompts"],
            "client_name": "",
            "data_sources_descriptions": secret_prompt,
        }
    }
    _post_completion(client, headers={"X-DIAL-APPLICATION-PROPERTIES": json.dumps(invalid)})

    [record] = [r for r in caplog.records if r.name == "dial_deep_research.app.properties"]
    assert "error(s)" in record.getMessage()
    assert "prompts.client_name" in record.getMessage()
    assert secret_prompt not in record.getMessage()


def test_property_fetch_failure_delivered_as_service_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(self) -> dict:
        raise httpx.ConnectError("core unreachable", request=httpx.Request("GET", "https://core"))

    monkeypatch.setattr(Request, "request_dial_application_properties", _boom)
    response = _post_completion(client)
    # A fetch failure is a service error, not a misconfiguration.
    assert response.status_code == 500
    display = _error(response)["display_message"]
    assert "not configured" not in display
    assert "required service" in display


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
    assert set(schema["properties"]) == {
        "max_research_iterations",
        "max_research_graph_steps",
        "prompts",
        "mcp_servers",
    }
    assert schema["properties"]["prompts"]["dial:meta"]["dial:propertyKind"] == "server"
    assert "$id" not in schema
    assert "$schema" not in schema
