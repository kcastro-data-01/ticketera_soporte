"""Idempotent migration: add ``author_id`` column to ``history`` table.

This script is safe to run multiple times. It checks whether the column
already exists before attempting to add it, so it works on both fresh
databases and existing SQLite files (local development and Docker volume).

The column stores the id of the authenticated user that performed the
audited action; it is nullable so legacy rows (written before user audit
existed, with free-text ``author``) keep working unchanged.
"""

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_add_history_author_id(target_engine=None) -> bool:
    """Add ``author_id`` column to ``history`` if it doesn't exist.

    Returns ``True`` if the column was added, ``False`` if it already existed.
    """
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    columns = [col["name"] for col in inspector.get_columns("history")]

    if "author_id" in columns:
        return False

    with db_engine.connect() as conn:
        conn.execute(text("ALTER TABLE history ADD COLUMN author_id INTEGER"))
        conn.commit()
    return True


if __name__ == "__main__":
    added = migrate_add_history_author_id()
    if added:
        print("Migración aplicada: columna 'author_id' agregada a 'history'.")
    else:
        print("La columna 'author_id' ya existe. No se requiere migración.")
