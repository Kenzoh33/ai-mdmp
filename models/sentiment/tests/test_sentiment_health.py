from fastapi.testclient import TestClient
from sentiment_service.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model"] == "sentiment"
