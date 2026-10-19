"""Request and response bodies for the deployer API (shared contracts stay in common/schemas.py)."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class DeploymentCreate(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    strategy: Literal["full", "canary"]
    replicas: int = Field(default=1, ge=1, le=10)
    initial_weight: int = Field(default=10, ge=0, le=100)


class WeightRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class ScaleRequest(BaseModel):
    replicas: int = Field(ge=0, le=10)


class RollbackRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    version: str
    strategy: str
    track: str
    status: str
    active: bool
    replicas: int
    weight: int
    previous_version: str | None
    reason: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_serializer("created_at", "updated_at", "finished_at")
    def _utc(self, value: datetime | None) -> str | None:
        # Stored as naive UTC; send it with an explicit offset.
        return value.replace(tzinfo=UTC).isoformat() if value else None


class AnomalyResult(BaseModel):
    action: Literal["rollback", "record", "ignore"]
    reason: str
    deployment_id: str
    anomaly_id: int
    rollback_id: int | None = None


class RiskOut(BaseModel):
    model: str
    version: str
    risk_level: Literal["low", "medium", "high"]
    recommended_initial_weight: int
    reasoning: str
    source: Literal["llm", "heuristic"]
    history: dict[str, int | bool]
