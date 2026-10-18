from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "sentiment"
    assert body["version"] == "vtest"
    assert body["model_loaded"] is True
