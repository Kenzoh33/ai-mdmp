"""deployer service. Owner and contract: see .github/CODEOWNERS and docs/CONTRACTS.md.

The only service that changes Kubernetes objects in the mdmp-models namespace.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from mdmp_deployer.api import internal, router
from mdmp_deployer.config import Settings, load_settings
from mdmp_deployer.db import init_db, make_engine, utcnow
from mdmp_deployer.errors import install_error_handlers
from mdmp_deployer.k8s import KubeClient
from mdmp_deployer.metrics import MetricsSource, PrometheusMetrics
from mdmp_deployer.risk import LLMAdvisor, RiskAdvisor


def create_app(
    settings: Settings | None = None,
    kube: KubeClient | None = None,
    clock: Callable[[], datetime] = utcnow,
    metrics: MetricsSource | None = None,
    risk_advisor: RiskAdvisor | None = None,
) -> FastAPI:
    """Tests pass a fake kube client, an in-memory database URL, a fixed clock, fake metrics
    and a risk advisor that never calls OpenAI."""
    settings = settings or load_settings()
    if metrics is None and settings.prometheus_url:
        metrics = PrometheusMetrics(settings.prometheus_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session_factory = init_db(make_engine(settings.database_url))
        yield

    app = FastAPI(title="AI-MDMP deployer", lifespan=lifespan)
    app.state.settings = settings
    app.state.kube = kube
    app.state.clock = clock
    app.state.metrics = metrics
    app.state.risk_advisor = risk_advisor or LLMAdvisor(timeout_s=settings.llm_timeout_s)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(internal)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "deployer"}

    return app


app = create_app()
