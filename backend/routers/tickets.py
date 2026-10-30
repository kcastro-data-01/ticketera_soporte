"""Ticket endpoints (creation, listing with search and filters, retrieval,
edition, assignment, state changes, history and deletion)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.schemas import (
    HistoryResponse,
    TicketAssignment,
    TicketCreate,
    TicketResponse,
    TicketStateUpdate,
    TicketSummary,
    TicketUpdate,
)
from backend.services import ticket_service
from backend.services.ticket_service import (
    InvalidTransitionError,
    TicketNotFoundError,
    UserNotFoundError,
)
from backend.models import User
from backend.routers.auth import (
    ROLES_ADMIN,
    ROLES_TODOS,
    role_required,
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
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> TicketResponse:
    """Create a ticket with title, description, category and priority (RF1, RF2)."""
    ticket = ticket_service.create_ticket(session, payload, current_user)
    return TicketResponse.model_validate(ticket)


@router.get(
    "",
    response_model=list[TicketResponse],
    summary="Listar, buscar y filtrar tickets",
)
def list_tickets(
    response: Response,
    search: str | None = Query(
        None,
        description=(
            "Texto parcial a buscar en title o description, sin distinguir "
            "mayúsculas. Vacío o solo espacios equivale a no enviarlo."
        ),
    ),
    category: TicketCategory | None = Query(
        None,
        description="Filtra por categoría (Hardware, Software, Red, Accesos).",
    ),
    priority: TicketPriority | None = Query(
        None,
        description="Filtra por prioridad (Baja, Media, Alta, Crítica).",
    ),
    state: list[TicketState] | None = Query(
        None,
        description=(
            "Filtra por estado (Nuevo, En proceso, Resuelto, Cerrado). Se puede "
            "repetir para varios estados: ?state=Resuelto&state=Cerrado."
        ),
    ),
    mios: bool = Query(
        False,
        description="Solo los tickets asignados al usuario que consulta.",
    ),
    limit: int | None = Query(
        None, ge=1, le=100, description="Tamaño de página (sin él, todos)."
    ),
    offset: int = Query(0, ge=0, description="Tickets a saltar (paginación)."),
    session: Session = Depends(get_session),
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> list[TicketResponse]:
    """Return all stored tickets, newest first (RF6), searchable by text and
    filterable by category, priority and state (RF7, RF8).

    The criteria are optional and combined with AND; without parameters the
    response is the plain listing. ``mios`` keeps the tickets assigned to the
    caller; ``limit``/``offset`` paginate and the ``X-Total-Count`` header
    carries the number of matching tickets.
    """
    tickets, total = ticket_service.list_tickets(
        session,
        search=search,
        category=category,
        priority=priority,
        state=state,
        # El Solicitante: los que creó y los asignados a él.
        visible_para=current_user,
        assigned_to_id=current_user.id if mios else None,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return [TicketResponse.model_validate(ticket) for ticket in tickets]


@router.get(
    "/summary",
    response_model=TicketSummary,
    summary="Resumen de tickets para el panel de inicio",
)
def get_ticket_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_TODOS)),
) -> TicketSummary:
    """Counters over the tickets the caller can see (the Solicitante only
    counts the tickets they created)."""
    return TicketSummary(**ticket_service.ticket_summary(session, current_user))


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Consultar un ticket",
)
def get_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> TicketResponse:
    """Return a single ticket by id (read-only)."""
    ticket = ticket_service.get_visible_ticket(session, ticket_id, current_user)
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
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> list[HistoryResponse]:
    """Return the audit entries recorded for a ticket, oldest first (RF9).

    Read-only: it exposes the existing ``history`` rows and never creates
    them. Optional model fields (``field``, ``old_value``, ``new_value``,
    ``author``) are returned as ``null`` when unavailable.
    """
    if ticket_service.get_visible_ticket(session, ticket_id, current_user) is None:
        entries = None
    else:
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
    current_user: User = Depends(
        role_required(ROLES_ADMIN)
    ),
) -> TicketResponse:
    """Update title, description, category and/or priority of a ticket."""
    ticket = ticket_service.update_ticket(session, ticket_id, payload, current_user)
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
    current_user: User = Depends(
        role_required(ROLES_ADMIN)
    ),
) -> TicketResponse:
    """Assign a user to a ticket; ``assigned_to_id: null`` unassigns it (RF4)."""
    try:
        ticket = ticket_service.assign_ticket(
            session, ticket_id, payload.assigned_to_id, current_user
        )
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
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> TicketResponse:
    """Move a ticket through the allowed workflow transitions (RF3).

    Técnico y Administrador cambian cualquier ticket; los demás
    roles (Solicitante), solo los asignados a ellos (``403`` si no). Un
    ticket que no puede ver responde ``404``.

    A ticket moves forward to any later state, even skipping steps
    (``Nuevo → Cerrado``); a ``Resuelto`` ticket is reopened only to ``En
    proceso``. ``Cerrado`` is final. Going back to ``Nuevo``, any change on a
    ``Cerrado`` ticket or staying in the same state is answered with ``409
    Conflict``. The new state comes from the existing ``TicketState`` enum,
    so an unknown value is rejected with ``422``. An optional ``motivo`` is
    saved as a comment of the ticket in the same transaction.
    """
    visible = ticket_service.get_visible_ticket(session, ticket_id, current_user)
    if visible is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    if not ticket_service.can_change_state(visible, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a este recurso",
        )
    try:
        ticket = ticket_service.change_ticket_state(
            session, ticket_id, payload.state, current_user, payload.motivo
        )
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


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un ticket (solo Administrador)",
)
def delete_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(role_required(ROLES_ADMIN)),
) -> Response:
    """Delete a ticket with its comments and history (Administrador only)."""
    try:
        ticket_service.delete_ticket(session, ticket_id, current_user)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} no encontrado",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
