"""Database configuration: engine, session factory and table creation.

SQLite by default (local and Docker); Postgres (Neon, on Vercel) when
``DATABASE_URL`` is a ``postgres://`` / ``postgresql://`` URL.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# The database file lives at the project root and is ignored by Git (*.db).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "ticketera.db"

# Local default: the SQLite file at the project root, exactly as before.
DEFAULT_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


def resolve_database_url(raw_url: str | None = None) -> str:
    """Return the database URL to use for this process.

    The ``DATABASE_URL`` environment variable wins when set, so Docker can
    point the app at a file inside a mounted volume
    (e.g. ``sqlite:////data/ticketera.db`` or simply ``/data/ticketera.db``).
    An empty/blank value falls back to :data:`DEFAULT_DATABASE_URL`, keeping
    the local behaviour unchanged. ``postgres://`` and ``postgresql://``
    (what Neon gives) are sent through the psycopg 3 driver.
    """
    if raw_url is None:
        raw_url = os.environ.get("DATABASE_URL")
    if raw_url is None or not raw_url.strip():
        return DEFAULT_DATABASE_URL
    cleaned = raw_url.strip()
    if cleaned.startswith("sqlite:"):
        return cleaned
    for prefix in ("postgres://", "postgresql://"):
        if cleaned.startswith(prefix):
            return "postgresql+psycopg://" + cleaned[len(prefix):]
    if cleaned.startswith("postgresql+"):
        return cleaned
    # Accept a plain file path (absolute or relative) as a convenience.
    return f"sqlite:///{cleaned}"


def es_sqlite(url_or_engine) -> bool:
    """True for a SQLite URL or engine."""
    url = str(getattr(url_or_engine, "url", url_or_engine))
    return url.startswith("sqlite")


def build_engine(url: str):
    """SQLite as always; Postgres without a local pool (each serverless call
    is short and Neon already pools connections) and checking connections
    before use."""
    if es_sqlite(url):
        db_engine = create_engine(url, connect_args={"check_same_thread": False})
        enable_sqlite_foreign_keys(db_engine)
        return db_engine
    return create_engine(url, poolclass=NullPool, pool_pre_ping=True)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def enable_sqlite_foreign_keys(db_engine) -> None:
    """Enforce SQLite foreign keys on every new connection of ``db_engine``."""

    @event.listens_for(db_engine, "connect")
    def _set_foreign_keys_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


DATABASE_URL = resolve_database_url()

engine = build_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_session():
    """FastAPI dependency: provides a session and always closes it afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(target_engine=None) -> None:
    """Create every table defined by the models and run migrations.

    Models are imported here so they register themselves on ``Base.metadata``
    even when this function is called before anything else touched the models.
    ``target_engine`` allows tests to create the schema on a different engine.
    """
    from backend import models  # noqa: F401  (import for side effects)

    db_engine = target_engine or engine
    Base.metadata.create_all(bind=db_engine)

    # Run incremental migrations (idempotent)
    from backend.migrate_add_password_hash import migrate_add_password_hash
    from backend.migrate_add_history_author_id import migrate_add_history_author_id
    from backend.migrate_categories import migrate_categories
    from backend.migrate_add_ticket_created_by import migrate_add_ticket_created_by
    from backend.migrate_remove_support_role import migrate_remove_support_role
    from backend.migrate_remove_supervisor_role import migrate_remove_supervisor_role
    from backend.migrate_add_email_conversation_id import migrate_add_email_conversation_id

    migrate_add_password_hash(db_engine)
    migrate_add_history_author_id(db_engine)
    if es_sqlite(db_engine):
        # Rebuilds the SQLite table from an old schema; a Postgres database is
        # always new (create_all already used the current categories).
        migrate_categories(db_engine)
    migrate_add_ticket_created_by(db_engine)
    migrate_remove_support_role(db_engine)
    migrate_remove_supervisor_role(db_engine)
    migrate_add_email_conversation_id(db_engine)
