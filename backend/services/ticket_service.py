"""Business logic for tickets (Task 4: creation, Task 5: listing, Task 6: edition)."""

from sqlalchemy import select

from backend.models import Ticket
from backend.schemas import TicketCreate, TicketUpdate


def create_ticket(session, payload: TicketCreate) -> Ticket:
    """Persist a new ticket.

    The initial ``state`` is not set here: it comes from the model default
    (``TicketState.NEW.value`` defined in ``backend/constants.py``), keeping a
    single source of truth for the initial state.
    """
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def list_tickets(session) -> list[Ticket]:
    """Return every stored ticket, newest first (RF6).

    Read-only query: it never modifies the stored rows.
    """
    statement = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc())
    return list(session.scalars(statement).all())


def update_ticket(session, ticket_id: int, payload: TicketUpdate) -> Ticket | None:
    """Apply a partial update to an existing ticket.

    Returns ``None`` when the ticket does not exist (the router answers 404).
    Only the fields present in ``TicketUpdate`` are touched; the ORM triggers
    ``updated_at`` through the model's ``onupdate=utc_now``.
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        return None

    changes = {
        field: value
        for field, value in payload.model_dump(mode="json", exclude_unset=True).items()
        if value is not None
    }
    for field, value in changes.items():
        setattr(ticket, field, value)

    session.commit()
    session.refresh(ticket)
    return ticket
