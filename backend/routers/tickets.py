"""Ticket endpoints (Task 4: creation only)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.schemas import TicketCreate, TicketResponse
from backend.services import ticket_service

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un ticket",
)
def create_ticket(
    payload: TicketCreate,
    session: Session = Depends(get_session),
) -> TicketResponse:
    """Create a ticket with title, description, category and priority (RF1, RF2)."""
    ticket = ticket_service.create_ticket(session, payload)
    return TicketResponse.model_validate(ticket)
