"""Optional Prometheus snapshot of a version's metrics, taken at promote and rollback.

Queries use the contract metrics (docs/CONTRACTS.md), which carry model and version labels.
Best effort: if Prometheus is slow or down, the snapshot is skipped and the operation goes on.
"""

import math
from typing import Protocol

import httpx

QUERIES = {
    # "or vector(0)": with no errors the numerator has no series, which would hide the ratio.
    "error_rate": (
        '(sum(rate(model_requests_total{{{sel},status="error"}}[{w}])) or vector(0))'
        " / sum(rate(model_requests_total{{{sel}}}[{w}]))"
    ),
    "p95_latency": (
        "histogram_quantile(0.95, sum by (le) "
        "(rate(model_request_latency_seconds_bucket{{{sel}}}[{w}])))"
    ),
    "confidence": (
        "sum(rate(model_prediction_confidence_sum{{{sel}}}[{w}]))"
        " / sum(rate(model_prediction_confidence_count{{{sel}}}[{w}]))"
    ),
}


class MetricsSource(Protocol):
    def snapshot(self, model: str, version: str) -> dict[str, float]: ...


class PrometheusMetrics:
    def __init__(
        self,
        base_url: str,
        window: str = "5m",
        timeout_s: float = 2.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.window = window
        self.client = client or httpx.Client(timeout=timeout_s)

    def _query(self, promql: str) -> float | None:
        response = self.client.get(f"{self.base_url}/api/v1/query", params={"query": promql})
        response.raise_for_status()
        result = response.json()["data"]["result"]
        if not result:
            return None
        value = float(result[0]["value"][1])
        return None if math.isnan(value) or math.isinf(value) else value

    def snapshot(self, model: str, version: str) -> dict[str, float]:
        selector = f'model="{model}",version="{version}"'
        values: dict[str, float] = {}
        for metric, template in QUERIES.items():
            try:
                value = self._query(template.format(sel=selector, w=self.window))
            except (httpx.HTTPError, KeyError, ValueError, IndexError):
                continue
            if value is not None:
                values[metric] = round(value, 4)
        return values
