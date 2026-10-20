from dataclasses import replace

from fastapi.testclient import TestClient
from mdmp_deployer.config import Settings
from mdmp_deployer.k8s import SimulatedKubeClient
from mdmp_deployer.main import create_app
from mdmp_deployer.risk import HeuristicAdvisor


def test_simulated_client_reports_ready() -> None:
    assert SimulatedKubeClient("mdmp-models").deployment_ready("sentiment-stable") is True


def test_simulate_mode_runs_full_flow_without_a_cluster(settings: Settings) -> None:
    app = create_app(settings=replace(settings, simulate_k8s=True), risk_advisor=HeuristicAdvisor())
    with TestClient(app) as client:
        v1 = client.post(
            "/api/v1/deployments", json={"model": "sentiment", "version": "v1", "strategy": "full"}
        )
        assert v1.status_code == 201, v1.text
        v2 = client.post(
            "/api/v1/deployments",
            json={
                "model": "sentiment",
                "version": "v2",
                "strategy": "canary",
                "initial_weight": 20,
            },
        )
        assert v2.status_code == 201, v2.text

        assert isinstance(app.state.kube, SimulatedKubeClient)
        statuses = {d["version"]: d["status"] for d in client.get("/api/v1/deployments").json()}
        assert statuses == {"v1": "promoted", "v2": "canary"}
