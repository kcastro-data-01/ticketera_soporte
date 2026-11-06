"""Áreas de IT: fijas (``backend.constants.IT_AREAS``). Solo se leen: no se
crean, renombran, desactivan ni borran desde la app; la migración
``backend.migrate_add_it_areas`` deja exactamente esas."""

from sqlalchemy import func, select

from backend.constants import CATEGORY_IT_AREA, IT_AREAS, UserRole
from backend.models import ItArea, User


class AreaNotFoundError(LookupError):
    def __init__(self, area_id: int):
        self.area_id = area_id
        super().__init__(f"Departamento {area_id} no encontrado")


class AreaInactiveError(ValueError):
    """Un área que no está entre las fijas activas (por si quedara una vieja)."""

    def __init__(self, area: ItArea):
        self.area = area
        super().__init__(f"El departamento «{area.name}» no está disponible.")


def _orden(area: ItArea) -> tuple[int, int]:
    return (IT_AREAS.index(area.name) if area.name in IT_AREAS else len(IT_AREAS), area.id)


def list_areas(session) -> list[ItArea]:
    """Las áreas fijas, en el orden de ``IT_AREAS``."""
    areas = session.scalars(select(ItArea).where(ItArea.is_active.is_(True))).all()
    return sorted(areas, key=_orden)


def technician_counts(session) -> dict[int, int]:
    """Técnicos activos por área (``{area_id: cantidad}``)."""
    filas = session.execute(
        select(User.area_id, func.count())
        .where(User.area_id.is_not(None), User.is_active.is_(True),
               User.role == UserRole.TECHNICIAN.value)
        .group_by(User.area_id)
    ).all()
    return {area_id: cantidad for area_id, cantidad in filas}


def get_area(session, area_id: int) -> ItArea | None:
    return session.get(ItArea, area_id)


def get_active_area(session, area_id: int) -> ItArea:
    """El área si existe y está activa; si no, ``AreaNotFoundError`` o
    ``AreaInactiveError``."""
    area = session.get(ItArea, area_id)
    if area is None:
        raise AreaNotFoundError(area_id)
    if not area.is_active:
        raise AreaInactiveError(area)
    return area


def area_for_category(session, category: str) -> ItArea | None:
    """Área de un ticket que no la trae, según su categoría (Hardware y
    Software → Soporte, Red → Redes e Infraestructura, Accesos →
    Ciberseguridad). ``None`` si esa área no existe en la base."""
    nombre = CATEGORY_IT_AREA.get(category)
    if nombre is None:
        return None
    return session.scalar(select(ItArea).where(ItArea.name == nombre, ItArea.is_active.is_(True)))
