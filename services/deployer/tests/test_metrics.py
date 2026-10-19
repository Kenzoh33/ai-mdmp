from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient
from mdmp_deployer.history import build_history
from mdmp_deployer.metrics import PrometheusMetrics
from mdmp_deployer.tables import DeploymentMetric
from sqlalchemy import select


def prometheus(handler: Callable[[httpx.Request], httpx.Response]) -> PrometheusMetrics:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PrometheusMetrics("http://prometheus:9090/", client=client)


def vector(value: str) -> httpx.Response:
    return httpx.Response(
        200, json={"status": "success", "data": {"result": [{"value": [0, value]}]}}
    )


def test_snapshot_queries_each_metric_for_the_version() -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        queries.append(query)
        if "model_requests_total" in query:
            return vector("0.2")
        if "latency" in query:
            return vector("0.31234")
        return vector("NaN")  # no confidence samples yet

    values = prometheus(handler).snapshot("sentiment", "v2")

    assert values == {"error_rate": 0.2, "p95_latency": 0.3123}
    assert len(queries) == 3
    assert all('model="sentiment",version="v2"' in q for q in queries)
    assert 'status="error"' in queries[0] and "or vector(0)" in queries[0]


def test_snapshot_is_empty_when_prometheus_fails() -> None:
    assert prometheus(lambda r: httpx.Response(503)).snapshot("sentiment", "v2") == {}

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert prometheus(refused).snapshot("sentiment", "v2") == {}


class FakeMetrics:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def snapshot(self, model: str, version: str) -> dict[str, float]:
        self.calls.append((model, version))
        if self.fail:
            raise RuntimeError("prometheus down")
        return {"error_rate": 0.18, "p95_latency": 0.42}


def deploy_and_rollback_canary(client: TestClient) -> dict:
    for version, strategy in (("v1", "full"), ("v2", "canary")):
        body = {"model": "sentiment", "version": version, "strategy": strategy}
        dep = client.post("/api/v1/deployments", json=body).json()
    response = client.post(f"/api/v1/deployments/{dep['id']}/rollback", json={"reason": "bad"})
    assert response.json()["status"] == "rolled_back"
    return dep


def test_rollback_stores_snapshot_used_by_history(
    make_client: Callable[..., TestClient],
) -> None:
    metrics = FakeMetrics()
    with make_client(metrics=metrics) as client:
        dep = deploy_and_rollback_canary(client)
        with client.app.state.session_factory() as session:
            rows = session.scalars(select(DeploymentMetric)).all()
            summary = build_history(session, "sentiment", "v3")

    assert metrics.calls == [("sentiment", "v2")]
    assert {(r.deployment_id, r.metric, r.value) for r in rows} == {
        (dep["id"], "error_rate", 0.18),
        (dep["id"], "p95_latency", 0.42),
    }
    rolled_back = next(d for d in summary.deployments if d.deployment_id == dep["id"])
    assert rolled_back.metrics_source == "prometheus"
    assert rolled_back.metrics == {"error_rate": 0.18, "p95_latency": 0.42}


def test_rollback_still_works_when_snapshot_fails(
    make_client: Callable[..., TestClient],
) -> None:
    with make_client(metrics=FakeMetrics(fail=True)) as client:
        deploy_and_rollback_canary(client)
        with client.app.state.session_factory() as session:
            assert session.scalars(select(DeploymentMetric)).all() == []
