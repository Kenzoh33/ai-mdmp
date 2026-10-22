import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from mdmp_api.database import Base, engine

DEPLOYER_URL = os.getenv("DEPLOYER_URL", "http://localhost:8001")
# Dashboard files, served at / when present (run from the repo root, or set FRONTEND_DIR).
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", "frontend/public"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables only when the actual app starts, not during test imports
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="AI-MDMP API Service", version="1.0.0", lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

async def event_generator():
    """Simulates live SSE events for the dashboard."""
    yield 'data: {"event": "deployment", "message": "v1 promoted to stable"}\n\n'
    await asyncio.sleep(5)
    yield 'data: {"event": "anomaly", "message": "High latency detected on v2 canary!"}\n\n'

@app.get("/api/v1/events")
async def sse_events():
    """SSE stream of deployment, anomaly, and rollback events."""
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def deployer_client() -> httpx.AsyncClient:
    # Long timeout: creating a deployment waits for the Kubernetes rollout.
    return httpx.AsyncClient(base_url=DEPLOYER_URL, timeout=200)

@app.api_route("/api/v1/{path:path}", methods=["GET", "POST"])
async def proxy_to_deployer(path: str, request: Request) -> Response:
    """Forward dashboard calls (deployments, feedback) to the deployer service."""
    try:
        async with deployer_client() as client:
            upstream = await client.request(
                request.method,
                f"/api/v1/{path}",
                params=request.query_params,
                content=await request.body(),
                headers={"content-type": request.headers.get("content-type", "application/json")},
            )
    except httpx.HTTPError:
        return JSONResponse(
            {"error": {"code": "deployer_unavailable", "message": "Deployer is not reachable"}},
            status_code=502,
        )
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )

# Mounted last so the API routes above take precedence over static files.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
