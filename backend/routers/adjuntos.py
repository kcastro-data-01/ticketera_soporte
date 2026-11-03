"""Adjuntos de un ticket ya creado: listar, subir, descargar y eliminar.

Los permisos son los de ver el ticket (el Solicitante, solo los suyos; un
ticket que no puede ver responde ``404``). Borrar: quien lo subió o el
Administrador. En Cerrado no se sube ni se borra (``409``).

Se sube **un archivo por llamada**, con el contenido tal cual en el cuerpo
(``application/octet-stream``) y el nombre en ``?nombre=``: así cada llamada
queda por debajo del límite de 4,5 MB de Vercel y no hace falta
``python-multipart``. No hay enlaces públicos: la descarga pasa por la API.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import Attachment, Ticket, User
from backend.routers.auth import ROLES_TODOS, role_required
from backend.schemas import AttachmentList, AttachmentResponse
from backend.services import adjuntos_service, ticket_service
from backend.services.adjuntos_service import (
    AdjuntoInvalidoError,
    AdjuntoSinPermisoError,
    AlmacenNoConfiguradoError,
    LimiteAdjuntosError,
)
from backend.services.ticket_service import TicketClosedError

router = APIRouter(prefix="/api/tickets", tags=["Adjuntos"])


def _ticket_visible(session: Session, ticket_id: int, user: User) -> Ticket:
    ticket = ticket_service.get_visible_ticket(session, ticket_id, user)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} no encontrado")
    return ticket


def _adjunto(session: Session, ticket_id: int, adjunto_id: int) -> Attachment:
    adjunto = adjuntos_service.obtener(session, ticket_id, adjunto_id)
    if adjunto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Adjunto no encontrado")
    return adjunto


def _respuesta(adjunto: Attachment, ticket: Ticket, user: User) -> AttachmentResponse:
    return AttachmentResponse(
        id=adjunto.id,
        ticket_id=adjunto.ticket_id,
        nombre=adjunto.filename,
        tipo=adjunto.content_type,
        tamano=adjunto.size,
        es_imagen=adjunto.content_type.startswith("image/"),
        subido_por=adjunto.uploaded_by,
        subido_por_id=adjunto.uploaded_by_id,
        creado=adjunto.created_at,
        puede_eliminar=adjuntos_service.puede_eliminar(adjunto, ticket, user),
        por_correo=adjunto.source == adjuntos_service.ORIGEN_CORREO,
    )


@router.get("/{ticket_id}/adjuntos", response_model=AttachmentList,
            summary="Adjuntos de un ticket")
def listar_adjuntos(
    ticket_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> AttachmentList:
    ticket = _ticket_visible(session, ticket_id, current_user)
    adjuntos = adjuntos_service.listar(session, ticket_id)
    return AttachmentList(
        adjuntos=[_respuesta(a, ticket, current_user) for a in adjuntos],
        puede_subir=not ticket_service.is_closed(ticket)
        and len(adjuntos) < adjuntos_service.MAX_POR_TICKET,
        cerrado=ticket_service.is_closed(ticket),
        max_archivos=adjuntos_service.MAX_POR_TICKET,
        max_bytes=adjuntos_service.MAX_BYTES,
    )


async def _leer_cuerpo(request: Request) -> bytes:
    """El cuerpo completo, cortando apenas pasa de 4 MB (``413``)."""
    demasiado = HTTPException(413,
                              detail="El archivo pesa más de 4 MB.")
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > adjuntos_service.MAX_BYTES:
        raise demasiado
    partes, total = [], 0
    async for parte in request.stream():
        total += len(parte)
        if total > adjuntos_service.MAX_BYTES:
            raise demasiado
        partes.append(parte)
    return b"".join(partes)


@router.post("/{ticket_id}/adjuntos", response_model=AttachmentResponse,
             status_code=status.HTTP_201_CREATED, summary="Subir un archivo al ticket")
async def subir_adjunto(
    ticket_id: int,
    request: Request,
    nombre: str = Query(..., min_length=1, max_length=400, description="Nombre del archivo"),
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> AttachmentResponse:
    """Un archivo (jpg, png, pdf, docx, xlsx o txt; hasta 4 MB) en el cuerpo."""
    contenido = await _leer_cuerpo(request)

    def guardar() -> AttachmentResponse:
        ticket = _ticket_visible(session, ticket_id, current_user)
        try:
            adjunto = adjuntos_service.subir(session, ticket, current_user, nombre, contenido)
        except TicketClosedError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
        except LimiteAdjuntosError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
        except AdjuntoInvalidoError as error:
            raise HTTPException(422, detail=str(error))
        except AlmacenNoConfiguradoError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
        return _respuesta(adjunto, ticket, current_user)

    return await run_in_threadpool(guardar)


@router.get("/{ticket_id}/adjuntos/{adjunto_id}/archivo", summary="Descargar un adjunto")
def descargar_adjunto(
    ticket_id: int,
    adjunto_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> Response:
    _ticket_visible(session, ticket_id, current_user)
    adjunto = _adjunto(session, ticket_id, adjunto_id)
    try:
        contenido = adjuntos_service.leer(adjunto)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El archivo ya no está disponible.")
    tipo = adjunto.content_type
    if tipo == "text/plain":
        tipo = "text/plain; charset=utf-8"
    return Response(
        content=contenido,
        media_type=tipo,
        headers={
            # Siempre como descarga y sin que el navegador adivine el tipo.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(adjunto.filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/{ticket_id}/adjuntos/{adjunto_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Eliminar un adjunto (quien lo subió o Administrador)")
def eliminar_adjunto(
    ticket_id: int,
    adjunto_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> Response:
    ticket = _ticket_visible(session, ticket_id, current_user)
    adjunto = _adjunto(session, ticket_id, adjunto_id)
    try:
        adjuntos_service.eliminar(session, ticket, adjunto, current_user)
    except TicketClosedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    except AdjuntoSinPermisoError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
