from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()


def ensure_schema_updates() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("recipes"):
        return
    columns = {column["name"] for column in inspector.get_columns("recipes")}
    if "raw_html" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE recipes ADD COLUMN raw_html TEXT NOT NULL DEFAULT ''"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
