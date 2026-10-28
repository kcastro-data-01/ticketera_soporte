"""Configuration endpoint: read-only exposure of the system constants."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.constants import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
    USER_ROLES,
)
from backend.services.asistente_service import ia_activa

router = APIRouter(prefix="/api", tags=["Configuración"])


class ConfigResponse(BaseModel):
    """System constants exposed for the configuration page.

    Read-only: the values come from ``backend.constants`` and are never
    persisted or edited through this endpoint.
    """

    categories: list[str]
    states: list[str]
    priorities: list[str]
    roles: list[str]
    # False con la IA apagada (Vercel): se oculta «Explicar con IA».
    ia_disponible: bool


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Constantes del sistema",
)
def get_config() -> ConfigResponse:
    """Return the fixed domain constants used by the ticket system.

    Read-only: the values are the Spanish strings defined in
    ``backend.constants`` and are never modified by this endpoint.
    """
    return ConfigResponse(
        categories=list(TICKET_CATEGORIES),
        states=list(TICKET_STATES),
        priorities=list(TICKET_PRIORITIES),
        roles=list(USER_ROLES),
        ia_disponible=ia_activa(),
    )
