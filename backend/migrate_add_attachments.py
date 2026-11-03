"""Migración idempotente de la tabla ``adjuntos``.

Corre al arrancar (``init_db``) en SQLite (local, Docker) y en Postgres
(Neon):

* crea ``adjuntos`` si no existe (bases de antes de los adjuntos);
* le agrega ``source`` (``app`` o ``correo``) si es de la parte 1, sin esa
  columna: los adjuntos que ya había quedan como ``app``.
"""

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_add_attachments(target_engine=None) -> bool:
    """Crea ``adjuntos`` (con sus índices). ``True`` si la creó."""
    from backend.models import Attachment

    db_engine = target_engine or engine
    if inspect(db_engine).has_table(Attachment.__tablename__):
        return False
    Attachment.__table__.create(bind=db_engine, checkfirst=True)
    return True


def migrate_add_attachment_source(target_engine=None) -> bool:
    """Agrega ``adjuntos.source`` si falta. ``True`` si la agregó."""
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("adjuntos"):
        return False
    if "source" in {col["name"] for col in inspector.get_columns("adjuntos")}:
        return False
    with db_engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE adjuntos ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'app'"))
    return True


if __name__ == "__main__":
    if migrate_add_attachments():
        print("Migración aplicada: tabla 'adjuntos' creada.")
    elif migrate_add_attachment_source():
        print("Migración aplicada: columna 'source' agregada a 'adjuntos'.")
    else:
        print("La tabla 'adjuntos' ya está al día. No se requiere migración.")
