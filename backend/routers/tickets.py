"""Ticket endpoints (creation, listing with search and filters, retrieval,
edition, assignment, state changes and history)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.database import get_session
from backend.schemas import (
    HistoryResponse,
    TicketAssignment,
    TicketCreate,
    TicketResponse,
    TicketStateUpdate,
    TicketUpdate,
)
from backend.services import ticket_service
from backend.services.ticket_service import (
    InvalidTransitionError,
    TicketNotFoundError,
    UserNotFoundError,
)

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
    summary="Listar, buscar y filtrar tickets",
)
def list_tickets(
    search: str | None = Query(
        None,
        description=(
            "Texto parcial a buscar en title o description, sin distinguir "
            "mayúsculas. Vacío o solo espacios equivale a no enviarlo."
        ),
    ),
    category: TicketCategory | None = Query(
        None,
        description="Filtra por categoría (Incidente, Consulta, Solicitud, Mantenimiento).",
    ),
    priority: TicketPriority | None = Query(
        None,
        description="Filtra por prioridad (Baja, Media, Alta, Crítica).",
    ),
    state: TicketState | None = Query(
        None,
        description="Filtra por estado (Nuevo, En proceso, Resuelto, Cerrado).",
    ),
    session: Session = Depends(get_session),
) -> list[TicketResponse]:
    """Return all stored tickets, newest first (RF6), searchable by text and
    filterable by category, priority and state (RF7, RF8).

    The criteria are optional and combined with AND; without parameters the
    response is the plain listing.
    """
    tickets = ticket_service.list_tickets(
        session,
        search=search,
        category=category,
        priority=priority,
        state=state,
    )
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


@router.get(
    "/{ticket_id}/history",
    response_model=list[HistoryResponse],
    summary="Historial de cambios de un ticket",
)
def get_ticket_history(
    ticket_id: int,
    session: Session = Depends(get_session),
) -> list[HistoryResponse]:
    """Return the audit entries recorded for a ticket, oldest first (RF9).

    Read-only: it exposes the existing ``history`` rows and never creates
    them. Optional model fields (``field``, ``old_value``, ``new_value``,
    ``author``) are returned as ``null`` when unavailable.
    """
    entries = ticket_service.get_ticket_history(session, ticket_id)
    if entries is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return [HistoryResponse.model_validate(entry) for entry in entries]


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


@router.patch(
    "/{ticket_id}/state",
    response_model=TicketResponse,
    summary="Cambiar el estado de un ticket",
)
def change_ticket_state(
    ticket_id: int,
    payload: TicketStateUpdate,
    session: Session = Depends(get_session),
) -> TicketResponse:
    """Move a ticket through the allowed workflow transitions (RF3).

    Only the forward linear moves are accepted: ``Nuevo → En proceso``,
    ``En proceso → Resuelto`` and ``Resuelto → Cerrado``. Any jump, step
    back, repeated state or change on a ``Cerrado`` ticket is answered with
    ``409 Conflict``. The new state comes from the existing ``TicketState``
    enum, so an unknown value is rejected with ``422``.
    """
    try:
        ticket = ticket_service.change_ticket_state(session, ticket_id, payload.state)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    except InvalidTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Transición de '{error.current}' a '{error.target}' no permitida"
            ),
        )
    return TicketResponse.model_validate(ticket)
