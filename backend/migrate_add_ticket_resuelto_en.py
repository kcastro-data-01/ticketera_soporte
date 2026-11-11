"""Migración idempotente: agrega ``resuelto_en`` a ``tickets`` (cierre
automático) y les pone «ahora» a los tickets que ya están en Resuelto.

Así el contador de los tickets resueltos antes de esta versión empieza
cuando se publica (el primer arranque con esta migración) y no desde cuando
se resolvieron: no se cierran todos de golpe. Se puede correr varias veces:
solo toca los que están en Resuelto y todavía no tienen fecha.
"""

from sqlalchemy import inspect, text, update

from backend.constants import TicketState
from backend.database import engine


def migrate_add_ticket_resuelto_en(target_engine=None) -> bool:
    """Agrega la columna si falta y completa los Resuelto sin fecha. Devuelve
    ``True`` si agregó la columna."""
    from backend.models import Ticket, utc_now

    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("tickets"):
        return False
    columnas = [col["name"] for col in inspector.get_columns("tickets")]
    agregada = "resuelto_en" not in columnas
    with db_engine.connect() as conn:
        if agregada:
            tipo = "TIMESTAMP WITH TIME ZONE" if db_engine.dialect.name == "postgresql" else "DATETIME"
            conn.execute(text(f"ALTER TABLE tickets ADD COLUMN resuelto_en {tipo}"))
        conn.execute(
            update(Ticket.__table__)
            .where(Ticket.__table__.c.state == TicketState.RESOLVED.value,
                   Ticket.__table__.c.resuelto_en.is_(None))
            # Sin tocar updated_at (onupdate): la migración no es un cambio del ticket.
            .values(resuelto_en=utc_now(), updated_at=Ticket.__table__.c.updated_at)
        )
        conn.commit()
    return agregada


if __name__ == "__main__":
    if migrate_add_ticket_resuelto_en():
        print("Migración aplicada: columna 'resuelto_en' agregada a 'tickets'.")
    else:
        print("La columna 'resuelto_en' ya existe. No se requiere migración.")
