"""Métricas de la mesa de soporte (solo Administrador). Sin IA."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_ADMIN, role_required
from backend.schemas import MetricasResponse
from backend.services import metricas_service

router = APIRouter(prefix="/api", tags=["Métricas"])


@router.get(
    "/metricas",
    response_model=MetricasResponse,
    summary="Métricas de tickets (solo Administrador)",
)
def ver_metricas(
    desde: date | None = Query(None, description="Primer día (YYYY-MM-DD, hora de Costa Rica)"),
    hasta: date | None = Query(None, description="Último día, incluido (por defecto, hoy)"),
    area: int | None = Query(None, ge=1, description="Solo los tickets de ese departamento"),
    sin_area: bool = Query(False, description="Solo los tickets «Sin departamento»"),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_ADMIN)),
) -> dict:
    """Counts computed by the server. ``abiertos`` and ``en_proceso`` are the
    queue right now; everything else uses the range (last 30 days by default).
    ``area`` / ``sin_area`` restrict every number to one IT area."""
    try:
        desde, hasta = metricas_service.rango(desde, hasta)
    except metricas_service.RangoInvalido as error:
        raise HTTPException(status_code=422, detail=str(error))
    if area is not None and sin_area:
        raise HTTPException(status_code=422, detail="Elija un departamento o «Sin departamento», no los dos.")
    return metricas_service.calcular(session, desde, hasta, area_id=area, sin_area=sin_area)
