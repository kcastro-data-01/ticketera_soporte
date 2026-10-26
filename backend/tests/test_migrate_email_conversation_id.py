"""Pruebas de la migración que añade ``processed_emails.conversation_id``."""

from sqlalchemy import create_engine, inspect, text

from backend.database import init_db
from backend.migrate_add_email_conversation_id import migrate_add_email_conversation_id


def test_adds_the_column_and_index_to_an_old_database_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE processed_emails (id INTEGER PRIMARY KEY, message_id VARCHAR(500), "
            "sender VARCHAR(255), result VARCHAR(20), ticket_id INTEGER, created_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO processed_emails (id, message_id, result) VALUES (1, '<a@x>', 'ticket')"))
        conn.commit()

    assert migrate_add_email_conversation_id(engine) is True
    assert migrate_add_email_conversation_id(engine) is False

    inspector = inspect(engine)
    assert "conversation_id" in {c["name"] for c in inspector.get_columns("processed_emails")}
    assert "ix_processed_emails_conversation_id" in {i["name"] for i in inspector.get_indexes("processed_emails")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT conversation_id FROM processed_emails")).scalar_one() is None
    engine.dispose()


def test_new_database_already_has_the_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nueva.db'}")
    init_db(engine)
    assert "conversation_id" in {c["name"] for c in inspect(engine).get_columns("processed_emails")}
    assert migrate_add_email_conversation_id(engine) is False
    engine.dispose()


def test_without_the_table_does_nothing(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vacia.db'}")
    assert migrate_add_email_conversation_id(engine) is False
    engine.dispose()
