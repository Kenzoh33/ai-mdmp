from unittest.mock import patch

from fastapi.testclient import TestClient

from services.monitor.mdmp_monitor.main import app

client = TestClient(app)

PAYLOAD = {
    "error_rate": 0.15,
    "latency_ms": 350,
    "baseline_error_rate": 0.02,
    "baseline_latency_ms": 100,
}


async def mock_llm_response(prompt):
    return "[MOCK MODE] Test anomaly analysis"


def _analyze(payload, sent):
    async def fake_notify(event):
        sent.append(event)
        return True

    with (
        patch("services.monitor.mdmp_monitor.main.llm_client.get_response", new=mock_llm_response),
        patch("services.monitor.mdmp_monitor.main.notify_deployer", new=fake_notify),
    ):
        return client.post("/anomalies/analyze", json=payload)


def test_high_severity_sends_critical_event_to_deployer():
    sent = []
    response = _analyze({**PAYLOAD, "deployment_id": "dep_1"}, sent)

    assert response.json()["deployer_notified"] is True
    assert len(sent) == 1
    event = sent[0]
    assert event.deployment_id == "dep_1"
    assert event.severity == "critical"
    assert event.metric == "error_rate"
    assert event.track == "canary"
    assert event.ai_summary == "[MOCK MODE] Test anomaly analysis"


def test_latency_only_sends_warning():
    sent = []
    payload = {**PAYLOAD, "error_rate": 0.02, "deployment_id": "dep_1"}
    _analyze(payload, sent)

    assert sent[0].severity == "warning"
    assert sent[0].metric == "p95_latency"


def test_no_deployment_id_or_no_anomaly_sends_nothing():
    sent = []
    _analyze(PAYLOAD, sent)
    _analyze({**PAYLOAD, "error_rate": 0.02, "latency_ms": 100, "deployment_id": "dep_1"}, sent)

    assert sent == []
