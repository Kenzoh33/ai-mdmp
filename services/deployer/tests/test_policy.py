from datetime import datetime, timedelta
from typing import Any

from mdmp_deployer.policy import decide
from mdmp_deployer.tables import Deployment

from common.schemas import AnomalyEvent

NOW = datetime(2026, 10, 19, 12, 0, 0)


def event(severity: str = "critical", track: str = "canary") -> AnomalyEvent:
    return AnomalyEvent(
        model="sentiment",
        version="v2",
        track=track,
        deployment_id="dep_1",
        metric="error_rate",
        value=0.2,
        threshold=0.05,
        severity=severity,
        timestamp=NOW,
    )


def deployment(**fields: Any) -> Deployment:
    values = {
        "id": "dep_1",
        "model": "sentiment",
        "version": "v2",
        "strategy": "canary",
        "track": "canary",
        "status": "canary",
        "active": True,
        "previous_version": "v1",
        **fields,
    }
    return Deployment(**values)


def run(ev: AnomalyEvent, dep: Deployment, warnings: int = 0, last: datetime | None = None):
    return decide(ev, dep, recent_warnings=warnings, last_rollback_at=last, now=NOW, cooldown_s=120)


def test_critical_on_canary_rolls_back() -> None:
    assert run(event(), deployment()).action == "rollback"


def test_critical_on_stable_after_full_deploy_rolls_back() -> None:
    dep = deployment(strategy="full", track="stable", status="promoted")
    decision = run(event(track="stable"), dep)
    assert (decision.action, decision.reason) == ("rollback", "critical_on_stable")


def test_critical_on_stable_without_previous_version_is_recorded() -> None:
    dep = deployment(strategy="full", track="stable", status="promoted", previous_version=None)
    assert run(event(track="stable"), dep).reason == "no_previous_version"


def test_promoted_canary_counts_as_stable() -> None:
    # Strategy canary, now stable: the canary's own rollback path no longer applies.
    dep = deployment(track="stable", status="promoted")
    assert run(event(track="canary"), dep).reason == "no_previous_version"


def test_single_warning_is_recorded() -> None:
    assert run(event("warning"), deployment(), warnings=1).action == "record"


def test_two_warnings_in_window_escalate() -> None:
    decision = run(event("warning"), deployment(), warnings=2)
    assert (decision.action, decision.reason) == ("rollback", "repeated_warnings_on_canary")


def test_info_is_recorded() -> None:
    assert run(event("info"), deployment()).reason == "info_recorded"


def test_already_rolled_back_is_ignored() -> None:
    dep = deployment(status="rolled_back", active=False)
    assert run(event(), dep).reason == "already_rolled_back"


def test_inactive_deployment_is_ignored() -> None:
    assert run(event(), deployment(active=False)).reason == "not_active"


def test_cooldown_blocks_second_rollback() -> None:
    recent = NOW - timedelta(seconds=60)
    assert run(event(), deployment(), last=recent).reason == "cooldown"


def test_cooldown_expires() -> None:
    old = NOW - timedelta(seconds=121)
    assert run(event(), deployment(), last=old).action == "rollback"
