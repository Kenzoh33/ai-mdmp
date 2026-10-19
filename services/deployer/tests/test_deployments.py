from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mdmp_deployer import api
from mdmp_deployer.main import create_app

Deploy = Callable[..., dict]


def test_full_deploy_promotes_after_rollout(client: TestClient, kube: Any, deploy: Deploy) -> None:
    created = deploy("v1", replicas=2)

    assert created["status"] == "deploying"
    assert created["created_at"].endswith("+00:00")
    fetched = client.get(f"/api/v1/deployments/{created['id']}").json()
    assert fetched["status"] == "promoted"
    assert kube.image("stable") == "ai-mdmp-sentiment:v1"
    assert ("Ingress", "sentiment") in kube.objects


def test_full_deploy_fails_when_rollout_never_ready(
    kube: Any, make_client: Callable[..., TestClient]
) -> None:
    kube.ready = False
    body = {"model": "sentiment", "version": "v1", "strategy": "full"}
    with make_client(rollout_timeout_s=0.05, rollout_poll_s=0.01) as client:
        created = client.post("/api/v1/deployments", json=body).json()
        fetched = client.get(f"/api/v1/deployments/{created['id']}").json()

    assert fetched["status"] == "failed"
    assert "not ready" in fetched["reason"]


def test_canary_deploy_creates_canary_objects(kube: Any, canary_v2: dict) -> None:
    assert canary_v2["status"] == "canary"
    assert canary_v2["previous_version"] == "v1"
    assert kube.image("canary") == "ai-mdmp-sentiment:v2"
    assert kube.weight() == "20"
    pod_spec = kube.objects[("Deployment", "sentiment-canary")]["spec"]["template"]["spec"]
    assert {"name": "ERROR_RATE", "value": "0.2"} in pod_spec["containers"][0]["env"]


def test_set_weight_and_scale(client: TestClient, kube: Any, canary_v2: dict) -> None:
    dep_id = canary_v2["id"]

    weight = client.post(f"/api/v1/deployments/{dep_id}/weight", json={"percent": 50})
    scaled = client.post(f"/api/v1/deployments/{dep_id}/scale", json={"replicas": 3})

    assert weight.status_code == 200 and weight.json()["weight"] == 50
    assert kube.weight() == "50"
    assert scaled.status_code == 200 and scaled.json()["replicas"] == 3
    assert ("scale", "sentiment-canary", 3) in kube.calls


def test_promote_moves_canary_version_to_stable(
    client: TestClient, kube: Any, stable_v1: dict, canary_v2: dict
) -> None:
    response = client.post(f"/api/v1/deployments/{canary_v2['id']}/promote")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "promoted" and body["track"] == "stable"
    assert kube.image("stable") == "ai-mdmp-sentiment:v2"
    assert ("Deployment", "sentiment-canary") not in kube.objects
    assert ("Ingress", "sentiment-canary") not in kube.objects
    old = client.get(f"/api/v1/deployments/{stable_v1['id']}").json()
    assert old["active"] is False


def test_rollback_canary_zeroes_weight_and_deletes(
    client: TestClient, kube: Any, canary_v2: dict
) -> None:
    response = client.post(
        f"/api/v1/deployments/{canary_v2['id']}/rollback", json={"reason": "manual test"}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "rolled_back" and body["reason"] == "manual test"
    assert ("weight", "sentiment-canary", 0) in kube.calls
    assert ("Deployment", "sentiment-canary") not in kube.objects
    assert kube.image("stable") == "ai-mdmp-sentiment:v1"


def test_rollback_full_deploy_restores_previous_stable(
    client: TestClient, kube: Any, stable_v1: dict, deploy: Deploy
) -> None:
    v3 = deploy("v3")
    assert kube.image("stable") == "ai-mdmp-sentiment:v3"

    response = client.post(f"/api/v1/deployments/{v3['id']}/rollback", json={"reason": "bad"})

    assert response.json()["status"] == "rolled_back"
    assert kube.image("stable") == "ai-mdmp-sentiment:v1"
    restored = client.get(f"/api/v1/deployments/{stable_v1['id']}").json()
    assert restored["active"] is True


def test_list_filters_by_model(client: TestClient, canary_v2: dict) -> None:
    response = client.get("/api/v1/deployments", params={"model": "sentiment"})
    assert [d["version"] for d in response.json()] == ["v2", "v1"]
    assert client.get("/api/v1/deployments", params={"model": "other"}).json() == []


def test_errors_use_contract_envelope(client: TestClient, stable_v1: dict) -> None:
    missing = client.get("/api/v1/deployments/dep_nope")
    unknown = client.post(
        "/api/v1/deployments", json={"model": "sentiment", "version": "v9", "strategy": "full"}
    )
    invalid = client.post("/api/v1/deployments", json={"model": "sentiment"})
    not_canary = client.post(f"/api/v1/deployments/{stable_v1['id']}/weight", json={"percent": 5})
    no_previous = client.post(
        f"/api/v1/deployments/{stable_v1['id']}/rollback", json={"reason": "x"}
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "deployment_not_found"
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_version"
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "invalid_request"
    assert not_canary.status_code == 409 and not_canary.json()["error"]["code"] == "not_canary"
    assert no_previous.status_code == 409
    assert no_previous.json()["error"]["code"] == "no_previous_version"


def test_canary_rules(client: TestClient, deploy: Deploy) -> None:
    canary_v2 = {"model": "sentiment", "version": "v2", "strategy": "canary"}
    without_stable = client.post("/api/v1/deployments", json=canary_v2)
    assert without_stable.status_code == 409
    assert without_stable.json()["error"]["code"] == "no_stable"

    deploy("v1")
    deploy("v2", "canary")
    second = client.post("/api/v1/deployments", json={**canary_v2, "version": "v3"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "canary_active"


def test_no_cluster_gives_503_and_reads_still_work(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    def no_config(*args: object) -> None:
        raise RuntimeError("no kubeconfig")

    # Never touch a real cluster from tests, even if ~/.kube/config exists.
    monkeypatch.setattr(api, "KubernetesClient", no_config)
    with TestClient(create_app(settings=settings)) as client:
        listed = client.get("/api/v1/deployments")
        created = client.post(
            "/api/v1/deployments", json={"model": "sentiment", "version": "v1", "strategy": "full"}
        )

    assert listed.status_code == 200 and listed.json() == []
    assert created.status_code == 503
    assert created.json()["error"]["code"] == "kube_unavailable"
