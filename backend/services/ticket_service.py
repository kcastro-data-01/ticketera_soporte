"""Business logic for tickets (creation, listing, edition, retrieval,
assignment and comments)."""

from sqlalchemy import or_, select

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Comment, History, Ticket, User
from backend.schemas import CommentCreate, TicketCreate, TicketUpdate


def _like_pattern(term: str) -> str:
    """Wrap a literal search term as an escaped SQL ``LIKE`` pattern.

    ``%`` and ``_`` are escaped so they are matched literally instead of
    acting as wildcards.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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


class InvalidTransitionError(Exception):
    """Raised when the requested state change is not an allowed transition.

    ``current`` and ``target`` keep the Spanish values shown by the UI so the
    router can build a clear message (answered as HTTP 409).
    """

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Transition from {current} to {target} not allowed")


# Allowed state transitions (RF3, Task 18): linear forward workflow only —
# no jumps and no backwards moves. "Cerrado" is terminal.
ALLOWED_TRANSITIONS: dict[TicketState, frozenset[TicketState]] = {
    TicketState.NEW: frozenset({TicketState.IN_PROGRESS}),
    TicketState.IN_PROGRESS: frozenset({TicketState.RESOLVED}),
    TicketState.RESOLVED: frozenset({TicketState.CLOSED}),
    TicketState.CLOSED: frozenset(),
}


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


def list_tickets(
    session,
    *,
    search: str | None = None,
    category: TicketCategory | None = None,
    priority: TicketPriority | None = None,
    state: TicketState | None = None,
) -> list[Ticket]:
    """Return stored tickets, newest first (RF6), optionally searched and
    filtered (RF7, RF8).

    Every sent criterion is combined with AND. ``search`` matches partially
    in ``title`` and ``description`` without distinguishing case; a blank
    ``search`` behaves as if it were not sent. When no criteria are given the
    query is identical to the plain listing. Read-only query: it never
    modifies the stored rows.
    """
    statement = select(Ticket)

    if category is not None:
        statement = statement.where(Ticket.category == category.value)
    if priority is not None:
        statement = statement.where(Ticket.priority == priority.value)
    if state is not None:
        statement = statement.where(Ticket.state == state.value)

    if search is not None:
        term = search.strip().lower()
        if term:
            statement = statement.where(
                or_(
                    Ticket.title.ilike(_like_pattern(term), escape="\\"),
                    Ticket.description.ilike(_like_pattern(term), escape="\\"),
                )
            )

    statement = statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    return list(session.scalars(statement).all())


def get_ticket(session, ticket_id: int) -> Ticket | None:
    """Return a ticket by id, or ``None`` when it does not exist."""
    return session.get(Ticket, ticket_id)


def get_ticket_history(session, ticket_id: int) -> list[History] | None:
    """Return the audit entries stored for a ticket, oldest first (RF9).

    Returns ``None`` when the ticket does not exist so the router can
    distinguish "missing ticket" from "no entries yet". Ordering is
    ``created_at`` with ``id`` as tiebreaker; there is no pagination.
    The function only reads the ``history`` table: it never creates entries.
    """
    if session.get(Ticket, ticket_id) is None:
        return None

    entries = session.scalars(
        select(History)
        .where(History.ticket_id == ticket_id)
        .order_by(History.created_at, History.id)
    ).all()
    return list(entries)


def get_ticket_comments(session, ticket_id: int) -> list[Comment] | None:
    """Return the comments stored for a ticket, oldest first (RF5).

    Returns ``None`` when the ticket does not exist so the router can
    distinguish "missing ticket" from "no comments yet". Ordering is
    ``created_at`` with ``id`` as tiebreaker (chronological); there is no
    pagination. The function only reads the ``comments`` table: it never
    creates entries.
    """
    if session.get(Ticket, ticket_id) is None:
        return None

    comments = session.scalars(
        select(Comment)
        .where(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at, Comment.id)
    ).all()
    return list(comments)


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


def change_ticket_state(session, ticket_id: int, new_state: TicketState) -> Ticket:
    """Move a ticket to another state through an allowed transition (RF3).

    The state update and its audit entry are both added to the session and
    committed in one go, so a failure cannot leave a ticket updated without
    its history entry nor an orphan history entry. A rejected transition
    raises before anything is written, so it never reaches the history.

    Raises:
        ``TicketNotFoundError``: the ticket does not exist.
        ``InvalidTransitionError``: the transition is not allowed. Staying in
            the same state is rejected as well: only the linear forward
            moves (``Nuevo → En proceso → Resuelto → Cerrado``) are valid.
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise TicketNotFoundError(ticket_id)

    current_state = TicketState(ticket.state)
    if new_state == current_state or new_state not in ALLOWED_TRANSITIONS[current_state]:
        raise InvalidTransitionError(current_state.value, new_state.value)

    ticket.state = new_state.value  # ``updated_at`` refreshed by ``onupdate``
    session.add(
        History(
            ticket_id=ticket.id,
            action="Cambio de estado",
            field="state",
            old_value=current_state.value,
            new_value=new_state.value,
            author="Anónimo",  # same convention as comments: no authentication
        )
    )
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
