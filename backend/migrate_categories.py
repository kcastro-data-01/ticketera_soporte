"""Idempotent migration: move tickets to the new official categories.

The category list changed from ``Incidente | Consulta | Solicitud |
Mantenimiento`` to ``Hardware | Software | Red | Accesos``. Two things must
happen on databases created before the change:

1. Existing rows keep their tickets but their ``category`` value must be
   mapped through :data:`backend.constants.LEGACY_CATEGORY_MAP` (the approved
   one-to-one correspondence).
2. SQLite cannot alter a ``CHECK`` constraint in place, so the ``tickets``
   table is rebuilt with the new constraint and the rows are copied over.

The script is safe to run multiple times: it rebuilds only when the table
still carries legacy values (or the old ``CHECK`` definition) and preserves
every column value verbatim, including ``created_at``/``updated_at``.
Comments and history rows are untouched (``foreign_keys`` is disabled for the
rebuild, otherwise the ``ON DELETE CASCADE`` clauses would wipe them).
"""

from sqlalchemy import inspect, text

from backend.constants import (
    LEGACY_CATEGORY_MAP,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
)
from backend.database import engine

_SCRATCH_TABLE = "tickets_migrated"

# Shape of the tickets table as created by the current models. The ``IN (...)``
# lists are generated from the constants so the constraint can never drift.
_TICKETS_DDL = f"""
CREATE TABLE {_SCRATCH_TABLE} (
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
	CONSTRAINT ck_tickets_category CHECK (category IN ({", ".join(f"'{value}'" for value in TICKET_CATEGORIES)})),
	CONSTRAINT ck_tickets_priority CHECK (priority IN ({", ".join(f"'{value}'" for value in TICKET_PRIORITIES)})),
	CONSTRAINT ck_tickets_state CHECK (state IN ({", ".join(f"'{value}'" for value in TICKET_STATES)})),
	FOREIGN KEY(assigned_to_id) REFERENCES users (id) ON DELETE SET NULL
)
"""

_CATEGORY_CASE = "CASE category " + " ".join(
    f"WHEN '{old}' THEN '{new}'" for old, new in LEGACY_CATEGORY_MAP.items()
) + " ELSE category END"


def _needs_migration(db_engine) -> tuple[bool, list[str]]:
    """Return ``(needed, legacy_values_in_rows)`` for the current database.

    The rebuild is required when the table definition still contains the old
    ``CHECK`` list or when any stored row uses a legacy category.
    """
    inspector = inspect(db_engine)
    if "tickets" not in inspector.get_table_names():
        # Fresh database: create_all already built it with the new CHECK.
        return False, []

    with db_engine.connect() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tickets'")
        ).scalar()
        rows = conn.execute(text("SELECT DISTINCT category FROM tickets")).fetchall()

    legacy_in_ddl = any(f"'{old}'" in (ddl or "") for old in LEGACY_CATEGORY_MAP)
    legacy_in_rows = sorted({value for (value,) in rows if value in LEGACY_CATEGORY_MAP})
    unknown = sorted(
        {
            value
            for (value,) in rows
            if value not in TICKET_CATEGORIES and value not in LEGACY_CATEGORY_MAP
        }
    )
    if unknown:
        raise ValueError(
            "No se puede migrar la tabla 'tickets': existen categorías desconocidas "
            f"{unknown}. Amplía LEGACY_CATEGORY_MAP antes de continuar; no se hizo "
            "ningún cambio."
        )
    return legacy_in_ddl or bool(legacy_in_rows), legacy_in_rows


def migrate_categories(target_engine=None) -> tuple[bool, list[str]]:
    """Rebuild ``tickets`` with the current categories and map legacy rows.

    Returns ``(applied, mapped_values)`` where ``applied`` tells whether the
    table was rebuilt and ``mapped_values`` lists the legacy categories that
    were present in the data. Nothing is written when no migration is needed.
    """
    # The rebuild drops and renames tables that comments/history reference.
    # ``foreign_keys`` must be off for that: with it on, the ON DELETE CASCADE
    # clauses would wipe the children. The SQLite driver wraps DML (not DDL) in
    # a transaction, so the PRAGMA is set on the raw DBAPI handle *before* the
    # transaction starts and restored afterwards, on the same connection.
    db_engine = target_engine or engine
    needed, legacy_in_rows = _needs_migration(db_engine)
    if not needed:
        return False, []

    with db_engine.connect() as conn:
        dbapi_connection = conn.connection.dbapi_connection
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")
        try:
            transaction = conn.begin()
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {_SCRATCH_TABLE}"))
                conn.execute(text(_TICKETS_DDL))
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {_SCRATCH_TABLE} (
                            id, title, description, category, priority, state,
                            assigned_to_id, created_at, updated_at
                        )
                        SELECT
                            id, title, description, {_CATEGORY_CASE}, priority, state,
                            assigned_to_id, created_at, updated_at
                        FROM tickets
                        """
                    )
                )
                copied = conn.execute(
                    text(f"SELECT COUNT(*) FROM {_SCRATCH_TABLE}")
                ).scalar()
                original = conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar()
                if copied != original:
                    raise RuntimeError(
                        f"La copia de 'tickets' quedó incompleta ({copied} de "
                        f"{original} filas); no se reemplaza la tabla original."
                    )
                conn.execute(text("DROP TABLE tickets"))
                conn.execute(text(f"ALTER TABLE {_SCRATCH_TABLE} RENAME TO tickets"))
                conn.execute(
                    text("CREATE INDEX ix_tickets_assigned_to_id ON tickets (assigned_to_id)")
                )
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise
        finally:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
    return True, legacy_in_rows


if __name__ == "__main__":
    applied, mapped = migrate_categories()
    if applied:
        print(f"Migración aplicada: categorías antiguas migradas {mapped or '[]'}.")
    else:
        print("La tabla 'tickets' ya usa las categorías actuales. No se requiere migración.")
