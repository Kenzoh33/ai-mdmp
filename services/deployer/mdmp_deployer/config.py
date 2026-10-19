"""Deployer settings. Everything comes from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    namespace: str
    image_template: str
    in_cluster: bool
    rollout_timeout_s: float
    rollout_poll_s: float
    warning_window_s: float
    cooldown_s: float
    prometheus_url: str | None
    llm_timeout_s: float


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./deployer.db"),
        namespace=os.getenv("MODELS_NAMESPACE", "mdmp-models"),
        # {model} and {version} are filled in per deployment, e.g. ai-mdmp-sentiment:v2.
        image_template=os.getenv("MODEL_IMAGE_TEMPLATE", "ai-mdmp-{model}:{version}"),
        in_cluster=os.getenv("IN_CLUSTER", "false").lower() == "true",
        rollout_timeout_s=float(os.getenv("ROLLOUT_TIMEOUT_SECONDS", "180")),
        rollout_poll_s=float(os.getenv("ROLLOUT_POLL_SECONDS", "2")),
        warning_window_s=float(os.getenv("WARNING_WINDOW_SECONDS", "300")),
        cooldown_s=float(os.getenv("ROLLBACK_COOLDOWN_SECONDS", "120")),
        # Unset = no metric snapshots; history then uses anomaly event values only.
        prometheus_url=os.getenv("PROMETHEUS_URL") or None,
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_SECONDS", "15")),
    )
