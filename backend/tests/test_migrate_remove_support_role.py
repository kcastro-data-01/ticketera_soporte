"""Pruebas de la migración que pasa los usuarios ``Soporte`` a ``Técnico``."""

from sqlalchemy import create_engine, text

from backend.migrate_remove_support_role import migrate_remove_support_role


def test_support_users_become_technicians_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(30))"))
        conn.execute(
            text(
                "INSERT INTO users (id, role) VALUES "
                "(1, 'Soporte'), (2, 'Administrador'), (3, 'Soporte')"
            )
        )
        conn.commit()

    assert migrate_remove_support_role(engine) == 2
    assert migrate_remove_support_role(engine) == 0

    with engine.connect() as conn:
        roles = conn.execute(text("SELECT role FROM users ORDER BY id")).scalars().all()
    assert roles == ["Técnico", "Administrador", "Técnico"]
    engine.dispose()
