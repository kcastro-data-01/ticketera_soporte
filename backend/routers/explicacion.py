"""«Explicar con IA»: qué le pasa a un ticket, causas probables y qué revisar primero."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import Ticket, User
from backend.routers.asistente import get_proveedor
from backend.routers.auth import ROLES_EQUIPO, role_required
from backend.schemas import ExplicacionResponse
from backend.services import asistente_service, explicacion_service
from backend.services.asistente_service import AsistenteNoDisponible
from backend.services.explicacion_service import ExplicacionInvalida

router = APIRouter(prefix="/api/tickets", tags=["Explicar con IA"])


def _ticket(session: Session, ticket_id: int) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Ticket {ticket_id} no encontrado")
    # Datos frescos (comentarios incluidos): la huella decide si la
    # explicación guardada sigue vigente.
    session.expire(ticket)
    return ticket


@router.get(
    "/{ticket_id}/explicacion",
    response_model=ExplicacionResponse,
    summary="Ver la última explicación de la IA (sin generar una nueva)",
)
def ver_explicacion(
    ticket_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_EQUIPO)),
) -> dict:
    """Last saved explanation (``explicacion: null`` if none) and the
    server-computed clarity. Never calls the AI."""
    datos = explicacion_service.obtener(session, _ticket(session, ticket_id))
    return {**datos, "ia_disponible": asistente_service.ia_activa()}


@router.post(
    "/{ticket_id}/explicacion",
    response_model=ExplicacionResponse,
    summary="Explicar un ticket con IA (Técnico y Administrador)",
)
def explicar_ticket(
    ticket_id: int,
    regenerar: bool = Query(False, description="Pedir una nueva aunque la guardada siga vigente"),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_EQUIPO)),
    proveedor=Depends(get_proveedor),
) -> dict:
    """Reuse the saved explanation while the ticket has not changed;
    otherwise (or with ``regenerar=true``) ask the AI and save it. With the
    AI turned off (``ASISTENTE_PROVEEDOR=ninguno``, Vercel) → 503."""
    if not asistente_service.ia_activa():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="La IA no está disponible en esta versión")
    ticket = _ticket(session, ticket_id)
    try:
        return explicacion_service.explicar(session, proveedor, ticket, current_user, regenerar)
    except AsistenteNoDisponible as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    except ExplicacionInvalida as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
