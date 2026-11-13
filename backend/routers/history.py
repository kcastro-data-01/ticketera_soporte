"""Global history endpoint (read-only, across all tickets)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_EQUIPO, role_required
from backend.schemas import HistorialResumen, HistoryResponse
from backend.services import historial_service

router = APIRouter(prefix="/api", tags=["Historial"])

# Todos los roles menos el Solicitante pueden leer el historial global.
HISTORY_ROLES = ROLES_EQUIPO
MAX_POR_PAGINA = 200

Periodo = Literal["hoy", "7", "30"]
PERSONA_DOC = "«todas» (por defecto), «sistema» (cambios automáticos) o el id del usuario."
BUSCAR_DOC = "Número (con o sin #) o parte del título del ticket."


def _persona(persona: str | None) -> str | int:
    try:
        return historial_service.normalizar_persona(persona)
    except historial_service.PersonaInvalida as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/history",
    response_model=list[HistoryResponse],
    summary="Historial global de todos los tickets",
)
def get_global_history(
    persona: str | None = Query(None, description=PERSONA_DOC),
    periodo: Periodo | None = Query(None, description="Hoy o los últimos 7 o 30 días (Costa Rica). Sin valor: todo."),
    buscar: str | None = Query(None, max_length=200, description=BUSCAR_DOC),
    limit: int | None = Query(None, ge=1, le=MAX_POR_PAGINA, description="Cuántos registros devolver."),
    offset: int = Query(0, ge=0, description="Cuántos registros saltar (para «Ver más»)."),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(HISTORY_ROLES)),
) -> list[HistoryResponse]:
    """Return the audit entries recorded across all tickets, newest first.

    Requires authentication (401 without token). Read-only: it exposes the
    existing ``history`` rows and never creates them. Optional model fields
    (``field``, ``old_value``, ``new_value``, ``author``) are returned as
    ``null`` when unavailable. Without query parameters it returns every
    entry; ``persona``, ``periodo`` and ``buscar`` filter and ``limit`` /
    ``offset`` page the result.
    """
    entries = historial_service.listar_cambios(
        session,
        persona=_persona(persona),
        periodo=periodo,
        buscar=buscar,
        limite=limit,
        desplazamiento=offset,
    )
    return [HistoryResponse.model_validate(entry) for entry in entries]


@router.get(
    "/history/resumen",
    response_model=HistorialResumen,
    summary="Personas que hicieron cambios y totales del período",
)
def get_history_summary(
    periodo: Periodo = Query(historial_service.PERIODO_POR_DEFECTO),
    persona: str | None = Query(None, description=PERSONA_DOC),
    buscar: str | None = Query(None, max_length=200, description=BUSCAR_DOC),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(HISTORY_ROLES)),
) -> HistorialResumen:
    """Personas (con «Sistema») y cantidad de cambios de cada una en el
    período, más las cajas del filtro: cambios, tickets tocados, comentarios
    y cambios de estado."""
    return HistorialResumen.model_validate(
        historial_service.resumen(session, periodo=periodo, persona=_persona(persona), buscar=buscar)
    )
