"""Business logic for tickets (creation, listing, edition, retrieval,
assignment and comments)."""

from sqlalchemy import select

from backend.models import Comment, Ticket, User
from backend.schemas import CommentCreate, TicketCreate, TicketUpdate


class UserNotFoundError(Exception):
    """Raised when assigning a ticket to a user that does not exist."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")


class TicketNotFoundError(Exception):
    """Raised when the target ticket of an operation does not exist."""

    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")


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


def get_ticket(session, ticket_id: int) -> Ticket | None:
    """Return a ticket by id, or ``None`` when it does not exist."""
    return session.get(Ticket, ticket_id)


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


def assign_ticket(session, ticket_id: int, assigned_to_id: int | None) -> Ticket:
    """Assign a ticket to a user, or unassign it when ``assigned_to_id`` is None.

    Raises:
        ``TicketNotFoundError``: the ticket does not exist.
        ``UserNotFoundError``: the target user does not exist.
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise TicketNotFoundError(ticket_id)

    if assigned_to_id is not None and session.get(User, assigned_to_id) is None:
        raise UserNotFoundError(assigned_to_id)

    ticket.assigned_to_id = assigned_to_id
    session.commit()
    session.refresh(ticket)
    return ticket


def create_comment(session, ticket_id: int, payload: CommentCreate) -> Comment:
    """Persist a comment on an existing ticket (RF5).

    Raises:
        ``TicketNotFoundError``: the ticket does not exist.
    """
    if session.get(Ticket, ticket_id) is None:
        raise TicketNotFoundError(ticket_id)

    comment = Comment(
        ticket_id=ticket_id,
        author=payload.author,
        content=payload.content,
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment
