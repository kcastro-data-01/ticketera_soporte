"""One-time data migration: renumber the tickets that came after a jump.

Antes la secuencia de Postgres nunca retrocedía: con #1–#5 y los #6–#15
creados y borrados, el siguiente fue el #16. Ahora el próximo es el mayor id
+ 1 (``ticket_service.reservar_numero``); esta migración corrige lo que ya
quedó: los tickets por encima del primer bloque seguido pasan a continuarlo
(#16 → #6), con sus comentarios, historial, explicación y correos
procesados.

Corre **una sola vez** (marca ``renumerar_tickets`` en
``schema_migrations``): después, borrar un ticket nunca renumera los demás.
Todo va en una transacción; en Postgres, con el mismo candado que la
creación de tickets. Cada cambio queda en el log.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from backend.database import Base, engine, es_sqlite

logger = logging.getLogger(__name__)

NOMBRE = "renumerar_tickets"
# El mismo candado que ticket_service.reservar_numero (sin importar el
# servicio aquí: init_db corre antes que todo).
CANDADO_NUMERACION = 742_001


def nuevos_numeros(ids: list[int]) -> list[tuple[int, int]]:
    """``(viejo, nuevo)`` de los tickets por encima del primer bloque
    seguido (el que empieza en el menor id), en orden: [1..5, 16, 18] →
    [(16, 6), (18, 7)]."""
    ids = sorted(ids)
    if not ids:
        return []
    fin = ids[0]
    for numero in ids[1:]:
        if numero != fin + 1:
            break
        fin = numero
    return [(viejo, fin + 1 + i) for i, viejo in enumerate(n for n in ids if n > fin)]


def _referencias() -> list[tuple[str, str]]:
    """``(tabla, columna)`` de cada clave foránea a ``tickets.id``."""
    from backend import models  # noqa: F401  (registra las tablas)

    return [(tabla.name, fk.parent.name) for tabla in Base.metadata.sorted_tables
            for fk in tabla.foreign_keys if fk.column.table.name == "tickets"]


def migrate_renumber_tickets(target_engine=None) -> list[tuple[int, int]]:
    """Renumera una sola vez; devuelve los cambios ``(viejo, nuevo)``."""
    from backend.models import Ticket

    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not (inspector.has_table("tickets") and inspector.has_table("schema_migrations")):
        return []
    postgres = not es_sqlite(db_engine)
    columnas = ", ".join(c.name for c in Ticket.__table__.columns if c.name != "id")
    referencias = _referencias()

    with db_engine.begin() as conn:
        if postgres:
            conn.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": CANDADO_NUMERACION})
        if conn.execute(text("SELECT 1 FROM schema_migrations WHERE name = :n"), {"n": NOMBRE}).first():
            return []
        cambios = nuevos_numeros(list(conn.scalars(text("SELECT id FROM tickets"))))
        for viejo, nuevo in cambios:
            # Copia con el número nuevo, mueve lo que lo referencia y borra el
            # viejo (las claves foráneas no tienen ON UPDATE CASCADE).
            conn.execute(text(f"INSERT INTO tickets (id, {columnas}) "
                              f"SELECT :nuevo, {columnas} FROM tickets WHERE id = :viejo"),
                         {"nuevo": nuevo, "viejo": viejo})
            for tabla, columna in referencias:
                conn.execute(text(f"UPDATE {tabla} SET {columna} = :nuevo WHERE {columna} = :viejo"),
                             {"nuevo": nuevo, "viejo": viejo})
            conn.execute(text("DELETE FROM tickets WHERE id = :viejo"), {"viejo": viejo})
        if postgres:
            conn.execute(text("SELECT setval(pg_get_serial_sequence('tickets', 'id'), "
                              "COALESCE(MAX(id), 0) + 1, false) FROM tickets"))
        conn.execute(text("INSERT INTO schema_migrations (name, applied_at) VALUES (:n, :ahora)"),
                     {"n": NOMBRE, "ahora": datetime.now(timezone.utc)})

    for viejo, nuevo in cambios:
        logger.warning("Numeración de tickets: el ticket #%s ahora es el #%s (con sus comentarios, "
                       "historial, explicación y correos)", viejo, nuevo)
    if not cambios:
        logger.warning("Numeración de tickets: ya estaba seguida, no se renumeró nada")
    return cambios


if __name__ == "__main__":
    print(migrate_renumber_tickets() or "Nada que renumerar (o ya se aplicó).")
