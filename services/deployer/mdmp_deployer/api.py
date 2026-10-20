"""HTTP routes: /api/v1 for clients, /internal for the monitor."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.schemas import AnomalyEvent
from mdmp_deployer.errors import DeployerError
from mdmp_deployer.history import build_history
from mdmp_deployer.k8s import KubeClient, KubernetesClient, SimulatedKubeClient
from mdmp_deployer.logs import logger
from mdmp_deployer.policy import decide
from mdmp_deployer.schemas import (
    AnomalyResult,
    DeploymentCreate,
    DeploymentOut,
    RiskOut,
    RollbackRequest,
    ScaleRequest,
    WeightRequest,
)
from mdmp_deployer.service import (
    Deployer,
    get_deployment,
    list_deployments,
    wait_for_rollout,
)
from mdmp_deployer.tables import AnomalyRecord, Rollback

router = APIRouter(prefix="/api/v1")
internal = APIRouter(prefix="/internal")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_kube(request: Request) -> KubeClient:
    """Created on first use so the app starts (and tests run) without a cluster."""
    state = request.app.state
    if state.kube is None and state.settings.simulate_k8s:
        state.kube = SimulatedKubeClient(state.settings.namespace)
    if state.kube is None:
        try:
            state.kube = KubernetesClient(state.settings.namespace, state.settings.in_cluster)
        except Exception as exc:
            raise DeployerError(503, "kube_unavailable", f"no Kubernetes config: {exc}") from exc
    return state.kube


def get_deployer(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    kube: Annotated[KubeClient, Depends(get_kube)],
) -> Deployer:
    state = request.app.state
    return Deployer(session, kube, state.settings, state.clock, state.metrics)


DeployerDep = Annotated[Deployer, Depends(get_deployer)]


@router.post("/deployments", status_code=201, response_model=DeploymentOut)
def create_deployment(
    body: DeploymentCreate, deployer: DeployerDep, request: Request, tasks: BackgroundTasks
) -> DeploymentOut:
    dep = deployer.create(body)
    if body.strategy == "full":
        state = request.app.state
        tasks.add_task(
            wait_for_rollout, state.session_factory, state.kube, state.settings, dep.id, state.clock
        )
    return DeploymentOut.model_validate(dep)


SessionDep = Annotated[Session, Depends(get_session)]


# Reads need no cluster, so they skip get_kube.
@router.get("/deployments", response_model=list[DeploymentOut])
def list_all(session: SessionDep, model: str | None = None) -> list[DeploymentOut]:
    return [DeploymentOut.model_validate(d) for d in list_deployments(session, model)]


@router.get("/deployments/{deployment_id}", response_model=DeploymentOut)
def get_one(deployment_id: str, session: SessionDep) -> DeploymentOut:
    return DeploymentOut.model_validate(get_deployment(session, deployment_id))


@router.post("/deployments/{deployment_id}/weight", response_model=DeploymentOut)
def set_weight(deployment_id: str, body: WeightRequest, deployer: DeployerDep) -> DeploymentOut:
    return DeploymentOut.model_validate(deployer.set_weight(deployment_id, body.percent))


@router.post("/deployments/{deployment_id}/scale", response_model=DeploymentOut)
def scale(deployment_id: str, body: ScaleRequest, deployer: DeployerDep) -> DeploymentOut:
    return DeploymentOut.model_validate(deployer.scale(deployment_id, body.replicas))


@router.post("/deployments/{deployment_id}/promote", response_model=DeploymentOut)
def promote(deployment_id: str, deployer: DeployerDep) -> DeploymentOut:
    return DeploymentOut.model_validate(deployer.promote(deployment_id))


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentOut)
def rollback(deployment_id: str, body: RollbackRequest, deployer: DeployerDep) -> DeploymentOut:
    deployer.rollback(deployment_id, body.reason)
    return DeploymentOut.model_validate(deployer.get(deployment_id))


@router.get("/feedback/risk", response_model=RiskOut)
async def feedback_risk(model: str, version: str, request: Request, session: SessionDep) -> RiskOut:
    """Risk of deploying `version` next, from this model's deployment history."""
    history = build_history(session, model, version)
    assessment = await request.app.state.risk_advisor.assess(history)
    return RiskOut(
        model=model,
        version=version,
        risk_level=assessment.risk_level,
        recommended_initial_weight=assessment.recommended_initial_weight,
        reasoning=assessment.reasoning,
        source=assessment.source,
        history=history.counts(),
    )


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


@internal.post("/anomalies", status_code=202, response_model=AnomalyResult)
def receive_anomaly(event: AnomalyEvent, request: Request, session: SessionDep) -> AnomalyResult:
    state = request.app.state
    clock: Callable[[], datetime] = state.clock
    now = clock()
    dep = get_deployment(session, event.deployment_id)

    window_start = now - timedelta(seconds=state.settings.warning_window_s)
    prior_warnings = session.scalar(
        select(func.count(AnomalyRecord.id)).where(
            AnomalyRecord.deployment_id == dep.id,
            AnomalyRecord.severity == "warning",
            AnomalyRecord.received_at >= window_start,
        )
    )
    recent_warnings = (prior_warnings or 0) + (1 if event.severity == "warning" else 0)
    last_rollback_at = session.scalar(
        select(func.max(Rollback.created_at)).where(Rollback.model == dep.model)
    )
    decision = decide(
        event,
        dep,
        recent_warnings=recent_warnings,
        last_rollback_at=last_rollback_at,
        now=now,
        cooldown_s=state.settings.cooldown_s,
    )

    record = AnomalyRecord(
        deployment_id=dep.id,
        model=event.model,
        version=event.version,
        track=event.track,
        metric=event.metric,
        value=event.value,
        threshold=event.threshold,
        severity=event.severity,
        ai_summary=event.ai_summary,
        timestamp=_naive_utc(event.timestamp),
        received_at=now,
        action=decision.action,
        action_reason=decision.reason,
    )
    session.add(record)
    session.commit()
    extra = {"model": dep.model, "version": dep.version, "deployment_id": dep.id}
    logger.info(
        "anomaly %s %s=%s: %s (%s)",
        event.severity,
        event.metric,
        event.value,
        decision.action,
        decision.reason,
        extra=extra,
    )

    rollback_id = None
    if decision.action == "rollback":
        # Kube is resolved only here, so recording events works without a cluster.
        deployer = Deployer(session, get_kube(request), state.settings, clock, state.metrics)
        reason = (
            f"automatic: {event.metric}={event.value:g} vs threshold {event.threshold:g} "
            f"({decision.reason})"
        )
        rollback_id = deployer.rollback(dep.id, reason, automatic=True, anomaly_id=record.id).id

    return AnomalyResult(
        action=decision.action,
        reason=decision.reason,
        deployment_id=dep.id,
        anomaly_id=record.id,
        rollback_id=rollback_id,
    )
