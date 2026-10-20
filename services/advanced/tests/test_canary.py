from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from services.advanced.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_canary_rollback():
    response = client.post(
        "/canary/analyze",
        json={
            "stable": {"error_rate": 0.02, "latency_ms": 100},
            "canary": {"error_rate": 0.10, "latency_ms": 150},
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "rollback"


def test_canary_rollout():
    response = client.post(
        "/canary/analyze",
        json={
            "stable": {"error_rate": 0.05, "latency_ms": 150},
            "canary": {"error_rate": 0.02, "latency_ms": 100},
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "rollout"


def test_canary_hold():
    response = client.post(
        "/canary/analyze",
        json={
            "stable": {"error_rate": 0.02, "latency_ms": 100},
            "canary": {"error_rate": 0.03, "latency_ms": 110},
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "hold"


def test_invalid_error_rate():
    response = client.post(
        "/canary/analyze",
        json={
            "stable": {"error_rate": 1.5, "latency_ms": 100},
            "canary": {"error_rate": 0.02, "latency_ms": 100},
        },
    )
    assert response.status_code == 422


def test_prometheus_integration():
    mock_response = httpx.Response(
        200,
        json={
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {
                            "job": "ai-mdmp-monitor"
                        },
                        "value": [1234567890, "1"],
                    }
                ]
            },
        },
        request=httpx.Request(
            "GET", "http://localhost:9090/api/v1/query"
        ),
    )

    with patch("services.advanced.main.httpx.get", return_value=mock_response):
        response = client.get("/monitoring/status")

    assert response.status_code == 200
    assert response.json()["source"] == "prometheus"
    assert response.json()["targets"][0]["value"][1] == "1"
