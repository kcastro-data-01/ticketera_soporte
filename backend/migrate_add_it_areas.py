"""Migración idempotente de las áreas de IT.

Corre al arrancar (``init_db``) en SQLite (local, Docker) y en Postgres
(Neon):

* crea ``it_areas`` si no existe;
* agrega ``users.area_id`` y ``tickets.area_id`` si faltan: los técnicos y
  tickets que ya había quedan «Sin área» (``NULL``) hasta que el
  Administrador los asigne;
* carga **una sola vez** las áreas de ejemplo (``EXAMPLE_IT_AREAS``) y deja
  la marca ``areas_it_ejemplo`` en ``schema_migrations``: si después se
  renombran o desactivan, no vuelven a aparecer.

Los tickets viejos asignados a un Solicitante no se tocan.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from backend.constants import EXAMPLE_IT_AREAS
from backend.database import engine

logger = logging.getLogger(__name__)

MARCA_EJEMPLO = "areas_it_ejemplo"


def migrate_add_it_areas_table(target_engine=None) -> bool:
    """Crea ``it_areas``. ``True`` si la creó."""
    from backend.models import ItArea

    db_engine = target_engine or engine
    if inspect(db_engine).has_table(ItArea.__tablename__):
        return False
    ItArea.__table__.create(bind=db_engine, checkfirst=True)
    return True


def _agregar_area_id(db_engine, tabla: str) -> bool:
    inspector = inspect(db_engine)
    if not inspector.has_table(tabla):
        return False
    if "area_id" in {col["name"] for col in inspector.get_columns(tabla)}:
        return False
    with db_engine.begin() as conn:
        conn.execute(text(
            f"ALTER TABLE {tabla} ADD COLUMN area_id INTEGER "
            "REFERENCES it_areas(id) ON DELETE SET NULL"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{tabla}_area_id ON {tabla} (area_id)"))
    return True


def migrate_add_area_columns(target_engine=None) -> bool:
    """Agrega ``area_id`` a ``users`` y ``tickets``. ``True`` si agregó alguna."""
    db_engine = target_engine or engine
    usuarios = _agregar_area_id(db_engine, "users")
    tickets = _agregar_area_id(db_engine, "tickets")
    return usuarios or tickets


def seed_example_areas(target_engine=None) -> bool:
    """Carga las áreas de ejemplo una sola vez. ``True`` si las cargó.

    Si la tabla ya tiene áreas (creadas a mano antes de la marca) solo se
    deja la marca, sin agregar las de ejemplo."""
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not (inspector.has_table("it_areas") and inspector.has_table("schema_migrations")):
        return False
    ahora = datetime.now(timezone.utc)
    with db_engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM schema_migrations WHERE name = :n"),
                        {"n": MARCA_EJEMPLO}).first():
            return False
        cargadas = False
        if conn.execute(text("SELECT COUNT(*) FROM it_areas")).scalar() == 0:
            for nombre in EXAMPLE_IT_AREAS:
                conn.execute(text(
                    "INSERT INTO it_areas (name, is_active, created_at) VALUES (:n, :a, :c)"),
                    {"n": nombre, "a": True, "c": ahora})
            cargadas = True
            logger.info("Áreas de IT de ejemplo cargadas: %s", ", ".join(EXAMPLE_IT_AREAS))
        conn.execute(text("INSERT INTO schema_migrations (name, applied_at) VALUES (:n, :c)"),
                     {"n": MARCA_EJEMPLO, "c": ahora})
    return cargadas


def migrate_it_areas(target_engine=None) -> None:
    """Todo lo anterior, en orden (lo llama ``init_db``)."""
    migrate_add_it_areas_table(target_engine)
    migrate_add_area_columns(target_engine)
    seed_example_areas(target_engine)


if __name__ == "__main__":
    migrate_it_areas()
    print("Áreas de IT al día.")
