"""Configuration endpoint: read-only exposure of the system constants."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.constants import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
    USER_ROLES,
)

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
    )
