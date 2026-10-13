"""Tests for the category migration (``backend.migrate_categories``).

The fixtures build a database with the *old* schema: a ``tickets`` table whose
``CHECK`` constraint only accepts the legacy categories
(``Incidente | Consulta | Solicitud | Mantenimiento``), plus the tables that
reference it (``comments``, ``history``). The migration must map every legacy
value through ``LEGACY_CATEGORY_MAP``, rebuild the constraint and leave the
rest of the data untouched.
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.constants import LEGACY_CATEGORY_MAP, TICKET_CATEGORIES
from backend.database import Base, enable_sqlite_foreign_keys, init_db
from backend.migrate_categories import migrate_categories
from backend.models import Comment, History

_LEGACY_CATEGORIES = tuple(LEGACY_CATEGORY_MAP)

# Mirrors of the schema as created by the models before the category change.
_LEGACY_TICKETS_DDL = """
CREATE TABLE tickets (
	id INTEGER NOT NULL,
	title VARCHAR(200) NOT NULL,
	description TEXT NOT NULL,
	category VARCHAR(30) NOT NULL,
	priority VARCHAR(20) NOT NULL,
	state VARCHAR(20) NOT NULL,
	assigned_to_id INTEGER,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_tickets_title_length CHECK (length(trim(title)) >= 3 AND length(title) <= 200),
	CONSTRAINT ck_tickets_description_not_empty CHECK (length(trim(description)) >= 1),
	CONSTRAINT ck_tickets_category CHECK (category IN ('Incidente', 'Consulta', 'Solicitud', 'Mantenimiento')),
	CONSTRAINT ck_tickets_priority CHECK (priority IN ('Baja', 'Media', 'Alta', 'Crítica')),
	CONSTRAINT ck_tickets_state CHECK (state IN ('Nuevo', 'En proceso', 'Resuelto', 'Cerrado')),
	FOREIGN KEY(assigned_to_id) REFERENCES users (id) ON DELETE SET NULL
)
"""


@pytest.fixture
def legacy_engine(tmp_path):
    """Engine whose database still has the pre-change schema and data."""
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'legacy.db'}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(test_engine)
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    role VARCHAR(30) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    password_hash VARCHAR(255),
                    PRIMARY KEY (id),
                    UNIQUE (email)
                )
                """
            )
        )
        conn.execute(text(_LEGACY_TICKETS_DDL))
        conn.execute(
            text("CREATE INDEX ix_tickets_assigned_to_id ON tickets (assigned_to_id)")
        )
        Comment.__table__.create(bind=conn)
        History.__table__.create(bind=conn)
        conn.execute(
            text(
                "INSERT INTO users (id, name, email, role, is_active) "
                "VALUES (1, 'Ana', 'ana@test.local', 'Soporte', 1)"
            )
        )
        conn.exec_driver_sql(
            "INSERT INTO tickets (id, title, description, category, priority, "
            "state, assigned_to_id, created_at, updated_at) VALUES (?, ?, ?, ?, "
            "?, ?, ?, ?, ?)",
            (1, "Impresora atascada", "No saca papel.", "Incidente", "Alta",
             "Nuevo", 1, "2026-01-01 10:00:00", "2026-01-01 10:00:00"),
        )
        conn.exec_driver_sql(
            "INSERT INTO comments (ticket_id, author, content, created_at) "
            "VALUES (1, 'Ana', 'En revisión.', '2026-01-01 11:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO history (ticket_id, action, field, old_value, "
            "new_value, author, created_at) VALUES "
            "(1, 'state_changed', 'state', 'Nuevo', 'En proceso', 'Ana', "
            "'2026-01-01 12:00:00')"
        )
    yield test_engine
    test_engine.dispose()


def insert_legacy_ticket(conn, ticket_id: int, category: str, **overrides) -> None:
    """Insert one ticket with the legacy schema; ``overrides`` tweaks columns."""
    row = {
        "id": ticket_id,
        "title": f"Ticket {ticket_id}",
        "description": "Descripción de prueba.",
        "category": category,
        "priority": "Media",
        "state": "Nuevo",
        "assigned_to_id": None,
        "created_at": "2026-02-01 09:00:00",
        "updated_at": "2026-02-01 09:00:00",
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.exec_driver_sql(
        f"INSERT INTO tickets ({columns}) VALUES ({placeholders})", tuple(row.values())
    )


def table_ddl(engine, table_name: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table_name},
        ).scalar()


def test_maps_every_legacy_category_one_to_one(legacy_engine):
    with legacy_engine.begin() as conn:
        for ticket_id, category in enumerate(_LEGACY_CATEGORIES, start=2):
            insert_legacy_ticket(conn, ticket_id, category)

    applied, mapped = migrate_categories(legacy_engine)

    assert applied is True
    assert mapped == sorted(_LEGACY_CATEGORIES)
    with legacy_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, category FROM tickets ORDER BY id")
        ).fetchall()
    assert [(1, "Hardware")] + [
        (ticket_id, LEGACY_CATEGORY_MAP[category])
        for ticket_id, category in enumerate(_LEGACY_CATEGORIES, start=2)
    ] == rows


