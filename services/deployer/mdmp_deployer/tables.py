"""SQLAlchemy tables for deployment state, anomalies and rollbacks."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mdmp_deployer.db import Base, utcnow


def new_deployment_id() -> str:
    return f"dep_{uuid.uuid4().hex[:10]}"


class Deployment(Base):
    """One row per deploy request. `active` marks the rows currently serving traffic:
    at most one stable and one canary per model."""

    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_deployment_id)
    model: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    strategy: Mapped[str] = mapped_column(String(16))
    track: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    replicas: Mapped[int] = mapped_column(Integer)
    weight: Mapped[int] = mapped_column(Integer, default=0)
    # Stable version that was serving when this deployment started; the rollback target.
    previous_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64))
    # Full image reference; when empty the MODEL_IMAGE_TEMPLATE setting is used.
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    env: Mapped[dict] = mapped_column(JSON, default=dict)


class RollbackThreshold(Base):
    __tablename__ = "rollback_thresholds"

    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float)


class AnomalyRecord(Base):
    """Every AnomalyEvent received, with what the policy did about it."""

    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64))
    track: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16))
    ai_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    action: Mapped[str] = mapped_column(String(32))
    action_reason: Mapped[str] = mapped_column(String(200))


class Rollback(Base):
    __tablename__ = "rollbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id"), index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    from_version: Mapped[str] = mapped_column(String(64))
    to_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_events.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeploymentMetric(Base):
    """Metric values captured from Prometheus when a deployment is promoted or rolled back."""

    __tablename__ = "deployment_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id"), index=True)
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
