"""Automatic rollback policy. A pure function so each rule can be tested on its own.

Rules, in order:
1. Events for a deployment that is rolled back or no longer serving are ignored.
2. Two warnings for one deployment inside the warning window count as critical.
3. Anything below critical is only recorded.
4. A critical event within the cooldown after a rollback of the same model is ignored.
5. Critical on a canary: roll the canary back (weight 0, canary objects deleted).
6. Critical on stable after a full deploy: redeploy the previous stable version.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from common.schemas import AnomalyEvent, DeploymentStatus
from mdmp_deployer.tables import Deployment


@dataclass(frozen=True)
class Decision:
    action: Literal["rollback", "record", "ignore"]
    reason: str


def decide(
    event: AnomalyEvent,
    deployment: Deployment,
    *,
    recent_warnings: int,
    last_rollback_at: datetime | None,
    now: datetime,
    cooldown_s: float,
) -> Decision:
    """recent_warnings counts warnings for this deployment inside the window, including this
    event. last_rollback_at is the latest rollback of the same model, if any."""
    if deployment.status == DeploymentStatus.ROLLED_BACK:
        return Decision("ignore", "already_rolled_back")
    if not deployment.active:
        return Decision("ignore", "not_active")

    escalated = event.severity == "warning" and recent_warnings >= 2
    if event.severity != "critical" and not escalated:
        return Decision("record", f"{event.severity}_recorded")
    why = "repeated_warnings" if escalated else "critical"

    if last_rollback_at is not None and (now - last_rollback_at).total_seconds() < cooldown_s:
        return Decision("ignore", "cooldown")

    # The deployment row's track wins over event.track: a promote may have moved it.
    if deployment.track == "canary":
        return Decision("rollback", f"{why}_on_canary")
    if deployment.strategy == "full" and deployment.previous_version:
        return Decision("rollback", f"{why}_on_stable")
    return Decision("record", "no_previous_version")
