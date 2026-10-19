"""Métricas de la mesa de soporte (Supervisor y Administrador). Sin IA."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_GESTION, role_required
from backend.schemas import MetricasResponse
from backend.services import metricas_service

router = APIRouter(prefix="/api", tags=["Métricas"])


@router.get(
    "/metricas",
    response_model=MetricasResponse,
    summary="Métricas de tickets (Supervisor y Administrador)",
)
def ver_metricas(
    desde: date | None = Query(None, description="Primer día (YYYY-MM-DD, hora de Costa Rica)"),
    hasta: date | None = Query(None, description="Último día, incluido (por defecto, hoy)"),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_GESTION)),
) -> dict:
    """Counts computed by the server. ``abiertos`` and ``en_proceso`` are the
    queue right now; everything else uses the range (last 30 days by default)."""
    try:
        desde, hasta = metricas_service.rango(desde, hasta)
    except metricas_service.RangoInvalido as error:
        raise HTTPException(status_code=422, detail=str(error))
    return metricas_service.calcular(session, desde, hasta)
