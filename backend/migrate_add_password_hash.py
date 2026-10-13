"""Idempotent migration: add ``password_hash`` column to ``users`` table.

This script is safe to run multiple times. It checks whether the column
already exists before attempting to add it, so it works on both fresh
databases and existing SQLite files (local development and Docker volume).
"""

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_add_password_hash(target_engine=None) -> bool:
    """Add ``password_hash`` column to ``users`` if it doesn't exist.

    Returns ``True`` if the column was added, ``False`` if it already existed.
    """
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    columns = [col["name"] for col in inspector.get_columns("users")]

    if "password_hash" in columns:
        return False

    with db_engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
        )
        conn.commit()
    return True


if __name__ == "__main__":
    added = migrate_add_password_hash()
    if added:
        print("Migración aplicada: columna 'password_hash' agregada a 'users'.")
    else:
        print("La columna 'password_hash' ya existe. No se requiere migración.")
