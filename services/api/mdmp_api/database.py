import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite by default so the api starts without Postgres; set DATABASE_URL for Postgres.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api.db")

# FastAPI runs sync routes in a threadpool, so SQLite must allow use across threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
