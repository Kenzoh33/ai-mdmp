"""Deployment operations: deploy (full or canary), weight, scale, promote and rollback."""

import time
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from common.schemas import DeploymentStatus
from mdmp_deployer.config import Settings
from mdmp_deployer.errors import DeployerError
from mdmp_deployer.k8s import KubeClient
from mdmp_deployer.logs import logger
from mdmp_deployer.manifests import (
    build_canary_ingress,
    build_deployment,
    build_service,
    build_stable_ingress,
    canary_ingress_name,
    object_name,
)
from mdmp_deployer.metrics import MetricsSource
from mdmp_deployer.schemas import DeploymentCreate
from mdmp_deployer.tables import Deployment, DeploymentMetric, ModelVersion, Rollback


def active_deployment(session: Session, model: str, track: str) -> Deployment | None:
    return session.scalar(
        select(Deployment)
        .where(Deployment.model == model, Deployment.track == track, Deployment.active)
        .order_by(Deployment.created_at.desc())
    )


def get_deployment(session: Session, deployment_id: str) -> Deployment:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise DeployerError(404, "deployment_not_found", f"no deployment {deployment_id}")
    return dep


def list_deployments(session: Session, model: str | None = None) -> list[Deployment]:
    query = select(Deployment).order_by(Deployment.created_at.desc())
    if model:
        query = query.where(Deployment.model == model)
    return list(session.scalars(query))


def log_fields(dep: Deployment) -> dict[str, str]:
    return {"model": dep.model, "version": dep.version, "deployment_id": dep.id}


