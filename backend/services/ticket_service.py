"""Business logic for tickets (Task 4: creation only)."""

from backend.models import Ticket
from backend.schemas import TicketCreate


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
