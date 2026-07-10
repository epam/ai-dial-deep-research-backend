import os

# Required env vars must be set before settings.py is imported (it instantiates the
# Settings singleton at module load and pydantic-settings will raise if the
# SecretStr fields are missing). Tests that want to override these can do so via
# monkeypatch in their own scope.
os.environ.setdefault("DIAL_URL", "http://localhost:8080")
os.environ.setdefault("MCP_URL", "http://localhost:8000/mcp")
os.environ.setdefault("MCP_API_KEY", "test-mcp-key")
os.environ.setdefault("MCP_SERVER_NAME", "test-mcp")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dial_deep_research.app.factory import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    return TestClient(app)