def test_rebuilds_the_check_constraint(legacy_engine):
    applied, _ = migrate_categories(legacy_engine)

    assert applied is True
    ddl = table_ddl(legacy_engine, "tickets")
    for value in TICKET_CATEGORIES:
        assert f"'{value}'" in ddl
    for legacy in _LEGACY_CATEGORIES:
        assert f"'{legacy}'" not in ddl

    # New values are accepted and legacy ones are rejected from now on.
    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tickets (title, description, category, priority, "
                "state, created_at, updated_at) VALUES ('Nuevo ticket', 'Ok', "
                "'Hardware', 'Media', 'Nuevo', '2026-03-01 09:00:00', "
                "'2026-03-01 09:00:00')"
            )
        )
        with pytest.raises(IntegrityError) as excinfo:
            conn.execute(
                text(
                    "INSERT INTO tickets (title, description, category, priority, "
                    "state, created_at, updated_at) VALUES ('Viejo ticket', 'No', "
                    "'Incidente', 'Media', 'Nuevo', '2026-03-01 09:00:00', "
                    "'2026-03-01 09:00:00')"
                )
            )
    assert "CHECK constraint failed" in str(excinfo.value)


def test_preserves_every_other_column_and_row(legacy_engine):
    with legacy_engine.begin() as conn:
        insert_legacy_ticket(
            conn,
            2,
            "Consulta",
            title="Ticket asignado",
            priority="Crítica",
            state="En proceso",
            assigned_to_id=1,
            created_at="2026-02-02 08:30:00",
            updated_at="2026-02-03 18:45:00",
        )

    migrate_categories(legacy_engine)

    with legacy_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, title, description, category, priority, state, "
                "assigned_to_id, created_at, updated_at FROM tickets ORDER BY id"
            )
        ).fetchall()
    assert rows == [
        (1, "Impresora atascada", "No saca papel.", "Hardware", "Alta", "Nuevo",
         1, "2026-01-01 10:00:00", "2026-01-01 10:00:00"),
        (2, "Ticket asignado", "Descripción de prueba.", "Software", "Crítica",
         "En proceso", 1, "2026-02-02 08:30:00", "2026-02-03 18:45:00"),
    ]


def test_keeps_comments_and_history_and_their_foreign_keys(legacy_engine):
    applied, _ = migrate_categories(legacy_engine)

    assert applied is True
    with legacy_engine.connect() as conn:
        comments = conn.execute(
            text("SELECT ticket_id, author, content, created_at FROM comments")
        ).fetchall()
        history = conn.execute(
            text(
                "SELECT ticket_id, action, field, old_value, new_value, author, "
                "created_at FROM history"
            )
        ).fetchall()
        index_names = {
            row["name"] for row in inspect(legacy_engine).get_indexes("tickets")
        }
    assert comments == [(1, "Ana", "En revisión.", "2026-01-01 11:00:00")]
    assert history == [
        (1, "state_changed", "state", "Nuevo", "En proceso", "Ana",
         "2026-01-01 12:00:00")
    ]
    assert "ix_tickets_assigned_to_id" in index_names

    # Foreign key enforcement is active again after the rebuild.
    with pytest.raises(IntegrityError) as excinfo:
        with legacy_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO comments (ticket_id, author, content, created_at) "
                    "VALUES (999, 'Ana', 'Huérfano.', '2026-01-01 11:00:00')"
                )
            )
    assert "FOREIGN KEY constraint failed" in str(excinfo.value)


def test_is_idempotent(legacy_engine):
    first_applied, _ = migrate_categories(legacy_engine)
    second_applied, second_mapped = migrate_categories(legacy_engine)

    assert first_applied is True
    assert second_applied is False
    assert second_mapped == []
    with legacy_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar() == 1


def test_fresh_database_needs_no_migration(tmp_path):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'fresh.db'}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(test_engine)
    Base.metadata.create_all(bind=test_engine)

    applied, mapped = migrate_categories(test_engine)

    assert applied is False
    assert mapped == []
    test_engine.dispose()


def test_unknown_category_aborts_without_changes(tmp_path):
    # Simulates a database where an out-of-list value reached the data (e.g.
    # inserted before the constraint existed): same legacy schema minus the
    # category CHECK, so the row can be planted for the test.
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'unknown.db'}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(test_engine)
    ddl = _LEGACY_TICKETS_DDL.replace(
        "CONSTRAINT ck_tickets_category CHECK (category IN "
        "('Incidente', 'Consulta', 'Solicitud', 'Mantenimiento')),",
        "",
    )
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    role VARCHAR(30) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    password_hash VARCHAR(255),
                    PRIMARY KEY (id),
                    UNIQUE (email)
                )
                """
            )
        )
        conn.execute(text(ddl))
        insert_legacy_ticket(conn, 1, "Incidente")
        insert_legacy_ticket(conn, 2, "Otra categoría")

    ddl_before = table_ddl(test_engine, "tickets")
    with pytest.raises(ValueError) as excinfo:
        migrate_categories(test_engine)

    assert "Otra categoría" in str(excinfo.value)
    assert table_ddl(test_engine, "tickets") == ddl_before
    with test_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, category FROM tickets ORDER BY id")
        ).fetchall()
    assert rows == [(1, "Incidente"), (2, "Otra categoría")]
    test_engine.dispose()


def test_init_db_applies_the_migration(legacy_engine):
    init_db(legacy_engine)

    with legacy_engine.connect() as conn:
        category = conn.execute(
            text("SELECT category FROM tickets WHERE id = 1")
        ).scalar()
    assert category == "Hardware"
