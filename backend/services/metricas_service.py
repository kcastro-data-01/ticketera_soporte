"""Métricas de la mesa de soporte (Supervisor y Administrador). Sin IA.

* **Hoy** (sin importar el rango): tickets abiertos (Nuevo + En proceso) y en
  proceso, y los abiertos de cada persona asignada.
* **En el rango**: tickets creados (por estado y por categoría actuales, por
  día y por origen: correo o web) y tickets resueltos, con el tiempo
  promedio desde que se crearon hasta su primer paso a «Resuelto».

Los días son de Costa Rica (UTC−6 fijo, sin horario de verano) y el rango
incluye los dos extremos.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select

from backend.constants import TICKET_CATEGORIES, TICKET_STATES, TicketState
from backend.models import History, ProcessedEmail, Ticket, User
from backend.services.ticket_service import OPEN_STATES

COSTA_RICA = timezone(timedelta(hours=-6))
DIAS_POR_DEFECTO = 30
MAX_DIAS = 366


class RangoInvalido(ValueError):
    """``desde`` es posterior a ``hasta`` o el rango es demasiado largo."""


def hoy() -> date:
    return datetime.now(COSTA_RICA).date()


def rango(desde: date | None, hasta: date | None) -> tuple[date, date]:
    """Completa y valida el rango: por defecto, los últimos 30 días con hoy."""
    hasta = hasta or hoy()
    desde = desde or hasta - timedelta(days=DIAS_POR_DEFECTO - 1)
    if desde > hasta:
        raise RangoInvalido("La fecha «desde» no puede ser posterior a «hasta».")
    if (hasta - desde).days + 1 > MAX_DIAS:
        raise RangoInvalido(f"El rango puede tener como máximo {MAX_DIAS} días.")
    return desde, hasta


def limites_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[inicio, fin) en UTC sin zona, como lo guarda la base."""
    inicio = datetime.combine(desde, time.min, COSTA_RICA)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, COSTA_RICA)
    return (inicio.astimezone(timezone.utc).replace(tzinfo=None),
            fin.astimezone(timezone.utc).replace(tzinfo=None))


def primer_paso_a(estado: str):
    """Subconsulta ``(ticket_id, en)``: cuándo pasó cada ticket por primera
    vez a ``estado`` (un ticket que vuelve a pasar no cuenta dos veces)."""
    return (
        select(History.ticket_id, func.min(History.created_at).label("en"))
        .where(History.field == "state", History.new_value == estado)
        .group_by(History.ticket_id)
        .subquery()
    )


def _dia_local(instante: datetime) -> date:
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(COSTA_RICA).date()


def _como_utc(instante: datetime) -> datetime:
    return instante if instante.tzinfo is not None else instante.replace(tzinfo=timezone.utc)


def calcular(session, desde: date, hasta: date) -> dict:
    inicio, fin = limites_utc(desde, hasta)
    en_rango = (Ticket.created_at >= inicio, Ticket.created_at < fin)

    # Hoy: la cola actual.
    por_estado_hoy = dict(session.execute(
        select(Ticket.state, func.count()).group_by(Ticket.state)
    ).all())
    abiertos = sum(por_estado_hoy.get(e, 0) for e in OPEN_STATES)

    # Creados en el rango: estado, categoría, día y origen.
    creados = session.execute(
        select(Ticket.id, Ticket.state, Ticket.category, Ticket.created_at).where(*en_rango)
    ).all()
    por_correo = set(session.scalars(
        select(ProcessedEmail.ticket_id).where(
            ProcessedEmail.result == "ticket",
            ProcessedEmail.ticket_id.in_([c.id for c in creados]),
        )
    ).all()) if creados else set()
    estados = {e: 0 for e in TICKET_STATES}
    categorias = {c: 0 for c in TICKET_CATEGORIES}
    dias = {desde + timedelta(days=i): 0 for i in range((hasta - desde).days + 1)}
    for creado in creados:
        estados[creado.state] = estados.get(creado.state, 0) + 1
        categorias[creado.category] = categorias.get(creado.category, 0) + 1
        dia = _dia_local(creado.created_at)
        if dia in dias:
            dias[dia] += 1

    # Resueltos en el rango: primer paso a «Resuelto» de cada ticket.
    primer_resuelto = primer_paso_a(TicketState.RESOLVED.value)
    resueltos = session.execute(
        select(Ticket.id, Ticket.created_at, Ticket.assigned_to_id, primer_resuelto.c.en)
        .join(primer_resuelto, primer_resuelto.c.ticket_id == Ticket.id)
        .where(primer_resuelto.c.en >= inicio, primer_resuelto.c.en < fin)
    ).all()
    horas = [
        (_como_utc(r.en) - _como_utc(r.created_at)).total_seconds() / 3600
        for r in resueltos
    ]
    promedio = round(sum(horas) / len(horas), 1) if horas else None

    # Por persona asignada: abiertos hoy y resueltos en el rango.
    abiertos_por_persona = dict(session.execute(
        select(Ticket.assigned_to_id, func.count())
        .where(Ticket.state.in_(OPEN_STATES))
        .group_by(Ticket.assigned_to_id)
    ).all())
    resueltos_por_persona: dict[int | None, int] = {}
    for r in resueltos:
        resueltos_por_persona[r.assigned_to_id] = resueltos_por_persona.get(r.assigned_to_id, 0) + 1
    ids = {i for i in (*abiertos_por_persona, *resueltos_por_persona) if i is not None}
    personas = session.scalars(select(User).where(User.id.in_(ids))).all() if ids else []
    por_persona = sorted(
        (
            {
                "id": u.id, "nombre": u.name, "rol": u.role, "activo": u.is_active,
                "abiertos": abiertos_por_persona.get(u.id, 0),
                "resueltos": resueltos_por_persona.get(u.id, 0),
            }
            for u in personas
        ),
        key=lambda p: (-p["abiertos"], -p["resueltos"], p["nombre"].lower()),
    )

    return {
        "desde": desde,
        "hasta": hasta,
        "tarjetas": {
            "abiertos": abiertos,
            "en_proceso": por_estado_hoy.get(TicketState.IN_PROGRESS.value, 0),
            "resueltos_periodo": len(resueltos),
            "tiempo_promedio_horas": promedio,
            "creados_periodo": len(creados),
            "por_correo": len(por_correo),
            "por_web": len(creados) - len(por_correo),
        },
        "por_estado": [{"nombre": n, "total": t} for n, t in estados.items()],
        "por_categoria": [{"nombre": n, "total": t} for n, t in categorias.items()],
        "por_persona": por_persona,
        "sin_asignar_abiertos": abiertos_por_persona.get(None, 0),
        "por_dia": [{"fecha": d, "total": t} for d, t in dias.items()],
    }
