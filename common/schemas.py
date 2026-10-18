"""Shared contracts used by more than one service. Change a field only after telling the team."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class DeploymentStatus(StrEnum):
    DEPLOYING = "deploying"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AnomalyEvent(BaseModel):
    model: str
    version: str
    track: Literal["stable", "canary"]
    deployment_id: str
    metric: Literal["error_rate", "p95_latency", "confidence"]
    value: float
    threshold: float
    severity: Literal["info", "warning", "critical"]
    ai_summary: str | None = None
    timestamp: datetime
