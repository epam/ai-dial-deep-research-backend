"""End-to-end tool-failure behaviour: the real research-agent over a real in-process MCP server.

The server is FastMCP, reached through the real `langchain-mcp-adapters` tools and the real `mcp`
streamable-HTTP client, whose HTTP transport is swapped for one that injects failures into
`tools/call` requests. Injected HTTP errors and transport failures therefore reach the tool the
way production ones do: raised inside the MCP client's task group, wrapped in an `ExceptionGroup`.

Each case asserts what the **next model call** receives, and how many times the server was
asked. Expectations are literal: a 502 is attempted three times, a 429 once. The production retry
rules are never imported into an assertion, so a change to them fails here rather than being
followed.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain.agents.middleware import tool_retry
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from dial_deep_research.app import tool_failures
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.tools import build_finish_iteration_tool
from dial_deep_research.app.tool_failures import RetryVerdict

# Shaped like a DIAL Core deployment URL, so an HTTP error's own message carries an internal-looking
# host and a deployment id — the two things the relayed result must never repeat.
_HOST = "mcp-gateway.internal.test"
_DEPLOYMENT_ID = "acme-rag-mcp"
_MCP_PATH = f"/v1/deployments/{_DEPLOYMENT_ID}/mcp"
_MCP_URL = f"http://{_HOST}{_MCP_PATH}"

# An injected failure: an HTTP status the transport answers with, or a transport error it raises.
Fault = int | Callable[[httpx.Request], Exception]


def _connect_error(request: httpx.Request) -> Exception:
    return httpx.ConnectError(f"connection refused by {request.url}", request=request)


def _read_timeout(request: httpx.Request) -> Exception:
    return httpx.ReadTimeout("timed out waiting for the response", request=request)


def _build_server() -> FastMCP:
    server = FastMCP(
        "harness",
        stateless_http=True,
        streamable_http_path=_MCP_PATH,
        # The in-process client sends the made-up host above, which the default Host-header check
        # would refuse.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @server.tool()
    def lookup(topic: str) -> str:
        """Look a topic up."""
        return f"lookup evidence about {topic}"

    @server.tool()
    def search(topic: str) -> str:
        """Search for a topic."""
        return f"search evidence about {topic}"

    @server.tool()
    def fetch_page(topic: str) -> str:
        """Fetch a page about a topic."""
        return f"page about {topic}"

    @server.tool()
    def refuse(topic: str) -> CallToolResult:
        """Reject the arguments, as a server validating its input does."""
        return CallToolResult(
            isError=True, content=[TextContent(type="text", text="year must be 1990 or later")]
        )

    @server.tool()
    def explode(topic: str) -> str:
        """Fail inside the tool's own code."""
        raise RuntimeError("database cursor closed")

    return server


class _FaultInjectingTransport(httpx.AsyncBaseTransport):
    """Forwards to the server, except for the `tools/call` requests a fault is queued for.

    Counts every `tools/call` request by tool name, faulted or not: one request is one attempt,
    since each tool invocation opens its own stateless session and sends one `tools/call`.
    """

    def __init__(self, app: Any) -> None:
        self._inner = httpx.ASGITransport(app=app)
        self.faults: dict[str, list[Fault]] = {}
        self.attempts: Counter[str] = Counter()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            if body.get("method") == "tools/call":
                tool_name = body["params"]["name"]
                self.attempts[tool_name] += 1
                queued = self.faults.get(tool_name)
                if queued:
                    fault = queued.pop(0)
                    if isinstance(fault, int):
                        return httpx.Response(fault, request=request, headers={"Retry-After": "37"})
                    raise fault(request)
        return await self._inner.handle_async_request(request)


class _ScriptedModel(GenericFakeChatModel):
    """Answers with the scripted messages and records what every call received."""

    received: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        self.received.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def _tool_call(name: str, call_id: str) -> dict[str, Any]:
    return {"name": name, "args": {"topic": "inflation"}, "id": call_id}


def _script(*tool_calls: dict[str, Any]) -> Iterator[AIMessage]:
    """One step issuing `tool_calls` in parallel, then `finish_iteration`."""
    yield AIMessage(content="", tool_calls=list(tool_calls))
    yield AIMessage(content="", tool_calls=[_tool_call("finish_iteration", "finish")])


