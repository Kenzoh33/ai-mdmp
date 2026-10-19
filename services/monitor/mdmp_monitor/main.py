
"""AI-MDMP monitoring service."""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)

app = FastAPI(title="AI-MDMP monitor")

# Configure structured JSON logging
logger = logging.getLogger("ai_mdmp_monitor")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

logger.propagate = False


def log_event(level, event, **details):
    """Write structured JSON logs to the terminal."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ai-mdmp-monitor",
        "event": event,
        **details,
    }
    logger.log(level, json.dumps(record))


# Count monitoring requests
request_counter = Counter(
    "monitor_requests_total",
    "Total monitoring requests",
)

# Measure request response time
request_latency = Histogram(
    "monitor_request_latency_seconds",
    "Time spent processing monitoring requests",
)

# Count failed requests
request_errors = Counter(
    "monitor_request_errors_total",
    "Total failed monitoring requests",
)


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start_time
        request_latency.observe(duration)
        request_errors.inc()

        log_event(
            logging.ERROR,
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_seconds=round(duration, 4),
        )
        raise

    duration = time.perf_counter() - start_time
    request_latency.observe(duration)

    if response.status_code >= 500:
        request_errors.inc()

    log_event(
        logging.ERROR if response.status_code >= 500 else logging.INFO,
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=round(duration, 4),
    )

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
        media_type=CONTENT_TYPE_LATEST,
    )
