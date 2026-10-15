"""Asistente de IA: preguntas sobre la app, limitadas por el rol."""

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_TODOS, role_required
from backend.schemas import AsistenteRequest, AsistenteResponse
from backend.services import asistente_service

router = APIRouter(prefix="/api", tags=["Asistente"])


def get_claude_client():
    """Claude client, or ``None`` when ``ANTHROPIC_API_KEY`` is not set."""
    if not asistente_service.configured():
        return None
    return anthropic.Anthropic()


@router.post(
    "/asistente",
    response_model=AsistenteResponse,
    summary="Preguntar al asistente de IA",
)
def preguntar(
    payload: AsistenteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
    client=Depends(get_claude_client),
) -> AsistenteResponse:
    """Answer a question about the app with the data the user's role can see."""
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El asistente no está configurado: falta la clave ANTHROPIC_API_KEY en el servidor",
        )
    messages = [m.model_dump() for m in payload.messages]
    try:
        texto = asistente_service.responder(client, session, current_user, messages)
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La clave ANTHROPIC_API_KEY del servidor no es válida",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="El asistente está recibiendo demasiadas consultas; intenta en un momento",
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El asistente no está disponible en este momento; intenta más tarde",
        )
    return AsistenteResponse(respuesta=texto)
