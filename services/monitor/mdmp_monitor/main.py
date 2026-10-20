
"""AI-MDMP monitoring service."""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, Field

from common.llm import llm_client

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
    """Write structured JSON logs to the terminal and Logstash."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "ai-mdmp-monitor",
        "event": event,
        **details,
    }

    # Keep existing terminal logging
    logger.log(level, json.dumps(record))

    # Forward logs to Logstash when configured
    logstash_url = os.getenv("LOGSTASH_URL")

    if logstash_url:
        try:
            data = json.dumps(record).encode("utf-8")

            request = urllib.request.Request(
                logstash_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            urllib.request.urlopen(request, timeout=0.5).close()

        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning(
                "Could not forward log to Logstash: %s", error
            )

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


class AnomalyRequest(BaseModel):
    error_rate: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    baseline_error_rate: float = Field(ge=0, le=1)
    baseline_latency_ms: float = Field(gt=0)


@app.post("/anomalies/analyze")
async def analyze_anomaly(data: AnomalyRequest):
    """Analyze monitoring metrics for potential anomalies."""

    error_anomaly = data.error_rate > data.baseline_error_rate + 0.05
    latency_anomaly = data.latency_ms > data.baseline_latency_ms * 1.2

    anomaly_detected = error_anomaly or latency_anomaly

    if error_anomaly and latency_anomaly:
        severity = "high"
    elif anomaly_detected:
        severity = "medium"
    else:
        severity = "normal"

    prompt = (
        "You are an ML production monitoring assistant. "
        "Analyze the following monitoring metrics and explain "
        "potential anomalies and recommended next steps.\n"
        f"Current error rate: {data.error_rate}\n"
        f"Baseline error rate: {data.baseline_error_rate}\n"
        f"Current latency (ms): {data.latency_ms}\n"
        f"Baseline latency (ms): {data.baseline_latency_ms}\n"
        f"Anomaly detected: {anomaly_detected}\n"
        f"Severity: {severity}\n"
        "Provide a concise explanation. Do not claim a root cause "
        "without supporting evidence."
    )

    recommendation = await llm_client.get_response(prompt)

    log_event(
        logging.WARNING if anomaly_detected else logging.INFO,
        "anomaly_analysis",
        anomaly_detected=anomaly_detected,
        severity=severity,
    )

    return {
        "anomaly_detected": anomaly_detected,
        "severity": severity,
        "error_anomaly": error_anomaly,
        "latency_anomaly": latency_anomaly,
        "ai_analysis": recommendation,
    }
