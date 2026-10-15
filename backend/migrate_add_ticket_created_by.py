"""Idempotent migration: add ``created_by_id`` column to ``tickets`` table.

This script is safe to run multiple times. It checks whether the column
already exists before attempting to add it, so it works on both fresh
databases and existing SQLite files (local development and Docker volume).
Tickets created before the migration keep ``created_by_id`` NULL.
"""

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_add_ticket_created_by(target_engine=None) -> bool:
    """Add ``created_by_id`` column to ``tickets`` if it doesn't exist.

    Returns ``True`` if the column was added, ``False`` if it already existed.
    """
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    columns = [col["name"] for col in inspector.get_columns("tickets")]

    if "created_by_id" in columns:
        return False

    with db_engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE tickets ADD COLUMN created_by_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tickets_created_by_id "
                "ON tickets (created_by_id)"
            )
        )
        conn.commit()
    return True


if __name__ == "__main__":
    added = migrate_add_ticket_created_by()
    if added:
        print("Migración aplicada: columna 'created_by_id' agregada a 'tickets'.")
    else:
        print("La columna 'created_by_id' ya existe. No se requiere migración.")
