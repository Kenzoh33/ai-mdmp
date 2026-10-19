from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import Counter, generate_latest

app = FastAPI()

request_counter = Counter(
    "monitor_requests_total",
    "Total monitoring requests"
)

@app.get("/")
def home():
    request_counter.inc()
    return {"message": "AI-MDMP Monitoring Service is running!"}

@app.get("/metrics")
def metrics():
    return Response(
        generate_latest(),
        media_type="text/plain"
    )