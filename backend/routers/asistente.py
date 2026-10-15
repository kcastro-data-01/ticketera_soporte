"""Asistente de IA: preguntas sobre la app, limitadas por el rol."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_TODOS, role_required
from backend.schemas import AsistenteRequest, AsistenteResponse
from backend.services import asistente_service
from backend.services.asistente_service import (
    AsistenteNoConfigurado,
    AsistenteNoDisponible,
    AsistenteOcupado,
)

router = APIRouter(prefix="/api", tags=["Asistente"])


def get_proveedor():
    """Proveedor de IA configurado (Qwen3 con Ollama por defecto)."""
    try:
        return asistente_service.crear_proveedor()
    except AsistenteNoConfigurado as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        )


@router.post(
    "/asistente",
    response_model=AsistenteResponse,
    summary="Preguntar al asistente de IA",
)
def preguntar(
    payload: AsistenteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
    proveedor=Depends(get_proveedor),
) -> AsistenteResponse:
    """Answer a question about the app with the data the user's role can see."""
    messages = [m.model_dump() for m in payload.messages]
    try:
        texto = asistente_service.responder(proveedor, session, current_user, messages)
    except AsistenteNoConfigurado as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except AsistenteOcupado:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="El asistente está recibiendo demasiadas consultas; intenta en un momento",
        )
    except AsistenteNoDisponible as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    return AsistenteResponse(respuesta=texto)
