import time
from collections.abc import Callable

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

LABELS = {"model": "sentiment", "version": "vtest"}


def sample(name: str, **labels: str) -> float:
    """Current metric value. Metrics are process-global, so tests compare before/after."""
    return REGISTRY.get_sample_value(name, {**LABELS, **labels}) or 0.0


def test_predict_returns_label_and_confidence(client: TestClient) -> None:
    before = sample("model_requests_total", status="success")
    confidence_before = sample("model_prediction_confidence_count")

    response = client.post("/predict", json={"text": "a wonderful and touching film"})

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "positive"
    assert 0.5 <= body["confidence"] <= 1.0
    assert sample("model_requests_total", status="success") - before == 1
    assert sample("model_prediction_confidence_count") - confidence_before == 1


def test_negative_review(client: TestClient) -> None:
    response = client.post("/predict", json={"text": "a boring, dull mess"})
    assert response.json()["label"] == "negative"


def test_error_injection(make_client: Callable[..., TestClient]) -> None:
    before = sample("model_requests_total", status="error")
    latency_before = sample("model_request_latency_seconds_count")

    with make_client(ERROR_RATE=1.0) as client:
        response = client.post("/predict", json={"text": "great fun"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "injected_error"
    assert sample("model_requests_total", status="error") - before == 1
    assert sample("model_request_latency_seconds_count") - latency_before == 1


def test_zero_error_rate_never_errors(client: TestClient) -> None:
    statuses = {client.post("/predict", json={"text": "great fun"}).status_code for _ in range(25)}
    assert statuses == {200}


def test_latency_injection(make_client: Callable[..., TestClient]) -> None:
    latency_before = sample("model_request_latency_seconds_sum")

    with make_client(EXTRA_LATENCY_MS=50) as client:
        start = time.perf_counter()
        response = client.post("/predict", json={"text": "great fun"})
        elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed >= 0.05
    assert sample("model_request_latency_seconds_sum") - latency_before >= 0.05


def test_metric_names_and_labels(client: TestClient) -> None:
    client.post("/predict", json={"text": "great fun"})
    lines = client.get("/metrics").text.splitlines()

    for name in (
        "model_requests_total",
        "model_request_latency_seconds_bucket",
        "model_prediction_confidence_bucket",
    ):
        matching = [line for line in lines if line.startswith(name + "{")]
        assert matching, f"{name} missing from /metrics"
        assert any('model="sentiment"' in line and 'version="vtest"' in line for line in matching)


def test_latency_buckets_match_contract(client: TestClient) -> None:
    client.post("/predict", json={"text": "great fun"})
    text = client.get("/metrics").text
    for bucket in ("0.01", "0.05", "0.1", "0.25", "0.5", "1.0", "2.5", "+Inf"):
        assert f'model_request_latency_seconds_bucket{{le="{bucket}"' in text


def test_empty_text_is_rejected(client: TestClient) -> None:
    response = client.post("/predict", json={"text": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_missing_model(make_client: Callable[..., TestClient]) -> None:
    with make_client(MODEL_PATH="/nonexistent/model.joblib") as client:
        predict = client.post("/predict", json={"text": "great fun"})
        health = client.get("/health")

    assert predict.status_code == 503
    assert predict.json()["error"]["code"] == "model_not_loaded"
    assert health.status_code == 503
    assert health.json()["model_loaded"] is False
