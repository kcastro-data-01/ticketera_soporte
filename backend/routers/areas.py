"""Áreas de IT: fijas y de solo lectura. Todos los roles las listan (para
elegir al crear un ticket); nadie, ni el Administrador, las crea, renombra,
desactiva ni borra: como solo hay rutas GET, cualquier otro método responde
``405 Method Not Allowed``."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import ItArea, User
from backend.routers.auth import ROLES_TODOS, role_required
from backend.schemas import AreaResponse
from backend.services import area_service

router = APIRouter(prefix="/api/areas", tags=["Áreas de IT"])


def _respuesta(area: ItArea, conteos: dict[int, int]) -> AreaResponse:
    return AreaResponse(id=area.id, name=area.name, is_active=area.is_active,
                        tecnicos=conteos.get(area.id, 0))


@router.get("", response_model=list[AreaResponse], summary="Listar las áreas de IT (fijas)")
def list_areas(
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> list[AreaResponse]:
    conteos = area_service.technician_counts(session)
    return [_respuesta(a, conteos) for a in area_service.list_areas(session)]


@router.get("/{area_id}", response_model=AreaResponse, summary="Consultar un área de IT")
def get_area(
    area_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> AreaResponse:
    area = area_service.get_area(session, area_id)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Área {area_id} no encontrada")
    return _respuesta(area, area_service.technician_counts(session))
