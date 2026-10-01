"""Where the data-sources fetch runs in a turn: once, before preparation, and never on a
conversation that already handed off to research."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import dial_deep_research.app.completion as completion_module
import dial_deep_research.app.playground.runner as playground_runner_module
from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.history import PrepState
from dial_deep_research.app.mcp_tools import LoadedMcpTools
from dial_deep_research.app.playground.runner import PlaygroundRunner
from dial_deep_research.app.research.data_queries import DataQueryStore
from dial_deep_research.app_properties import ApplicationProperties

COMPLETIONS_URL = "/openai/deployments/deep-research/chat/completions"

_PROPERTIES: dict = {
    "prompts": {
        "client_name": "ACME",
        "agent_name": "ACME Deep Research",
        "data_sources_descriptions": "## Publications\n\nMarket Outlook 2025.",
    },
    "mcp_servers": [
        {
            "server_name": "datasets",
            "server_type": "statgpt",
            "deployment_id": "statgpt-mcp",
            "list_datasets_tool": "list_datasets",
            "client_meta_key": "acme.example.org/client",
            "references_table": {"title": "Datasets", "columns": [{"heading": "N", "key": "name"}]},
        }
    ],
}

_FETCHED = DataSources(text="## Publications\n\nMarket Outlook 2025.\n\nDatasets:\n[]")


def _post(client: TestClient) -> httpx.Response:
    return client.post(
        COMPLETIONS_URL,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
        headers={
            "Api-Key": "test-key",
            "X-DIAL-APPLICATION-PROPERTIES": json.dumps(_PROPERTIES),
        },
    )


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch) -> list[ApplicationProperties]:
    """Replace the fetch with one that records each call and returns `_FETCHED`."""
    calls: list[ApplicationProperties] = []

    async def fetch(properties: ApplicationProperties, **_kwargs: Any) -> DataSources:
        calls.append(properties)
        return _FETCHED

    monkeypatch.setattr(completion_module, "fetch_data_sources", fetch)
    return calls


def test_a_handed_off_conversation_makes_no_data_sources_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fetches: list[ApplicationProperties],
) -> None:
    monkeypatch.setattr(
        completion_module, "load_last_prep_state", lambda request: PrepState(research_started=True)
    )

    response = _post(client)

    assert response.status_code == 409
    assert fetches == []


def test_one_fetch_reaches_both_preparation_and_research(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fetches: list[ApplicationProperties],
) -> None:
    received: dict[str, Any] = {}

    class _Prep:
        appended_content = False

        def __init__(self, choice: Any) -> None:
            pass

        async def run(self, *, prep_state: PrepState, data_sources: DataSources, **_: Any) -> list:
            received["prep"] = data_sources
            prep_state.research_started = True
            return []

    class _Research:
        def __init__(self, choice: Any, **_: Any) -> None:
            pass

        async def run(self, _prep_state: PrepState, *, data_sources: DataSources, **_: Any) -> list:
            received["research"] = data_sources
            return []

    async def no_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(completion_module, "PrepAgentRunner", _Prep)
    monkeypatch.setattr(completion_module, "ResearchRunner", _Research)
    monkeypatch.setattr(completion_module.DeepResearchCompletion, "_persist", no_persist)

    response = _post(client)

    assert response.status_code == 200
    assert len(fetches) == 1
    assert received["prep"] is _FETCHED
    assert received["research"] is _FETCHED


async def test_the_playground_runs_its_own_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[ApplicationProperties] = []
    built: dict[str, Any] = {}

    async def fetch(properties: ApplicationProperties, **_kwargs: Any) -> DataSources:
        fetched.append(properties)
        return _FETCHED

    async def load(**_kwargs: Any) -> LoadedMcpTools:
        return LoadedMcpTools(
            agent_tools=[],
            file_sharing_tool=None,
            list_datasets_tool=None,
            client=None,  # type: ignore[arg-type]
            data_queries=DataQueryStore(),
        )

    class _Agent:
        async def astream(self, *_args: Any, **_kwargs: Any) -> Any:
            return
            yield

    def build(**kwargs: Any) -> _Agent:
        built.update(kwargs)
        return _Agent()

    monkeypatch.setattr(playground_runner_module, "fetch_data_sources", fetch)
    monkeypatch.setattr(playground_runner_module, "load_mcp_tools", load)
    monkeypatch.setattr(playground_runner_module, "build_playground_agent", build)

    properties = ApplicationProperties.model_validate(_PROPERTIES)
    await PlaygroundRunner(choice=None).run(  # type: ignore[arg-type]
        request=SimpleNamespace(messages=[]),  # type: ignore[arg-type]
        properties=properties,
    )

    assert fetched == [properties]
    assert built["data_sources"] == _FETCHED.text
