"""Idempotent migration: add ``conversation_id`` to ``processed_emails``.

Safe to run multiple times: it checks whether the column already exists
before adding it, so it works on fresh databases and on existing SQLite
files (local development and Docker volume).

The column keeps the Graph ``conversationId`` of each processed mail, the
fallback to find the ticket of a thread when a reply has no
In-Reply-To/References. It is nullable: mails processed before keep working.
"""

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_add_email_conversation_id(target_engine=None) -> bool:
    """Add ``conversation_id`` (and its index) to ``processed_emails`` if it
    doesn't exist. Returns ``True`` if the column was added."""
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("processed_emails"):
        return False
    columns = [col["name"] for col in inspector.get_columns("processed_emails")]

    if "conversation_id" in columns:
        return False

    with db_engine.connect() as conn:
        conn.execute(text("ALTER TABLE processed_emails ADD COLUMN conversation_id VARCHAR(500)"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_processed_emails_conversation_id "
            "ON processed_emails (conversation_id)"
        ))
        conn.commit()
    return True


if __name__ == "__main__":
    added = migrate_add_email_conversation_id()
    if added:
        print("Migración aplicada: columna 'conversation_id' agregada a 'processed_emails'.")
    else:
        print("La columna 'conversation_id' ya existe. No se requiere migración.")