class _Harness:
    def __init__(
        self, server: FastMCP, transport: _FaultInjectingTransport, client: MultiServerMCPClient
    ) -> None:
        self.server = server
        self.transport = transport
        self.client = client
        self.model: _ScriptedModel | None = None
        self.backoff_requests: list[dict[str, Any]] = []
        self.classified: list[Exception] = []

    def fail(self, tool_name: str, *faults: Fault) -> None:
        self.transport.faults[tool_name] = list(faults)

    async def run(
        self, monkeypatch: pytest.MonkeyPatch, *tool_calls: dict[str, Any]
    ) -> dict[str, Any]:
        model = _ScriptedModel(messages=_script(*tool_calls))
        self.model = model
        monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
        # Entered here rather than in the fixture: the session manager runs an anyio task group,
        # which must be exited by the task that entered it, and a fixture's setup and teardown run
        # in different tasks.
        async with self.server.session_manager.run():
            tools = await self.client.get_tools()
            agent = nodes.build_research_agent(
                tools=[*tools, build_finish_iteration_tool()],
                today_date="2026-09-22",
                client_name="ACME",
            )
            # `research_iteration` is the research graph's channel the agent's iteration counter
            # increments; the agent runs here without that graph around it.
            return await agent.ainvoke(
                {"messages": [HumanMessage(content="Research inflation.")], "research_iteration": 0}
            )

    def next_model_call_tool_results(self) -> dict[str, ToolMessage]:
        """The tool results the model received on the call after the tool step, by call id."""
        assert self.model is not None
        second_call = self.model.received[1]
        return {m.tool_call_id: m for m in second_call if isinstance(m, ToolMessage)}


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Harness:
    # FastMCP reads a `.env` from the working directory; an empty one keeps the test hermetic.
    monkeypatch.chdir(tmp_path)
    server = _build_server()
    transport = _FaultInjectingTransport(server.streamable_http_app())

    def client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, headers=headers, timeout=timeout, auth=auth)

    client = MultiServerMCPClient(
        connections={
            "harness": {
                "transport": "streamable_http",
                "url": _MCP_URL,
                "httpx_client_factory": client_factory,
            }
        }
    )
    result = _Harness(server=server, transport=transport, client=client)

    # No real waiting between attempts; the requested backoff is recorded instead.
    def record_backoff(retry_number: int, **kwargs: Any) -> float:
        result.backoff_requests.append({"retry_number": retry_number, **kwargs})
        return 0.0

    monkeypatch.setattr(tool_retry, "calculate_delay", record_backoff)

    # Record what the retry decision is taken on, to prove the failure arrives wrapped.
    real_predicate = tool_failures.is_immediately_retryable

    def recording_predicate(e: Exception) -> bool:
        result.classified.append(e)
        return real_predicate(e)

    monkeypatch.setattr(tool_failures, "is_immediately_retryable", recording_predicate)
    return result


