"""Áreas de IT: listado, creación, renombre y activación (solo Administrador)."""

from sqlalchemy import func, select

from backend.constants import UserRole
from backend.models import ItArea, User
from backend.schemas import AreaCreate, AreaUpdate


class AreaNameTakenError(ValueError):
    """Ya existe un área con ese nombre (sin distinguir mayúsculas)."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Ya existe un área llamada «{name}».")


class AreaNotFoundError(LookupError):
    def __init__(self, area_id: int):
        self.area_id = area_id
        super().__init__(f"Área {area_id} no encontrada")


class AreaInactiveError(ValueError):
    def __init__(self, area: ItArea):
        self.area = area
        super().__init__(f"El área «{area.name}» está desactivada.")


def list_areas(session, include_inactive: bool = False) -> list[ItArea]:
    """Áreas ordenadas por nombre; solo las activas salvo ``include_inactive``."""
    statement = select(ItArea).order_by(func.lower(ItArea.name), ItArea.id)
    if not include_inactive:
        statement = statement.where(ItArea.is_active.is_(True))
    return list(session.scalars(statement).all())


def technician_counts(session) -> dict[int, int]:
    """Técnicos activos por área (``{area_id: cantidad}``)."""
    filas = session.execute(
        select(User.area_id, func.count())
        .where(User.area_id.is_not(None), User.is_active.is_(True),
               User.role == UserRole.TECHNICIAN.value)
        .group_by(User.area_id)
    ).all()
    return {area_id: cantidad for area_id, cantidad in filas}


def has_active_areas(session) -> bool:
    return session.scalar(select(ItArea.id).where(ItArea.is_active.is_(True)).limit(1)) is not None


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


def _nombre_libre(session, name: str, excepto: int | None = None) -> None:
    statement = select(ItArea.id).where(func.lower(ItArea.name) == name.lower())
    if excepto is not None:
        statement = statement.where(ItArea.id != excepto)
    if session.scalar(statement) is not None:
        raise AreaNameTakenError(name)


def create_area(session, payload: AreaCreate) -> ItArea:
    _nombre_libre(session, payload.name)
    area = ItArea(name=payload.name, is_active=True)
    session.add(area)
    session.commit()
    session.refresh(area)
    return area


def update_area(session, area_id: int, payload: AreaUpdate) -> ItArea:
    """Renombra, desactiva o reactiva. Desactivar no toca a los técnicos ni a
    los tickets que ya la tienen."""
    area = session.get(ItArea, area_id)
    if area is None:
        raise AreaNotFoundError(area_id)
    if payload.name is not None:
        _nombre_libre(session, payload.name, excepto=area_id)
        area.name = payload.name
    if payload.is_active is not None:
        area.is_active = payload.is_active
    session.commit()
    session.refresh(area)
    return area
