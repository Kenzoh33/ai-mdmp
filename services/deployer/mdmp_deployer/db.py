"""Database engine, sessions and seed data. SQLite locally and in tests, Postgres in the cluster."""

from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC. SQLite drops tzinfo, so every stored timestamp is naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # One shared in-memory connection for tests; file SQLite needs cross-thread access
        # because FastAPI runs sync endpoints and background tasks in a thread pool.
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # A bare postgresql:// URL means psycopg2 to SQLAlchemy; we install psycopg 3.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return create_engine(url, pool_pre_ping=True)


# Fault flags for v2 live here, not in the image, so the same image could run healthy too.
SEED_VERSIONS = [
    ("sentiment", "v1", {}),
    ("sentiment", "v2", {"EXTRA_LATENCY_MS": "300", "ERROR_RATE": "0.2"}),
    ("sentiment", "v3", {}),
]

# Contract thresholds. kind: absolute = value above limit, ratio = canary / stable above limit,
# drop = stable - canary above limit.
SEED_THRESHOLDS = [
    ("error_rate", "absolute", 0.05),
    ("p95_latency", "ratio", 2.0),
    ("confidence", "drop", 0.20),
]


def init_db(engine: Engine) -> sessionmaker[Session]:
    from mdmp_deployer.tables import ModelVersion, RollbackThreshold

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        for model, version, env in SEED_VERSIONS:
            exists = session.scalar(
                select(ModelVersion).where(
                    ModelVersion.model == model, ModelVersion.version == version
                )
            )
            if exists is None:
                session.add(ModelVersion(model=model, version=version, env=env))
        for metric, kind, value in SEED_THRESHOLDS:
            if session.get(RollbackThreshold, metric) is None:
                session.add(RollbackThreshold(metric=metric, kind=kind, value=value))
        session.commit()
    return session_factory
