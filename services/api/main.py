from fastapi import FastAPI
from common.llm_client import llm_client
from services.api.database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-MDMP API Service", version="1.0.0")

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "api"}

@app.get("/api/v1/mock-llm-test")
async def test_llm():
    response = await llm_client.get_response("Are you running in mock mode?")
    return {"llm_response": response}
