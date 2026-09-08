from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from grd.models import Base


def make_engine(url: str) -> Engine:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    else:
        # sane pool defaults for Postgres / other servers
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


def init_db(engine: Engine) -> None:
    """Create tables. On Postgres, ensure the pgvector extension first.

    Fine for dev; production schema changes go through Alembic (see alembic/).
    """
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:  # noqa: BLE001 - needs superuser; skip if already handled
                pass
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