async def test_the_agent_is_told_what_each_verdict_means(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.run(monkeypatch, _tool_call("lookup", "c1"))

    assert harness.model is not None
    system = harness.model.received[0][0]
    assert isinstance(system, SystemMessage)
    for verdict in RetryVerdict:
        assert f"**{verdict.value}**" in system.text


async def test_a_successful_call_reaches_the_agent_unchanged(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.run(monkeypatch, _tool_call("lookup", "c1"))

    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "success"
    assert "lookup evidence about inflation" in result.text
    assert harness.transport.attempts["lookup"] == 1


async def test_a_server_reported_error_carries_the_servers_content_and_no_verdict(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.run(monkeypatch, _tool_call("refuse", "c1"))

    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "error"
    assert "year must be 1990 or later" in result.text
    assert "Verdict:" not in result.text
    assert harness.transport.attempts["refuse"] == 1


async def test_a_transport_failure_is_retried_twice_and_relayed(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", _connect_error, _connect_error, _connect_error)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 3
    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "error"
    assert "`fetch_page`" in result.text
    assert "ConnectError" in result.text
    assert "Verdict: retrying may help." in result.text


async def test_a_wrapped_502_is_retried_exactly_twice_then_relayed(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", 502, 502, 502)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    # The decision is taken on the wrapper the MCP client raises, not on a bare HTTP error; a
    # retry rule matching exception types would see no 502 here and never retry.
    assert harness.classified
    assert all(isinstance(e, ExceptionGroup) for e in harness.classified)
    assert harness.transport.attempts["fetch_page"] == 3
    assert harness.backoff_requests == [
        {
            "retry_number": 0,
            "backoff_factor": 2.0,
            "initial_delay": 1.0,
            "max_delay": 60.0,
            "jitter": True,
        },
        {
            "retry_number": 1,
            "backoff_factor": 2.0,
            "initial_delay": 1.0,
            "max_delay": 60.0,
            "jitter": True,
        },
    ]
    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "error"
    assert "HTTPStatusError (HTTP status 502)" in result.text
    assert "Verdict: retrying may help." in result.text


async def test_a_429_is_called_once_and_relayed_as_retry_later(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", 429)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 1
    assert harness.backoff_requests == []
    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "error"
    assert "HTTP status 429" in result.text
    assert "Verdict: retry later." in result.text
    assert "rate limited" in result.text
    # The server's Retry-After interval is withheld: the agent cannot wait for it.
    assert "37" not in result.text


async def test_a_403_is_called_once_and_relayed_as_not_worth_retrying(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", 403)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 1
    result = harness.next_model_call_tool_results()["c1"]
    assert "Verdict: retrying will not help." in result.text


async def test_a_read_timeout_is_called_once_and_relayed_as_not_worth_retrying(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", _read_timeout)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 1
    assert harness.backoff_requests == []
    result = harness.next_model_call_tool_results()["c1"]
    assert "ReadTimeout" in result.text
    assert "Verdict: retrying will not help." in result.text


async def test_siblings_of_a_failed_call_still_reach_the_agent(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", _connect_error, _connect_error, _connect_error)

    await harness.run(
        monkeypatch,
        _tool_call("lookup", "c1"),
        _tool_call("search", "c2"),
        _tool_call("fetch_page", "c3"),
    )

    results = harness.next_model_call_tool_results()
    assert set(results) == {"c1", "c2", "c3"}
    assert results["c1"].status == "success"
    assert "lookup evidence about inflation" in results["c1"].text
    assert results["c2"].status == "success"
    assert "search evidence about inflation" in results["c2"].text
    assert results["c3"].status == "error"


async def test_a_retry_that_succeeds_is_one_result_and_one_log_record(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.tool_failures")
    harness.fail("fetch_page", _connect_error)

    final_state = await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 2
    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "success"
    assert "page about inflation" in result.text
    # The runner renders one stage per tool result, keyed on the call id; one result means one
    # stage, and the conversation the app persists records one call.
    results_for_call = [
        m for m in final_state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "c1"
    ]
    assert len(results_for_call) == 1
    assert [r.getMessage() for r in caplog.records] == [
        "Retrying tool call: tool=fetch_page failure=ConnectError status=None attempt=2"
    ]


async def test_the_relayed_result_carries_no_endpoint(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", 502, 502, 502)

    await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    # The failure's own text does name the endpoint; the result must not repeat it.
    assert any(_HOST in str(leaf) for e in harness.classified for leaf in e.exceptions)
    text = harness.next_model_call_tool_results()["c1"].text
    assert _HOST not in text
    assert _DEPLOYMENT_ID not in text
    assert "/v1/deployments" not in text
    assert "://" not in text


async def test_an_exception_inside_the_tool_is_relayed_rather_than_ending_the_turn(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    final_state = await harness.run(monkeypatch, _tool_call("explode", "c1"))

    result = harness.next_model_call_tool_results()["c1"]
    assert result.status == "error"
    assert "database cursor closed" in result.text
    assert harness.transport.attempts["explode"] == 1
    # The turn went on: research-agent ended the iteration with its sentinel.
    assert final_state["messages"][-1].name == "finish_iteration"


async def test_a_server_error_status_is_relayed_as_retry_later_without_a_retry(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.fail("fetch_page", 500)

    final_state = await harness.run(monkeypatch, _tool_call("fetch_page", "c1"))

    assert harness.transport.attempts["fetch_page"] == 1
    result = harness.next_model_call_tool_results()["c1"]
    assert "HTTP status 500" in result.text
    assert "Verdict: retry later." in result.text
    assert final_state["messages"][-1].name == "finish_iteration"
