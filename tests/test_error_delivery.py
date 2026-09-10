"""Failures are delivered through the DIAL error protocol, not as HTTP 200 content.

Drives the app through its HTTP surface with `stream: false`, so a raised DIAL exception surfaces
as a non-200 response whose body is the OpenAI-style `{"error": {...}}` envelope.
"""

import json

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import dial_deep_research.app.completion as completion_module
from dial_deep_research.app.history import PrepState

COMPLETIONS_URL = "/openai/deployments/deep-research/chat/completions"

VALID_PROPERTIES: dict = {
    "max_research_iterations": 3,
    "prompts": {
        "client_name": "Test Corp",
        "agent_name": "Test Deep Research",
        "data_sources_descriptions": "## report\n\nA report.",
    },
    "mcp_servers": [
        {
            "server_name": "rag",
            "server_type": "generic_rag",
            "deployment_id": "generic-rag-mcp",
            "file_sharing_tool": "get_citation_url",
        }
    ],
}

_REQUEST = httpx.Request("POST", "https://core.example/openai")


def _post(client: TestClient) -> httpx.Response:
    return client.post(
        COMPLETIONS_URL,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
        headers={
            "Api-Key": "test-key",
            "X-DIAL-APPLICATION-PROPERTIES": json.dumps(VALID_PROPERTIES),
        },
    )


def _error(response: httpx.Response) -> dict:
    return response.json()["error"]


def _runner_raising(exc: Exception):
    class _BoomRunner:
        def __init__(self, choice) -> None:
            self._choice = choice

        async def run(self, **kwargs):
            raise exc

    return _BoomRunner


def test_unexpected_error_delivered_as_protocol_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _runner_raising(RuntimeError("boom")))
    response = _post(client)
    assert response.status_code == 500
    error = _error(response)
    assert "Something went wrong" in error["display_message"]
    assert "error reference:" in error["display_message"]
    # The failure is an error body, not a successful completion carrying error content.
    assert "choices" not in response.json()


def test_error_reference_appears_in_message_and_display_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _runner_raising(RuntimeError("boom")))
    error = _error(_post(client))
    # Both fields carry the same reference; internal detail stays in the server log.
    assert error["message"] == error["display_message"]
    assert "(error reference: " in error["display_message"]


def test_content_filter_from_llm_is_actionable_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"error": {"code": "content_filter", "type": "invalid_request_error"}}
    llm_error = openai.BadRequestError(
        "blocked", response=httpx.Response(400, request=_REQUEST, json=body), body=body["error"]
    )
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _runner_raising(llm_error))
    response = _post(client)
    assert response.status_code == 400
    error = _error(response)
    assert "content management policy" in error["display_message"]
    assert error["code"] == "content_filter"


def test_upstream_rate_limit_downgraded_to_500_but_keeps_true_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"error": {"code": "429", "message": "slow down"}}
    llm_error = openai.RateLimitError(
        "rate limited",
        response=httpx.Response(429, request=_REQUEST, json=body),
        body=body["error"],
    )
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _runner_raising(llm_error))
    response = _post(client)
    # Never emit a balancer-retriable status; the true cause survives in `code`.
    assert response.status_code == 500
    assert _error(response)["code"] == "429"


def test_research_already_handed_off_delivered_as_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        completion_module, "load_last_prep_state", lambda request: PrepState(research_started=True)
    )
    response = _post(client)
    assert response.status_code == 409
    error = _error(response)
    assert "new conversation" in error["display_message"]
    assert "error reference:" in error["display_message"]
