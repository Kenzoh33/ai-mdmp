from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from mdmp_deployer.tables import AnomalyRecord, Rollback
from sqlalchemy import select


def send(client: TestClient, dep: dict, severity: str = "critical", **extra: Any) -> dict:
    body = {
        "model": dep["model"],
        "version": dep["version"],
        "track": dep["track"],
        "deployment_id": dep["id"],
        "metric": "error_rate",
        "value": 0.21,
        "threshold": 0.05,
        "severity": severity,
        "timestamp": "2026-10-19T12:00:00Z",
        **extra,
    }
    response = client.post("/internal/anomalies", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def status(client: TestClient, dep: dict) -> str:
    return client.get(f"/api/v1/deployments/{dep['id']}").json()["status"]


def test_critical_event_rolls_back_canary_and_stores_rollback(
    client: TestClient, kube: Any, canary_v2: dict
) -> None:
    result = send(client, canary_v2)

    assert result["action"] == "rollback"
    assert status(client, canary_v2) == "rolled_back"
    assert ("Deployment", "sentiment-canary") not in kube.objects
    with client.app.state.session_factory() as session:
        rollback = session.get(Rollback, result["rollback_id"])
        assert rollback.automatic is True
        assert rollback.anomaly_id == result["anomaly_id"]
        assert (rollback.from_version, rollback.to_version) == ("v2", "v1")
        assert "error_rate=0.21" in rollback.reason


def test_critical_on_stable_after_full_deploy_restores_previous(
    client: TestClient, kube: Any, stable_v1: dict, deploy: Callable[..., dict]
) -> None:
    v3 = deploy("v3")
    v3 = client.get(f"/api/v1/deployments/{v3['id']}").json()

    result = send(client, v3)

    assert result["action"] == "rollback"
    assert kube.image("stable") == "ai-mdmp-sentiment:v1"


def test_two_warnings_within_window_roll_back(
    client: TestClient, clock: Any, canary_v2: dict
) -> None:
    first = send(client, canary_v2, "warning")
    clock.advance(60)
    second = send(client, canary_v2, "warning")

    assert first["action"] == "record"
    assert second["action"] == "rollback"
    assert second["reason"] == "repeated_warnings_on_canary"


def test_warnings_outside_window_do_not_escalate(
    client: TestClient, clock: Any, canary_v2: dict
) -> None:
    send(client, canary_v2, "warning")
    clock.advance(301)
    assert send(client, canary_v2, "warning")["action"] == "record"
    assert status(client, canary_v2) == "canary"


def test_repeat_events_after_rollback_are_ignored(client: TestClient, canary_v2: dict) -> None:
    send(client, canary_v2)
    repeat = send(client, canary_v2)

    assert (repeat["action"], repeat["reason"]) == ("ignore", "already_rolled_back")
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(Rollback)).all()) == 1
        assert len(session.scalars(select(AnomalyRecord)).all()) == 2


def test_cooldown_per_model(
    client: TestClient, clock: Any, canary_v2: dict, deploy: Callable[..., dict]
) -> None:
    send(client, canary_v2)
    clock.advance(30)
    canary_v3 = deploy("v3", "canary")

    blocked = send(client, canary_v3)
    clock.advance(120)
    allowed = send(client, canary_v3)

    assert (blocked["action"], blocked["reason"]) == ("ignore", "cooldown")
    assert allowed["action"] == "rollback"


def test_unknown_deployment_is_404(client: TestClient) -> None:
    missing = {"id": "dep_missing", "model": "sentiment", "version": "v2", "track": "canary"}
    body = {
        "model": "sentiment",
        "version": "v2",
        "track": "canary",
        "deployment_id": missing["id"],
        "metric": "error_rate",
        "value": 0.2,
        "threshold": 0.05,
        "severity": "critical",
        "timestamp": "2026-10-19T12:00:00Z",
    }
    response = client.post("/internal/anomalies", json=body)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "deployment_not_found"
