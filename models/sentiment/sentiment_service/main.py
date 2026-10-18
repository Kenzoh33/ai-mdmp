"""Demo sentiment model server: /predict, /health and /metrics (metrics per docs/CONTRACTS.md).

EXTRA_LATENCY_MS and ERROR_RATE inject latency and errors so v2 behaves like a broken release.
"""

import json
import logging
import os
import random
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import joblib
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from sentiment_service.train import LABELS

MODEL_NAME = "sentiment"

REQUESTS = Counter("model_requests_total", "Prediction requests", ["model", "version", "status"])
LATENCY = Histogram(
    "model_request_latency_seconds",
    "Prediction latency in seconds",
    ["model", "version"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
CONFIDENCE = Histogram(
    "model_prediction_confidence",
    "Probability of the predicted label",
    ["model", "version"],
    buckets=tuple(round(0.5 + 0.05 * i, 2) for i in range(11)),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": MODEL_NAME,
            "message": record.getMessage(),
        }
        for key in ("model", "version"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


logger = logging.getLogger("sentiment")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonFormatter())
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass(frozen=True)
class Settings:
    version: str
    model_path: str
    extra_latency_ms: float
    error_rate: float


def load_settings() -> Settings:
    return Settings(
        version=os.getenv("MODEL_VERSION", "v1"),
        model_path=os.getenv("MODEL_PATH", "/app/model/model.joblib"),
        extra_latency_ms=float(os.getenv("EXTRA_LATENCY_MS", "0")),
        error_rate=float(os.getenv("ERROR_RATE", "0")),
    )


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    app.state.settings = settings
    app.state.model = None
    log_fields = {"model": MODEL_NAME, "version": settings.version}
    try:
        app.state.model = joblib.load(settings.model_path)
        logger.info("model loaded from %s", settings.model_path, extra=log_fields)
    except FileNotFoundError:
        logger.error("model file not found: %s", settings.model_path, extra=log_fields)
    yield


app = FastAPI(title="AI-MDMP sentiment model", lifespan=lifespan)
app.state.settings = load_settings()
app.state.model = None


class PredictRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class PredictResponse(BaseModel):
    label: str
    confidence: float


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(str(err["msg"]) for err in exc.errors())
    return error_response(422, "invalid_request", message)


@app.get("/health")
def health(request: Request) -> JSONResponse:
    loaded = request.app.state.model is not None
    body = {
        "status": "ok" if loaded else "no_model",
        "model": MODEL_NAME,
        "version": request.app.state.settings.version,
        "model_loaded": loaded,
    }
    return JSONResponse(status_code=200 if loaded else 503, content=body)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest, request: Request) -> PredictResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    model = request.app.state.model
    labels = {"model": MODEL_NAME, "version": settings.version}
    start = time.perf_counter()
    status = "error"
    try:
        if model is None:
            return error_response(503, "model_not_loaded", "model is not loaded")
        if settings.extra_latency_ms > 0:
            time.sleep(settings.extra_latency_ms / 1000)
        if random.random() < settings.error_rate:
            logger.warning("injected error", extra=labels)
            return error_response(500, "injected_error", "injected failure (ERROR_RATE)")

        proba = model.predict_proba([body.text])[0]
        best = int(proba.argmax())
        confidence = float(proba[best])
        CONFIDENCE.labels(**labels).observe(confidence)
        status = "success"
        return PredictResponse(
            label=LABELS[int(model.classes_[best])], confidence=round(confidence, 4)
        )
    finally:
        REQUESTS.labels(**labels, status=status).inc()
        LATENCY.labels(**labels).observe(time.perf_counter() - start)
