"""Asistente de IA: preguntas sobre la app, limitadas por el rol."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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
        texto, fuente = asistente_service.responder_completo(
            proveedor, session, current_user, messages, payload.ticket_id
        )
    except AsistenteNoConfigurado as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except AsistenteOcupado:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=asistente_service.MENSAJE_IA_LIMITE,
        )
    except AsistenteNoDisponible as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    return AsistenteResponse(respuesta=texto, fuente=fuente)


@router.post(
    "/asistente/stream",
    summary="Preguntar al asistente de IA (respuesta por partes)",
    response_class=StreamingResponse,
)
def preguntar_stream(
    payload: AsistenteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
    proveedor=Depends(get_proveedor),
) -> StreamingResponse:
    """Same as ``POST /api/asistente`` but answers as NDJSON events while the
    model writes: ``{"t": "…"}`` chunks, then ``{"fin": true, "fuente": …}``
    or ``{"error": "…"}``."""
    messages = [m.model_dump() for m in payload.messages]
    # Se calcula aquí (con la sesión abierta) y se envía a medida que llega.
    eventos = asistente_service.responder_stream(
        proveedor, session, current_user, messages, payload.ticket_id
    )

    def ndjson():
        for evento in eventos:
            yield json.dumps(evento, ensure_ascii=False) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")
