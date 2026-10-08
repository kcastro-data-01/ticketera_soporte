"""SQLite database configuration: engine, session factory and table creation."""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# The database file lives at the project root and is ignored by Git (*.db).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "ticketera.db"

# Local default: the SQLite file at the project root, exactly as before.
DEFAULT_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


def resolve_database_url(raw_url: str | None = None) -> str:
    """Return the SQLite URL to use for this process.

    The ``DATABASE_URL`` environment variable wins when set, so Docker can
    point the app at a file inside a mounted volume
    (e.g. ``sqlite:////data/ticketera.db`` or simply ``/data/ticketera.db``).
    An empty/blank value falls back to :data:`DEFAULT_DATABASE_URL`, keeping
    the local behaviour unchanged.
    """
    if raw_url is None:
        raw_url = os.environ.get("DATABASE_URL")
    if raw_url is None or not raw_url.strip():
        return DEFAULT_DATABASE_URL
    cleaned = raw_url.strip()
    if cleaned.startswith("sqlite:"):
        return cleaned
    # Accept a plain file path (absolute or relative) as a convenience.
    return f"sqlite:///{cleaned}"


DATABASE_URL = resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def enable_sqlite_foreign_keys(db_engine) -> None:
    """Enforce SQLite foreign keys on every new connection of ``db_engine``."""

    @event.listens_for(db_engine, "connect")
    def _set_foreign_keys_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


enable_sqlite_foreign_keys(engine)


def get_session():
    """FastAPI dependency: provides a session and always closes it afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(target_engine=None) -> None:
    """Create every table defined by the models.

    Models are imported here so they register themselves on ``Base.metadata``
    even when this function is called before anything else touched the models.
    ``target_engine`` allows tests to create the schema on a different engine.
    """
    from backend import models  # noqa: F401  (import for side effects)

    Base.metadata.create_all(bind=target_engine or engine)
