import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from common.llm import llm_client
from mdmp_api.database import Base, engine

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
