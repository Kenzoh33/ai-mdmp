import httpx
from fastapi.testclient import TestClient
from mdmp_api import main


def _use_transport(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        main,
        "deployer_client",
        lambda: httpx.AsyncClient(
            base_url="http://deployer", transport=httpx.MockTransport(handler)
        ),
    )


def test_proxy_forwards_to_deployer(monkeypatch) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": "dep_1", "status": "canary"}])

    _use_transport(monkeypatch, handler)
    response = TestClient(main.app).get("/api/v1/deployments?model=sentiment")

    assert response.status_code == 200
    assert response.json() == [{"id": "dep_1", "status": "canary"}]
    assert seen["method"] == "GET"
    assert seen["url"] == "http://deployer/api/v1/deployments?model=sentiment"


def test_proxy_passes_post_body_and_status(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.content == b'{"percent":30}'
        return httpx.Response(409, json={"error": {"code": "conflict", "message": "x"}})

    _use_transport(monkeypatch, handler)
    response = TestClient(main.app).post("/api/v1/deployments/dep_1/weight", json={"percent": 30})

    assert response.status_code == 409


def test_proxy_returns_502_when_deployer_down(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    _use_transport(monkeypatch, handler)
    response = TestClient(main.app).get("/api/v1/deployments")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "deployer_unavailable"
