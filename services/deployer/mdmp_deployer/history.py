"""Per-model deployment history: how past deployments ended and what their metrics looked like."""

from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.schemas import DeploymentStatus
from mdmp_deployer.tables import AnomalyRecord, Deployment, DeploymentMetric

FINISHED = (DeploymentStatus.PROMOTED, DeploymentStatus.ROLLED_BACK, DeploymentStatus.FAILED)
# For anomaly values, keep the worst one seen: highest error rate and latency, lowest confidence.
WORST = {"error_rate": max, "p95_latency": max, "confidence": min}


@dataclass
class DeploymentOutcome:
    deployment_id: str
    version: str
    strategy: str
    outcome: str
    reason: str | None
    metrics: dict[str, float] = field(default_factory=dict)
    metrics_source: str | None = None


@dataclass
class HistorySummary:
    model: str
    version: str
    deployments: list[DeploymentOutcome]

    def _count(self, status: str) -> int:
        return sum(1 for d in self.deployments if d.outcome == status)

    @property
    def version_rolled_back_before(self) -> bool:
        return any(
            d.version == self.version and d.outcome == DeploymentStatus.ROLLED_BACK
            for d in self.deployments
        )

    def counts(self) -> dict[str, int | bool]:
        return {
            "deployments": len(self.deployments),
            "promoted": self._count(DeploymentStatus.PROMOTED),
            "rolled_back": self._count(DeploymentStatus.ROLLED_BACK),
            "failed": self._count(DeploymentStatus.FAILED),
            "version_rolled_back_before": self.version_rolled_back_before,
        }

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "candidate_version": self.version,
            "summary": self.counts(),
            "deployments": [asdict(d) for d in self.deployments],
        }


def _metrics_for(session: Session, dep: Deployment) -> tuple[dict[str, float], str | None]:
    """Prometheus snapshot if one was taken, otherwise the worst anomaly event values."""
    snapshot = session.scalars(
        select(DeploymentMetric)
        .where(DeploymentMetric.deployment_id == dep.id)
        .order_by(DeploymentMetric.recorded_at)
    ).all()
    if snapshot:
        return {row.metric: row.value for row in snapshot}, "prometheus"

    values: dict[str, float] = {}
    for event in session.scalars(
        select(AnomalyRecord).where(AnomalyRecord.deployment_id == dep.id)
    ):
        pick = WORST.get(event.metric, max)
        values[event.metric] = (
            pick(values[event.metric], event.value) if event.metric in values else event.value
        )
    return values, ("anomaly_events" if values else None)


def build_history(session: Session, model: str, version: str, limit: int = 20) -> HistorySummary:
    rows = session.scalars(
        select(Deployment)
        .where(Deployment.model == model, Deployment.status.in_(FINISHED))
        .order_by(Deployment.created_at.desc())
        .limit(limit)
    ).all()
    outcomes = []
    for dep in rows:
        metrics, source = _metrics_for(session, dep)
        outcomes.append(
            DeploymentOutcome(
                deployment_id=dep.id,
                version=dep.version,
                strategy=dep.strategy,
                outcome=dep.status,
                reason=dep.reason,
                metrics=metrics,
                metrics_source=source,
            )
        )
    return HistorySummary(model=model, version=version, deployments=outcomes)
