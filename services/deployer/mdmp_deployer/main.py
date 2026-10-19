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


def create_app(
    settings: Settings | None = None,
    kube: KubeClient | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> FastAPI:
    """Tests pass a fake kube client, an in-memory database URL and a fixed clock."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session_factory = init_db(make_engine(settings.database_url))
        yield

    app = FastAPI(title="AI-MDMP deployer", lifespan=lifespan)
    app.state.settings = settings
    app.state.kube = kube
    app.state.clock = clock
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(internal)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "deployer"}

    return app


app = create_app()
