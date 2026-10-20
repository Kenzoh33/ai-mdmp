
from unittest.mock import patch

from fastapi.testclient import TestClient

from services.monitor.mdmp_monitor.main import app

client = TestClient(app)


def test_high_severity_anomaly():
    payload = {
        "error_rate": 0.15,
        "latency_ms": 350,
        "baseline_error_rate": 0.02,
        "baseline_latency_ms": 100,
    }

    async def mock_llm_response(prompt):
        return "[MOCK MODE] Test anomaly analysis"

    with patch(
        "services.monitor.mdmp_monitor.main.llm_client.get_response",
        new=mock_llm_response,
    ):
        response = client.post("/anomalies/analyze", json=payload)

    assert response.status_code == 200

    data = response.json()
    assert data["anomaly_detected"] is True
    assert data["severity"] == "high"
    assert data["error_anomaly"] is True
    assert data["latency_anomaly"] is True
    assert data["ai_analysis"] == "[MOCK MODE] Test anomaly analysis"


def test_normal_metrics():
    payload = {
        "error_rate": 0.02,
        "latency_ms": 100,
        "baseline_error_rate": 0.02,
        "baseline_latency_ms": 100,
    }

    async def mock_llm_response(prompt):
        return "No significant anomalies."

    with patch(
        "services.monitor.mdmp_monitor.main.llm_client.get_response",
        new=mock_llm_response,
    ):
        response = client.post("/anomalies/analyze", json=payload)

    assert response.status_code == 200
    assert response.json()["anomaly_detected"] is False
    assert response.json()["severity"] == "normal"


def test_invalid_error_rate():
    payload = {
        "error_rate": 1.5,
        "latency_ms": 350,
        "baseline_error_rate": 0.02,
        "baseline_latency_ms": 100,
    }

    response = client.post("/anomalies/analyze", json=payload)

    assert response.status_code == 422
