"""Comment endpoints (Task 9: creation; Task 20.2: listing, RF5)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.schemas import CommentCreate, CommentResponse
from backend.services import ticket_service
from backend.services.ticket_service import TicketNotFoundError

router = APIRouter(prefix="/api/tickets", tags=["Comentarios"])


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un comentario a un ticket",
)
def create_comment(
    ticket_id: int,
    payload: CommentCreate,
    session: Session = Depends(get_session),
) -> CommentResponse:
    """Create a comment on an existing ticket (RF5)."""
    try:
        comment = ticket_service.create_comment(session, ticket_id, payload)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return CommentResponse.model_validate(comment)


@router.get(
    "/{ticket_id}/comments",
    response_model=list[CommentResponse],
    summary="Comentarios de un ticket",
)
def list_comments(
    ticket_id: int,
    session: Session = Depends(get_session),
) -> list[CommentResponse]:
    """Return the comments stored for a ticket, oldest first (RF5).

    Read-only: it exposes the existing ``comments`` rows and never creates
    them. A missing ticket is answered with ``404``; an existing ticket
    without comments returns an empty list.
    """
    comments = ticket_service.get_ticket_comments(session, ticket_id)
    if comments is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return [CommentResponse.model_validate(comment) for comment in comments]
