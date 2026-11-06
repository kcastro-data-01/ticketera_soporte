"""Pantalla «Departamentos»: resumen de tickets por departamento (en el
código, «áreas de IT»). Solo el Administrador (permiso «Ver departamentos»):
``403`` para los demás roles. Los números los calcula el servidor."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_DEPARTAMENTOS, role_required
from backend.schemas import DepartamentosResumen
from backend.services import area_service

router = APIRouter(prefix="/api/departamentos", tags=["Departamentos (áreas de IT)"])


@router.get("/resumen", response_model=DepartamentosResumen,
            summary="Tickets por departamento (solo Administrador)")
def resumen(
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_DEPARTAMENTOS)),
) -> dict:
    """Por cada departamento fijo y «Sin departamento»: total, abiertos
    (Nuevo + En proceso), cada estado y los Técnicos activos; además el total
    de abiertos y el departamento con más abiertos."""
    return area_service.resumen_departamentos(session)
