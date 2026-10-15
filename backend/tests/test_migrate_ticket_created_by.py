"""Pruebas de la migración que añade ``tickets.created_by_id``."""

from sqlalchemy import create_engine, inspect, text

from backend.migrate_add_ticket_created_by import migrate_add_ticket_created_by


def test_adds_the_column_to_an_old_database_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text("CREATE TABLE tickets (id INTEGER PRIMARY KEY, title VARCHAR(200))")
        )
        conn.execute(text("INSERT INTO tickets (id, title) VALUES (1, 'Antiguo')"))
        conn.commit()

    assert migrate_add_ticket_created_by(engine) is True
    assert migrate_add_ticket_created_by(engine) is False

    columns = {col["name"] for col in inspect(engine).get_columns("tickets")}
    assert "created_by_id" in columns
    with engine.connect() as conn:
        value = conn.execute(text("SELECT created_by_id FROM tickets")).scalar_one()
    assert value is None
    engine.dispose()
