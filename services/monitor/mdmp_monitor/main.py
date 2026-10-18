
"""AI-MDMP monitoring service."""

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)
import time

app = FastAPI(title="AI-MDMP monitor")

# Count monitoring requests
request_counter = Counter(
    "monitor_requests_total",
    "Total monitoring requests"
)

# Measure request response time
request_latency = Histogram(
    "monitor_request_latency_seconds",
    "Time spent processing monitoring requests"
)

# Count failed requests
request_errors = Counter(
    "monitor_request_errors_total",
    "Total failed monitoring requests"
)


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        request_errors.inc()
        raise
    finally:
        request_latency.observe(time.perf_counter() - start_time)

    if response.status_code >= 500:
        request_errors.inc()

    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "monitor"}


@app.get("/")
def home():
    request_counter.inc()
    return {"message": "AI-MDMP Monitoring Service is running!"}


@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
