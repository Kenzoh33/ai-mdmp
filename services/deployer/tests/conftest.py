from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mdmp_deployer.config import Settings
from mdmp_deployer.main import create_app


class FakeKube:
    """In-memory stand-in for KubernetesClient: keeps objects by (kind, name)."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple] = []
        self.ready = True

    def apply(self, body: dict[str, Any]) -> None:
        self.calls.append(("apply", body["kind"], body["metadata"]["name"]))
        self.objects[(body["kind"], body["metadata"]["name"])] = body

    def delete(self, kind: str, name: str) -> None:
        self.calls.append(("delete", kind, name))
        self.objects.pop((kind, name), None)

    def scale(self, name: str, replicas: int) -> None:
        self.calls.append(("scale", name, replicas))
        self.objects[("Deployment", name)]["spec"]["replicas"] = replicas

    def set_canary_weight(self, ingress_name: str, weight: int) -> None:
        self.calls.append(("weight", ingress_name, weight))
        annotations = self.objects[("Ingress", ingress_name)]["metadata"]["annotations"]
        annotations["nginx.ingress.kubernetes.io/canary-weight"] = str(weight)

    def deployment_ready(self, name: str) -> bool:
        return self.ready

    def image(self, track: str) -> str:
        dep = self.objects[("Deployment", f"sentiment-{track}")]
        return dep["spec"]["template"]["spec"]["containers"][0]["image"]

    def weight(self) -> str:
        ingress = self.objects[("Ingress", "sentiment-canary")]
        return ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/canary-weight"]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 19, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def make_settings(**overrides: Any) -> Settings:
    values = {
        "database_url": "sqlite://",
        "namespace": "mdmp-models",
        "image_template": "ai-mdmp-{model}:{version}",
        "in_cluster": False,
        "rollout_timeout_s": 1.0,
        "rollout_poll_s": 0.0,
        "warning_window_s": 300.0,
        "cooldown_s": 120.0,
        **overrides,
    }
    return Settings(**values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def kube() -> FakeKube:
    return FakeKube()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_client(kube: FakeKube, clock: Clock) -> Callable[..., TestClient]:
    """App with the fake kube client and a fresh in-memory database; pass Settings overrides.
    Use the result as a context manager so the lifespan creates the tables."""

    def _make(**overrides: Any) -> TestClient:
        return TestClient(create_app(settings=make_settings(**overrides), kube=kube, clock=clock))

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> Iterator[TestClient]:
    with make_client() as test_client:
        yield test_client


@pytest.fixture
def deploy(client: TestClient) -> Callable[..., dict]:
    def _deploy(version: str, strategy: str = "full", **extra: Any) -> dict:
        body = {"model": "sentiment", "version": version, "strategy": strategy, **extra}
        response = client.post("/api/v1/deployments", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _deploy


@pytest.fixture
def stable_v1(client: TestClient, deploy: Callable[..., dict]) -> dict:
    """v1 fully deployed. The rollout background task runs before post() returns."""
    created = deploy("v1", replicas=2)
    return client.get(f"/api/v1/deployments/{created['id']}").json()


@pytest.fixture
def canary_v2(stable_v1: dict, deploy: Callable[..., dict], clock: Clock) -> dict:
    clock.advance(1)  # distinct created_at so "newest first" ordering is deterministic
    return deploy("v2", "canary", initial_weight=20)
