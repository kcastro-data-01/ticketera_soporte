"""Ticket endpoints (creation, listing, retrieval, edition and assignment)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.schemas import TicketAssignment, TicketCreate, TicketResponse, TicketUpdate
from backend.services import ticket_service
from backend.services.ticket_service import TicketNotFoundError, UserNotFoundError

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


@router.get(
    "",
    response_model=list[TicketResponse],
    summary="Listar tickets",
)
def list_tickets(session: Session = Depends(get_session)) -> list[TicketResponse]:
    """Return all stored tickets, newest first (RF6)."""
    tickets = ticket_service.list_tickets(session)
    return [TicketResponse.model_validate(ticket) for ticket in tickets]


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Consultar un ticket",
)
def get_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
) -> TicketResponse:
    """Return a single ticket by id (read-only)."""
    ticket = ticket_service.get_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return TicketResponse.model_validate(ticket)


@router.patch(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Editar un ticket",
)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    session: Session = Depends(get_session),
) -> TicketResponse:
    """Update title, description, category and/or priority of a ticket."""
    ticket = ticket_service.update_ticket(session, ticket_id, payload)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return TicketResponse.model_validate(ticket)


@router.patch(
    "/{ticket_id}/assign",
    response_model=TicketResponse,
    summary="Asignar o desasignar un ticket",
)
def assign_ticket(
    ticket_id: int,
    payload: TicketAssignment,
    session: Session = Depends(get_session),
) -> TicketResponse:
    """Assign a user to a ticket; ``assigned_to_id: null`` unassigns it (RF4)."""
    try:
        ticket = ticket_service.assign_ticket(session, ticket_id, payload.assigned_to_id)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario {error.user_id} no encontrado",
        )
    return TicketResponse.model_validate(ticket)
