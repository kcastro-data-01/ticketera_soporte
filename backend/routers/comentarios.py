"""Comment endpoints (Task 9: creation only, RF5)."""

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
