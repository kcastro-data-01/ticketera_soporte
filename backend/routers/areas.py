"""Áreas de IT: todos ven las activas (para elegir al crear un ticket); solo
el Administrador ve las inactivas, crea, renombra y desactiva."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import ItArea, User
from backend.routers.auth import ROLES_ADMIN, ROLES_TODOS, role_required
from backend.schemas import AreaCreate, AreaResponse, AreaUpdate
from backend.services import area_service
from backend.constants import UserRole

router = APIRouter(prefix="/api/areas", tags=["Áreas de IT"])


def _respuesta(area: ItArea, conteos: dict[int, int]) -> AreaResponse:
    return AreaResponse(id=area.id, name=area.name, is_active=area.is_active,
                        tecnicos=conteos.get(area.id, 0))


@router.get("", response_model=list[AreaResponse], summary="Listar áreas de IT")
def list_areas(
    todas: bool = Query(False, description="Incluir las desactivadas (solo Administrador)."),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> list[AreaResponse]:
    if todas and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo el Administrador ve las áreas desactivadas.")
    conteos = area_service.technician_counts(session)
    return [_respuesta(a, conteos) for a in area_service.list_areas(session, include_inactive=todas)]


@router.post("", response_model=AreaResponse, status_code=status.HTTP_201_CREATED,
             summary="Crear un área de IT")
def create_area(
    payload: AreaCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_ADMIN)),
) -> AreaResponse:
    try:
        area = area_service.create_area(session, payload)
    except area_service.AreaNameTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return _respuesta(area, {})


@router.patch("/{area_id}", response_model=AreaResponse,
              summary="Renombrar, desactivar o reactivar un área de IT")
def update_area(
    area_id: int,
    payload: AreaUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_ADMIN)),
) -> AreaResponse:
    try:
        area = area_service.update_area(session, area_id, payload)
    except area_service.AreaNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except area_service.AreaNameTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return _respuesta(area, area_service.technician_counts(session))
