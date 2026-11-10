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
    Software → Soporte IT, Red → Redes e Infraestructura, Accesos →
    Ciberseguridad). ``None`` si esa área no existe en la base."""
    nombre = CATEGORY_IT_AREA.get(category)
    if nombre is None:
        return None
    return session.scalar(select(ItArea).where(ItArea.name == nombre, ItArea.is_active.is_(True)))


def resumen_departamentos(session) -> dict:
    """Pantalla «Departamentos» (solo Administrador): por cada departamento
    fijo y «Sin departamento», cuántos tickets hay en total, abiertos (Nuevo
    + En proceso) y en cada estado, y sus Técnicos activos. Arriba, el total
    de abiertos y el departamento con más abiertos (``None`` si ninguno
    tiene; empate: el primero en el orden de ``IT_AREAS``)."""
    from backend.constants import TICKET_STATES, TicketState
    from backend.models import Ticket

    abiertos_estados = (TicketState.NEW.value, TicketState.IN_PROGRESS.value)
    conteos: dict[int | None, dict[str, int]] = {}
    for area_id, estado, cantidad in session.execute(
        select(Ticket.area_id, Ticket.state, func.count()).group_by(Ticket.area_id, Ticket.state)
    ).all():
        conteos.setdefault(area_id, {})[estado] = cantidad

    tecnicos: dict[int, list[dict]] = {}
    for usuario in session.scalars(
        select(User).where(User.area_id.is_not(None), User.is_active.is_(True),
                           User.role == UserRole.TECHNICIAN.value).order_by(func.lower(User.name))
    ).all():
        tecnicos.setdefault(usuario.area_id, []).append({"id": usuario.id, "name": usuario.name})

    def fila(area_id: int | None, nombre: str) -> dict:
        por_estado = {estado: conteos.get(area_id, {}).get(estado, 0) for estado in TICKET_STATES}
        lista = tecnicos.get(area_id, []) if area_id is not None else []
        return {
            "area_id": area_id,
            "nombre": nombre,
            "total": sum(por_estado.values()),
            "abiertos": sum(por_estado[e] for e in abiertos_estados),
            "por_estado": por_estado,
            "tecnicos": lista,
        }

    from backend.constants import NO_AREA_LABEL

    filas = [fila(area.id, area.name) for area in list_areas(session)]
    filas.append(fila(None, NO_AREA_LABEL))
    con_abiertos = [f for f in filas if f["area_id"] is not None and f["abiertos"] > 0]
    mayor = max(con_abiertos, key=lambda f: f["abiertos"], default=None)
    return {
        "total_abiertos": sum(f["abiertos"] for f in filas),
        "mas_abiertos": ({"area_id": mayor["area_id"], "nombre": mayor["nombre"],
                          "abiertos": mayor["abiertos"]} if mayor else None),
        "departamentos": filas,
    }
