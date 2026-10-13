"""Global history endpoint (read-only, across all tickets)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import (
    ROLES_SOLICITANTE,
    ROLES_SUPERVISOR,
    ROLES_SOPORTE,
    ROLES_TECNICO,
    role_required,
)
from backend.schemas import HistoryResponse
from backend.services import ticket_service

router = APIRouter(prefix="/api", tags=["Historial"])

# Cualquier usuario autenticado puede leer el historial global.
HISTORY_ROLES = (
    ROLES_SOLICITANTE | ROLES_SOPORTE | ROLES_SUPERVISOR | ROLES_TECNICO
)


@router.get(
    "/history",
    response_model=list[HistoryResponse],
    summary="Historial global de todos los tickets",
)
def get_global_history(
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(HISTORY_ROLES)),
) -> list[HistoryResponse]:
    """Return the audit entries recorded across all tickets, newest first.

    Requires authentication (401 without token). Read-only: it exposes the
    existing ``history`` rows and never creates them. Optional model fields
    (``field``, ``old_value``, ``new_value``, ``author``) are returned as
    ``null`` when unavailable.
    """
    entries = ticket_service.get_global_history(session)
    return [HistoryResponse.model_validate(entry) for entry in entries]