class Deployer:
    def __init__(
        self,
        session: Session,
        kube: KubeClient,
        settings: Settings,
        clock: Callable[[], datetime],
        metrics: MetricsSource | None = None,
    ) -> None:
        self.session = session
        self.kube = kube
        self.settings = settings
        self.clock = clock
        self.metrics = metrics

    def get(self, deployment_id: str) -> Deployment:
        return get_deployment(self.session, deployment_id)

    def _record_metrics(self, dep: Deployment) -> None:
        """Store the version's current metrics for the history. Never blocks the operation."""
        if self.metrics is None:
            return
        try:
            values = self.metrics.snapshot(dep.model, dep.version)
        except Exception as exc:
            logger.warning("metrics snapshot failed: %s", exc, extra=log_fields(dep))
            return
        now = self.clock()
        for metric, value in values.items():
            self.session.add(
                DeploymentMetric(
                    deployment_id=dep.id,
                    metric=metric,
                    value=value,
                    source="prometheus",
                    recorded_at=now,
                )
            )

    def _model_version(self, model: str, version: str) -> ModelVersion:
        mv = self.session.scalar(
            select(ModelVersion).where(ModelVersion.model == model, ModelVersion.version == version)
        )
        if mv is None:
            raise DeployerError(422, "unknown_version", f"{model} {version} is not registered")
        return mv

    def _apply_track(self, model: str, version: str, track: str, replicas: int) -> None:
        mv = self._model_version(model, version)
        image = mv.image or self.settings.image_template.format(model=model, version=version)
        ns = self.settings.namespace
        self.kube.apply(build_deployment(model, version, track, replicas, image, mv.env, ns))
        self.kube.apply(build_service(model, track, ns))

    def _remove_canary(self, model: str) -> None:
        # Weight 0 first so traffic leaves the canary even if a delete below fails.
        try:
            self.kube.set_canary_weight(canary_ingress_name(model), 0)
        except Exception as exc:  # the Ingress may already be gone
            logger.warning("could not zero canary weight: %s", exc, extra={"model": model})
        self.kube.delete("Ingress", canary_ingress_name(model))
        self.kube.delete("Service", object_name(model, "canary"))
        self.kube.delete("Deployment", object_name(model, "canary"))

    def create(self, req: DeploymentCreate) -> Deployment:
        self._model_version(req.model, req.version)
        stable = active_deployment(self.session, req.model, "stable")
        if active_deployment(self.session, req.model, "canary") is not None:
            raise DeployerError(409, "canary_active", f"{req.model} already has a canary")
        now = self.clock()

        if req.strategy == "full":
            self._apply_track(req.model, req.version, "stable", req.replicas)
            self.kube.apply(build_stable_ingress(req.model, self.settings.namespace))
            dep = Deployment(
                model=req.model,
                version=req.version,
                strategy="full",
                track="stable",
                status=DeploymentStatus.DEPLOYING,
                replicas=req.replicas,
                weight=100,
                previous_version=stable.version if stable else None,
                created_at=now,
                updated_at=now,
            )
            if stable is not None:
                stable.active = False
        else:
            if stable is None or stable.status != DeploymentStatus.PROMOTED:
                raise DeployerError(
                    409, "no_stable", f"{req.model} needs a promoted stable version first"
                )
            if stable.version == req.version:
                raise DeployerError(409, "same_version", f"{req.version} is already stable")
            self._apply_track(req.model, req.version, "canary", req.replicas)
            self.kube.apply(
                build_canary_ingress(req.model, req.initial_weight, self.settings.namespace)
            )
            dep = Deployment(
                model=req.model,
                version=req.version,
                strategy="canary",
                track="canary",
                status=DeploymentStatus.CANARY,
                replicas=req.replicas,
                weight=req.initial_weight,
                previous_version=stable.version,
                created_at=now,
                updated_at=now,
            )
        self.session.add(dep)
        self.session.commit()
        logger.info("deployment created (%s)", req.strategy, extra=log_fields(dep))
        return dep

    def _require_active(self, dep: Deployment) -> None:
        if not dep.active or dep.status == DeploymentStatus.ROLLED_BACK:
            raise DeployerError(409, "not_active", f"deployment {dep.id} is not serving traffic")

    def _require_canary(self, dep: Deployment) -> None:
        self._require_active(dep)
        if dep.track != "canary":
            raise DeployerError(409, "not_canary", f"deployment {dep.id} is not a canary")

    def set_weight(self, deployment_id: str, percent: int) -> Deployment:
        dep = self.get(deployment_id)
        self._require_canary(dep)
        self.kube.set_canary_weight(canary_ingress_name(dep.model), percent)
        dep.weight = percent
        self.session.commit()
        logger.info("canary weight set to %d", percent, extra=log_fields(dep))
        return dep

    def scale(self, deployment_id: str, replicas: int) -> Deployment:
        dep = self.get(deployment_id)
        self._require_active(dep)
        self.kube.scale(object_name(dep.model, dep.track), replicas)
        dep.replicas = replicas
        self.session.commit()
        logger.info("scaled to %d replicas", replicas, extra=log_fields(dep))
        return dep

    def promote(self, deployment_id: str) -> Deployment:
        dep = self.get(deployment_id)
        self._require_canary(dep)
        stable = active_deployment(self.session, dep.model, "stable")
        replicas = stable.replicas if stable else dep.replicas
        self._record_metrics(dep)  # before the canary pods go away
        # Stable rolls to the canary's version first; the old pods keep serving until the new
        # ones pass readiness, so removing the canary afterwards drops no traffic.
        self._apply_track(dep.model, dep.version, "stable", replicas)
        self._remove_canary(dep.model)
        if stable is not None:
            stable.active = False
        dep.track = "stable"
        dep.status = DeploymentStatus.PROMOTED
        dep.weight = 100
        dep.replicas = replicas
        dep.finished_at = self.clock()
        self.session.commit()
        logger.info("canary promoted to stable", extra=log_fields(dep))
        return dep

    def rollback(
        self,
        deployment_id: str,
        reason: str,
        automatic: bool = False,
        anomaly_id: int | None = None,
    ) -> Rollback:
        dep = self.get(deployment_id)
        self._require_active(dep)
        now = self.clock()
        self._record_metrics(dep)

        if dep.track == "canary":
            self._remove_canary(dep.model)
            dep.weight = 0
        else:
            if not dep.previous_version:
                raise DeployerError(
                    409, "no_previous_version", f"{dep.id} has no earlier stable to restore"
                )
            self._apply_track(dep.model, dep.previous_version, "stable", dep.replicas)
            self._reactivate_stable(dep, now)

        dep.active = False
        dep.status = DeploymentStatus.ROLLED_BACK
        dep.reason = reason
        dep.finished_at = now
        rollback = Rollback(
            deployment_id=dep.id,
            model=dep.model,
            from_version=dep.version,
            to_version=dep.previous_version,
            reason=reason,
            automatic=automatic,
            anomaly_id=anomaly_id,
            created_at=now,
        )
        self.session.add(rollback)
        self.session.commit()
        logger.warning("rolled back: %s", reason, extra=log_fields(dep))
        return rollback

    def _reactivate_stable(self, dep: Deployment, now: datetime) -> None:
        """Mark the restored version's row as serving again, or add one if it is missing."""
        prev = self.session.scalar(
            select(Deployment)
            .where(
                Deployment.model == dep.model,
                Deployment.version == dep.previous_version,
                Deployment.track == "stable",
                Deployment.status == DeploymentStatus.PROMOTED,
                Deployment.id != dep.id,
            )
            .order_by(Deployment.created_at.desc())
        )
        if prev is None:
            prev = Deployment(
                model=dep.model,
                version=dep.previous_version,
                strategy="full",
                track="stable",
                status=DeploymentStatus.PROMOTED,
                replicas=dep.replicas,
                weight=100,
                reason=f"restored by rollback of {dep.id}",
                created_at=now,
                updated_at=now,
                finished_at=now,
            )
            self.session.add(prev)
        prev.active = True


def wait_for_rollout(
    session_factory: sessionmaker[Session],
    kube: KubeClient,
    settings: Settings,
    deployment_id: str,
    clock: Callable[[], datetime],
) -> None:
    """Background task after a full deploy: deploying -> promoted, or failed on timeout."""
    with session_factory() as session:
        dep = session.get(Deployment, deployment_id)
        if dep is None:
            return
        name = object_name(dep.model, dep.track)
        deadline = time.monotonic() + settings.rollout_timeout_s
        ready = False
        error = None
        while time.monotonic() < deadline:
            try:
                if kube.deployment_ready(name):
                    ready = True
                    break
            except Exception as exc:
                error = str(exc)
            time.sleep(settings.rollout_poll_s)

        session.refresh(dep)
        if dep.status != DeploymentStatus.DEPLOYING:
            return  # rolled back or changed while we waited
        if ready:
            dep.status = DeploymentStatus.PROMOTED
        else:
            dep.status = DeploymentStatus.FAILED
            dep.reason = error or f"rollout not ready after {settings.rollout_timeout_s:.0f}s"
        dep.finished_at = clock()
        session.commit()
        logger.info("rollout finished: %s", dep.status, extra=log_fields(dep))
