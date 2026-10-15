"""Demo sentiment model server (Rochak). Must expose /predict, /health and /metrics.

TODO: load the trained model, add the Prometheus metrics from docs/CONTRACTS.md, and the
EXTRA_LATENCY_MS / ERROR_RATE flags that make v2 the broken version.
"""

import os

from fastapi import FastAPI

VERSION = os.getenv("MODEL_VERSION", "v1")

app = FastAPI(title="AI-MDMP sentiment model")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": "sentiment", "version": VERSION}
