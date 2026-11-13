"""Historial global agrupado por persona (pantalla «Historial»).

* **Personas**: quién hizo cambios (Técnicos, Administradores, Solicitantes)
  y «Sistema» para los automáticos (registros sin ``author_id``: cierre
  automático, tickets creados desde correo antiguos, registros previos a la
  auditoría con usuario). Cada una con la cantidad de cambios del período.
* **Cambios**: los registros filtrados por persona, período y búsqueda (por
  número o título de ticket), del más nuevo al más viejo, por páginas.
* **Cajas**: totales del filtro (cambios, tickets tocados, comentarios y
  cambios de estado).

Los períodos son días de Costa Rica: «hoy» empieza a la medianoche de hoy;
«7» y «30» incluyen hoy y los 6 o 29 días anteriores.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.orm import selectinload

from backend.models import History, Ticket, User
from backend.services import metricas_service

PERIODOS = {"hoy": 1, "7": 7, "30": 30}
PERIODO_POR_DEFECTO = "7"
SISTEMA = "sistema"
TODAS = "todas"
NOMBRE_SISTEMA = "Sistema"
ROL_SISTEMA = "Cambios automáticos"

# Acciones que cambian el estado del ticket (manual o automáticamente).
ACCIONES_ESTADO = ("Cambio de estado", "state_changed", "Cierre automático", "Reabierto por respuesta")
ACCION_COMENTARIO = "commented"


class PersonaInvalida(ValueError):
    """``persona`` no es «todas», «sistema» ni un número de usuario."""


def desde_periodo(periodo: str) -> datetime:
    """Inicio del período en UTC sin zona (como lo guarda la base)."""
    dias = PERIODOS[periodo]
    hoy = metricas_service.hoy()
    inicio, _ = metricas_service.limites_utc(hoy - timedelta(days=dias - 1), hoy)
    return inicio


def normalizar_persona(persona: str | None) -> str | int:
    """``None``/«todas» → «todas»; «sistema» → «sistema»; «12» → 12."""
    valor = (persona or "").strip().lower()
    if valor in ("", TODAS):
        return TODAS
    if valor == SISTEMA:
        return SISTEMA
    if valor.isdigit():
        return int(valor)
    raise PersonaInvalida("La persona debe ser «todas», «sistema» o un número de usuario.")


def _condiciones(persona: str | int, desde: datetime | None, buscar: str | None) -> list:
    condiciones = []
    if persona == SISTEMA:
        condiciones.append(History.author_id.is_(None))
    elif persona != TODAS:
        condiciones.append(History.author_id == persona)
    if desde is not None:
        condiciones.append(History.created_at >= desde)
    texto = (buscar or "").strip()
    if texto:
        numero = texto.lstrip("#").strip()
        patron = f"%{texto}%"
        if numero.isdigit():
            condiciones.append(or_(History.ticket_id == int(numero), Ticket.title.ilike(patron)))
        else:
            condiciones.append(Ticket.title.ilike(patron))
    return condiciones


def _con_ticket(consulta, buscar: str | None):
    """La búsqueda por título necesita la tabla de tickets."""
    return consulta.join(Ticket, Ticket.id == History.ticket_id) if (buscar or "").strip() else consulta


def listar_cambios(
    session,
    *,
    persona: str | int = TODAS,
    periodo: str | None = None,
    buscar: str | None = None,
    limite: int | None = None,
    desplazamiento: int = 0,
) -> list[History]:
    """Registros del filtro, del más nuevo al más viejo (``id`` desempata)."""
    desde = desde_periodo(periodo) if periodo else None
    consulta = _con_ticket(select(History), buscar).where(*_condiciones(persona, desde, buscar))
    consulta = (
        consulta.options(selectinload(History.ticket))
        .order_by(History.created_at.desc(), History.id.desc())
        .offset(desplazamiento)
    )
    if limite is not None:
        consulta = consulta.limit(limite)
    return list(session.scalars(consulta).all())


def _nombre_autor(fila_autor: str | None) -> str:
    autor = (fila_autor or "").strip()
    return autor if autor and autor != "Anónimo" else NOMBRE_SISTEMA


def personas(session, periodo: str) -> list[dict]:
    """Todas las personas que hicieron cambios alguna vez, con los del período.

    Ordenadas por cambios del período (más primero) y luego por nombre. Las
    que no tienen cambios en el período vienen con ``cambios = 0`` (la
    pantalla las oculta salvo que estén elegidas).
    """
    desde = desde_periodo(periodo)
    en_periodo = func.sum(_uno_si(History.created_at >= desde))
    filas = session.execute(
        select(History.author_id, func.count(History.id), en_periodo, func.max(History.author))
        .group_by(History.author_id)
    ).all()

    ids = [fila[0] for fila in filas if fila[0] is not None]
    usuarios = {}
    if ids:
        usuarios = {
            u.id: u
            for u in session.scalars(
                select(User).where(User.id.in_(ids)).options(selectinload(User.area))
            ).all()
        }

    resultado = []
    for author_id, _total, cambios, autor in filas:
        cambios = int(cambios or 0)
        if author_id is None:
            resultado.append({
                "clave": SISTEMA, "user_id": None, "nombre": NOMBRE_SISTEMA,
                "rol": ROL_SISTEMA, "departamento": None, "cambios": cambios,
            })
            continue
        usuario = usuarios.get(author_id)
        resultado.append({
            "clave": str(author_id),
            "user_id": author_id,
            "nombre": usuario.name if usuario else _nombre_autor(autor),
            "rol": usuario.role if usuario else None,
            "departamento": usuario.area.name if usuario and usuario.area else None,
            "cambios": cambios,
        })
    resultado.sort(key=lambda p: (-p["cambios"], p["nombre"].lower()))
    return resultado


def _uno_si(condicion):
    """Para contar con ``sum``: 1 si se cumple, 0 si no."""
    return case((condicion, 1), else_=0)


def cajas(session, *, persona: str | int, periodo: str, buscar: str | None) -> dict:
    """Totales del filtro: cambios, tickets tocados, comentarios y de estado."""
    desde = desde_periodo(periodo)
    consulta = _con_ticket(
        select(
            func.count(History.id),
            func.count(distinct(History.ticket_id)),
            func.sum(_uno_si(History.action == ACCION_COMENTARIO)),
            func.sum(_uno_si(History.action.in_(ACCIONES_ESTADO))),
        ),
        buscar,
    ).where(*_condiciones(persona, desde, buscar))
    cambios, tickets, comentarios, estados = session.execute(consulta).one()
    return {
        "cambios": int(cambios or 0),
        "tickets": int(tickets or 0),
        "comentarios": int(comentarios or 0),
        "cambios_estado": int(estados or 0),
    }


def resumen(session, *, periodo: str, persona: str | int = TODAS, buscar: str | None = None) -> dict:
    lista = personas(session, periodo)
    return {
        "periodo": periodo,
        "desde": desde_periodo(periodo).replace(tzinfo=timezone.utc),
        "total": sum(p["cambios"] for p in lista),
        "personas": lista,
        "cajas": cajas(session, persona=persona, periodo=periodo, buscar=buscar),
    }
