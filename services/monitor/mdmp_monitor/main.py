"""monitor service. Owner and contract: see .github/CODEOWNERS and docs/CONTRACTS.md."""

from fastapi import FastAPI

app = FastAPI(title="AI-MDMP monitor")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "monitor"}
