from fastapi.testclient import TestClient


def test_health_endpoint_returns_200(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
