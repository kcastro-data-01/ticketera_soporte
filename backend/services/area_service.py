"""Áreas de IT: fijas (``backend.constants.IT_AREAS``). Solo se leen: no se
crean, renombran, desactivan ni borran desde la app; la migración
``backend.migrate_add_it_areas`` deja exactamente esas."""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

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


# Tickets abiertos que trae cada departamento (el resto, en la lista filtrada).
MAX_TICKETS_ABIERTOS = 10


def resumen_departamentos(session) -> dict:
    """Pantalla «Departamentos» (solo Administrador): por cada departamento
    fijo y «Sin departamento», cuántos tickets hay en total, abiertos (Nuevo
    + En proceso) y en cada estado, y sus Técnicos activos. Arriba, el total
    de abiertos y el departamento con más abiertos (``None`` si ninguno
    tiene; empate: el primero en el orden de ``IT_AREAS``).

    Para el detalle de cada departamento: qué atiende (``atiende``), cada
    Técnico con sus abiertos y sus resueltos de este mes (primer paso a
    «Resuelto» desde el día 1 del mes en Costa Rica) y hasta
    ``MAX_TICKETS_ABIERTOS`` tickets abiertos, de mayor a menor prioridad y,
    con la misma prioridad, el más viejo primero."""
    from backend.constants import IT_AREA_SCOPE, TICKET_PRIORITIES, TICKET_STATES, TicketState
    from backend.models import Ticket
    from backend.services import metricas_service

    abiertos_estados = (TicketState.NEW.value, TicketState.IN_PROGRESS.value)
    conteos: dict[int | None, dict[str, int]] = {}
    for area_id, estado, cantidad in session.execute(
        select(Ticket.area_id, Ticket.state, func.count()).group_by(Ticket.area_id, Ticket.state)
    ).all():
        conteos.setdefault(area_id, {})[estado] = cantidad

    # Abiertos y resueltos este mes de cada persona, dentro de cada departamento.
    abiertos_persona: dict[tuple[int | None, int | None], int] = {
        (area_id, persona): cantidad for area_id, persona, cantidad in session.execute(
            select(Ticket.area_id, Ticket.assigned_to_id, func.count())
            .where(Ticket.state.in_(abiertos_estados))
            .group_by(Ticket.area_id, Ticket.assigned_to_id)
        ).all()
    }
    hoy = metricas_service.hoy()
    inicio_mes, fin_mes = metricas_service.limites_utc(hoy.replace(day=1), hoy)
    primer_resuelto = metricas_service.primer_paso_a(TicketState.RESOLVED.value)
    resueltos_persona: dict[tuple[int | None, int | None], int] = {
        (area_id, persona): cantidad for area_id, persona, cantidad in session.execute(
            select(Ticket.area_id, Ticket.assigned_to_id, func.count())
            .join(primer_resuelto, primer_resuelto.c.ticket_id == Ticket.id)
            .where(primer_resuelto.c.en >= inicio_mes, primer_resuelto.c.en < fin_mes)
            .group_by(Ticket.area_id, Ticket.assigned_to_id)
        ).all()
    }

    tecnicos: dict[int, list[dict]] = {}
    for usuario in session.scalars(
        select(User).where(User.area_id.is_not(None), User.is_active.is_(True),
                           User.role == UserRole.TECHNICIAN.value).order_by(func.lower(User.name))
    ).all():
        clave = (usuario.area_id, usuario.id)
        tecnicos.setdefault(usuario.area_id, []).append({
            "id": usuario.id, "name": usuario.name,
            "abiertos": abiertos_persona.get(clave, 0),
            "resueltos_mes": resueltos_persona.get(clave, 0),
        })

    # Tickets abiertos: prioridad (Crítica primero) y después antigüedad.
    peso = {p: i for i, p in enumerate(reversed(TICKET_PRIORITIES))}
    abiertos_lista: dict[int | None, list] = {}
    for t in sorted(
        session.scalars(select(Ticket).options(selectinload(Ticket.assignee))
                        .where(Ticket.state.in_(abiertos_estados))).all(),
        key=lambda t: (peso.get(t.priority, len(peso)), metricas_service._como_utc(t.created_at), t.id),
    ):
        abiertos_lista.setdefault(t.area_id, []).append(t)

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
            "atiende": IT_AREA_SCOPE.get(nombre, "tickets que todavía no tienen departamento"
                                         if area_id is None else ""),
            "tickets_abiertos": [
                {"id": t.id, "title": t.title, "state": t.state, "priority": t.priority,
                 "assigned_to_name": t.assignee.name if t.assignee is not None else None,
                 "created_at": t.created_at}
                for t in abiertos_lista.get(area_id, [])[:MAX_TICKETS_ABIERTOS]
            ],
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
