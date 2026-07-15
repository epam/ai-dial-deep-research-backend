import os

# Required env vars must be set before settings.py is imported (it instantiates the
# Settings singleton at module load and pydantic-settings will raise if the required
# fields are missing). Tests that want to override these can do so via monkeypatch in
# their own scope.
os.environ.setdefault("DIAL_URL", "http://localhost:8080")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dial_deep_research.app.factory import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    return TestClient(app)
