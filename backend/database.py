"""SQLite database configuration: engine, session factory and table creation."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# The database file lives at the project root and is ignored by Git (*.db).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "ticketera.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

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
