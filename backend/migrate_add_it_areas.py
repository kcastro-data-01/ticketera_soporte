"""Migración idempotente de las áreas de IT (fijas).

Corre en cada arranque (``init_db``), en SQLite (local, Docker) y en Postgres
(Neon):

* crea ``it_areas`` si no existe y agrega ``users.area_id`` y
  ``tickets.area_id`` si faltan (lo que ya había queda «Sin área»);
* deja **exactamente** las áreas fijas de ``backend.constants.IT_AREAS``
  (Soporte, Redes e Infraestructura, Ciberseguridad, Programación):

  - el mismo nombre sin tildes o con otras mayúsculas («Programacion») es
    esa área fija y se corrige;
  - los nombres de antes (``LEGACY_IT_AREA_NAMES``) pasan al área fija que
    corresponde: «Soporte técnico» → «Soporte»; «Redes» e «Infraestructura»
    → «Redes e Infraestructura» (si había varias filas para la misma área,
    sus tickets y técnicos pasan a una sola y las otras se borran);
  - cualquier otra área se borra y sus tickets y técnicos quedan «Sin área»;
  - las que falten se crean, todas activas.

En una base nueva (Neon) solo crea las 4. Cada cambio queda en el log; si
ya está al día, no hace nada.
"""

import logging
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from backend.constants import IT_AREAS, LEGACY_IT_AREA_NAMES
from backend.database import engine

logger = logging.getLogger(__name__)


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


def _normal(nombre: str) -> str:
    """Sin tildes, mayúsculas ni espacios de más («Programacion» = «Programación»)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", nombre)
                         if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def _destino(nombre: str) -> str | None:
    """Área fija que le toca a un nombre guardado (sin distinguir tildes ni
    mayúsculas), o ``None`` si no es ninguna."""
    limpio = _normal(nombre)
    for fija in IT_AREAS:
        if _normal(fija) == limpio:
            return fija
    for viejo, fija in LEGACY_IT_AREA_NAMES.items():
        if _normal(viejo) == limpio:
            return fija
    return None


def fix_it_areas(target_engine=None) -> list[str]:
    """Deja exactamente las áreas fijas. Devuelve los cambios hechos (vacío
    si ya estaba al día)."""
    db_engine = target_engine or engine
    if not inspect(db_engine).has_table("it_areas"):
        return []
    cambios: list[str] = []
    with db_engine.begin() as conn:
        filas = conn.execute(text("SELECT id, name, is_active FROM it_areas ORDER BY id")).all()
        por_fija: dict[str, list] = {}
        sobrantes = []
        for fila in filas:
            fija = _destino(fila.name)
            if fija is None:
                sobrantes.append(fila)
            else:
                por_fija.setdefault(fija, []).append(fila)

        def mover(desde: int, hacia: int | None) -> None:
            for tabla in ("tickets", "users"):
                conn.execute(text(f"UPDATE {tabla} SET area_id = :hacia WHERE area_id = :desde"),
                             {"hacia": hacia, "desde": desde})

        # Primero se borran las que sobran: así un nombre fijo queda libre.
        for fila in sobrantes:
            mover(fila.id, None)
            conn.execute(text("DELETE FROM it_areas WHERE id = :id"), {"id": fila.id})
            cambios.append(f"borrada «{fila.name}» (sus tickets y técnicos quedan «Sin área»)")

        for fija, grupo in por_fija.items():
            # Se queda la que ya se llama así; si no, la de menor id.
            elegida = next((f for f in grupo if f.name == fija), grupo[0])
            for otra in grupo:
                if otra.id == elegida.id:
                    continue
                mover(otra.id, elegida.id)
                conn.execute(text("DELETE FROM it_areas WHERE id = :id"), {"id": otra.id})
                cambios.append(f"«{otra.name}» unida a «{fija}»")
            if elegida.name != fija:
                conn.execute(text("UPDATE it_areas SET name = :n WHERE id = :id"),
                             {"n": fija, "id": elegida.id})
                cambios.append(f"«{elegida.name}» pasa a «{fija}»")
            if not elegida.is_active:
                conn.execute(text("UPDATE it_areas SET is_active = :a WHERE id = :id"),
                             {"a": True, "id": elegida.id})
                cambios.append(f"«{fija}» reactivada")

        ahora = datetime.now(timezone.utc)
        for fija in IT_AREAS:
            if fija not in por_fija:
                conn.execute(text(
                    "INSERT INTO it_areas (name, is_active, created_at) VALUES (:n, :a, :c)"),
                    {"n": fija, "a": True, "c": ahora})
                cambios.append(f"creada «{fija}»")
    for cambio in cambios:
        logger.warning("Áreas de IT: %s", cambio)
    return cambios


def migrate_it_areas(target_engine=None) -> None:
    """Todo lo anterior, en orden (lo llama ``init_db``)."""
    migrate_add_it_areas_table(target_engine)
    migrate_add_area_columns(target_engine)
    fix_it_areas(target_engine)


if __name__ == "__main__":
    migrate_it_areas()
    print("Áreas de IT al día.")
