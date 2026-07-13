"""The app enables the SDK's auth-header propagation so downstream DIAL Core calls carry
the per-request api-key (see the per-request-dial-auth change)."""

from aidial_sdk.header_propagator import FastAPIMiddleware
from fastapi.testclient import TestClient


def test_app_enables_auth_header_propagation(client: TestClient) -> None:
    assert any(m.cls is FastAPIMiddleware for m in client.app.user_middleware)
