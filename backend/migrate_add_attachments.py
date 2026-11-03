"""Migración idempotente: crea la tabla ``adjuntos`` si no existe.

Corre al arrancar (``init_db``) en SQLite (local, Docker) y en Postgres
(Neon). ``create_all`` ya la crea en una base nueva; esto la agrega a las
bases que existían antes de los adjuntos y no toca las demás tablas.
"""

from sqlalchemy import inspect

from backend.database import engine


def migrate_add_attachments(target_engine=None) -> bool:
    """Crea ``adjuntos`` (con sus índices). ``True`` si la creó."""
    from backend.models import Attachment

    db_engine = target_engine or engine
    if inspect(db_engine).has_table(Attachment.__tablename__):
        return False
    Attachment.__table__.create(bind=db_engine, checkfirst=True)
    return True


if __name__ == "__main__":
    if migrate_add_attachments():
        print("Migración aplicada: tabla 'adjuntos' creada.")
    else:
        print("La tabla 'adjuntos' ya existe. No se requiere migración.")
