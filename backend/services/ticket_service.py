"""Business logic for tickets (creation, listing, edition, retrieval,
assignment and comments)."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import joinedload

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole
from backend.models import Comment, History, ProcessedEmail, Ticket, User
from backend.schemas import CommentCreate, TicketCreate, TicketUpdate
from backend.services.user_service import get_auto_assignable_users


# Clave del candado de Postgres (pg_advisory_xact_lock) que ordena la
# numeración: crear un ticket y renumerar nunca corren a la vez.
CANDADO_NUMERACION = 742_001


def reservar_numero(session) -> None:
    """El ticket que se inserta en esta transacción recibe el mayor id + 1
    (aunque antes se hayan creado y borrado otros; los huecos del medio no
    se rellenan).

    SQLite ya lo hace solo (``INTEGER PRIMARY KEY`` sin AUTOINCREMENT usa el
    mayor rowid + 1). En Postgres la secuencia nunca retrocede: se toma un
    candado de la transacción y se pone en ``MAX(id)``; otra creación espera
    al candado hasta el commit y ve el ticket nuevo, así dos tickets nunca
    reciben el mismo número.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": CANDADO_NUMERACION})
    session.execute(text(
        "SELECT setval(pg_get_serial_sequence('tickets', 'id'), COALESCE(MAX(id), 0) + 1, false) "
        "FROM tickets"
    ))


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


logger = logging.getLogger(__name__)
# Sale en «docker compose logs ticketera» (uvicorn no muestra los INFO de la app).
if not logger.handlers:
    _salida = logging.StreamHandler()
    _salida.setFormatter(logging.Formatter("TICKETS: %(message)s"))
    logger.addHandler(_salida)
    logger.setLevel(logging.INFO)
    logger.propagate = False


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


def pick_next_assignee(session) -> User | None:
    """Return the eligible user with the fewest assigned tickets.

    Round-robin among the active users whose role is in ``AUTO_ASSIGN_ROLES``
    (``Técnico``): ties are broken by lowest user id. Returns
    ``None`` when there are no eligible users, so the caller can leave the
    ticket unassigned. Read-only: it never modifies the ``users`` table.
    """
    eligible_users = get_auto_assignable_users(session)
    if not eligible_users:
        return None

    # Count assigned tickets per user (only counting eligible users).
    eligible_ids = [user.id for user in eligible_users]
    counts: dict[int, int] = {user_id: 0 for user_id in eligible_ids}
    assigned = session.scalars(
        select(Ticket.assigned_to_id).where(Ticket.assigned_to_id.in_(eligible_ids))
    ).all()
    for user_id in assigned:
        if user_id in counts:
            counts[user_id] += 1

    # Pick the user with fewest assigned tickets (tie: lowest id).
    best = min(eligible_users, key=lambda user: (counts[user.id], user.id))
    return best


def _audit_author(current_user: User | None) -> tuple[str | None, int | None]:
    """Return ``(author name, author id)`` for a new history entry.

    The authenticated user is the author of the audited action. Legacy rows
    (or internal calls without a user) store ``None`` for both values, and
    the UI renders them as ``Sistema``; new events never use ``"Anónimo"``.
    """
    if current_user is None:
        return None, None
    return current_user.name, current_user.id


def create_ticket(
    session,
    payload: TicketCreate,
    current_user: User | None = None,
    *,
    asignado: User | None = None,
    origen: str | None = None,
) -> Ticket:
    """Persist a new ticket.

    The initial ``state`` is not set here: it comes from the model default
    (``TicketState.NEW.value`` defined in ``backend/constants.py``), keeping a
    single source of truth for the initial state.

    The ticket is auto-assigned to the eligible user (``Técnico``) with the
    fewest assigned tickets (round-robin, tie: lowest
    id). When there are no eligible users the ticket is created unassigned,
    and the manual assignment endpoint (``PATCH .../assign``) remains
    available.

    ``asignado`` (tickets que llegan por correo: quien recibe el correo)
    reemplaza el reparto automático. ``origen`` es el texto que queda en el
    historial de la creación («Ticket creado desde correo enviado por … a
    …»).

    Registra una entrada de historial por la creación del ticket (RF9).
    """
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
        created_by_id=current_user.id if current_user is not None else None,
    )

    # Automatic round-robin assignment among active Support/Technician users,
    # unless the caller names the assignee.
    assignee = asignado if asignado is not None else pick_next_assignee(session)
    if assignee is not None:
        ticket.assigned_to_id = assignee.id

    reservar_numero(session)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    # Registry of creation in history (RF9), signed by the authenticated user
    author_name, author_id = _audit_author(current_user)
    if origen:
        # Creado desde un correo: el historial dice quién lo envió y a quién.
        campo, valor = "correo", origen
    else:
        # Automatic assignee (if any), so the history explains who got it.
        campo = "assigned_to_id" if assignee is not None else None
        valor = assignee.name if assignee is not None else None
    session.add(
        History(
            ticket_id=ticket.id,
            action="created",
            field=campo,
            old_value=None,
            new_value=valor,
            author=author_name,
            author_id=author_id,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def list_tickets(
    session,
    *,
    search: str | None = None,
    category: TicketCategory | None = None,
    priority: TicketPriority | None = None,
    state: TicketState | list[TicketState] | None = None,
    created_by_id: int | None = None,
    assigned_to_id: int | None = None,
    visible_para: User | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    """Return stored tickets, newest first (RF6), optionally searched and
    filtered (RF7, RF8).

    Every sent criterion is combined with AND. ``search`` matches partially
    in ``title`` and ``description`` without distinguishing case; a blank
    ``search`` behaves as if it were not sent. When no criteria are given the
    query is identical to the plain listing. Read-only query: it never
    modifies the stored rows. ``created_by_id`` restricts the listing to the
    tickets created by that user, ``assigned_to_id`` to the tickets assigned
    to that user ("Mis tickets") and ``visible_para`` to the tickets that
    user may see (:func:`filtro_visible`).

    Returns ``(page, total)``: ``total`` counts every matching ticket and
    ``page`` holds at most ``limit`` of them starting at ``offset`` (all of
    them when ``limit`` is ``None``).
    """
    statement = select(Ticket)

    if visible_para is not None:
        condicion = filtro_visible(visible_para)
        if condicion is not None:
            statement = statement.where(condicion)
    if created_by_id is not None:
        statement = statement.where(Ticket.created_by_id == created_by_id)
    if assigned_to_id is not None:
        statement = statement.where(Ticket.assigned_to_id == assigned_to_id)

    if category is not None:
        statement = statement.where(Ticket.category == category.value)
    if priority is not None:
        statement = statement.where(Ticket.priority == priority.value)
    if state:
        states = state if isinstance(state, (list, tuple)) else [state]
        statement = statement.where(Ticket.state.in_([s.value for s in states]))

    if search is not None:
        term = search.strip().lower()
        if term:
            statement = statement.where(
                or_(
                    Ticket.title.ilike(_like_pattern(term), escape="\\"),
                    Ticket.description.ilike(_like_pattern(term), escape="\\"),
                )
            )

    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    statement = statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all()), total


OPEN_STATES = (TicketState.NEW.value, TicketState.IN_PROGRESS.value)


def ticket_summary(session, user: User) -> dict[str, int]:
    """Counters for the dashboard over the tickets ``user`` can see."""
    base = select(Ticket)
    condicion = filtro_visible(user)
    if condicion is not None:
        base = base.where(condicion)

    def count(*conditions) -> int:
        statement = base.where(*conditions) if conditions else base
        return session.scalar(select(func.count()).select_from(statement.subquery()))

    return {
        "total": count(),
        "nuevos": count(Ticket.state == TicketState.NEW.value),
        "en_proceso": count(Ticket.state == TicketState.IN_PROGRESS.value),
        # Un ticket Cerrado ya pasó por Resuelto: cuenta como resuelto.
        "resueltos": count(
            Ticket.state.in_((TicketState.RESOLVED.value, TicketState.CLOSED.value))
        ),
        "cerrados": count(Ticket.state == TicketState.CLOSED.value),
        "criticos_abiertos": count(
            Ticket.priority == TicketPriority.CRITICAL.value,
            Ticket.state.in_(OPEN_STATES),
        ),
        "mios_abiertos": count(
            Ticket.assigned_to_id == user.id,
            Ticket.state.in_(OPEN_STATES),
        ),
    }


def get_ticket(session, ticket_id: int) -> Ticket | None:
    """Return a ticket by id, or ``None`` when it does not exist."""
    return session.get(Ticket, ticket_id)


def filtro_visible(user: User):
    """Condición SQL de los tickets que ``user`` puede ver, o ``None`` si los
    ve todos. El Solicitante ve los que creó y los que tiene asignados (por
    ejemplo, los que le llegaron desde un correo); los demás roles, todos."""
    if user.role != UserRole.REQUESTER.value:
        return None
    return or_(Ticket.created_by_id == user.id, Ticket.assigned_to_id == user.id)


def can_view_ticket(ticket: Ticket, user: User | None) -> bool:
    """Whether ``user`` may read ``ticket`` (and its comments and history).

    A ``Solicitante`` only sees the tickets they created or that are
    assigned to them; every other role sees all tickets.
    """
    if user is None or user.role != UserRole.REQUESTER.value:
        return True
    return user.id in (ticket.created_by_id, ticket.assigned_to_id)


def can_change_state(ticket: Ticket, user: User) -> bool:
    """Técnico y Administrador cambian el estado de cualquier
    ticket; cualquier otro rol, solo el de los tickets asignados a él."""
    return user.role != UserRole.REQUESTER.value or ticket.assigned_to_id == user.id


def get_visible_ticket(session, ticket_id: int, user: User | None) -> Ticket | None:
    """Return the ticket when it exists and ``user`` may see it, else ``None``.

    A ticket the user may not see is reported as missing (``None``) so its
    existence is not revealed.
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or not can_view_ticket(ticket, user):
        return None
    return ticket


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


def get_global_history(session) -> list[History]:
    """Return the audit entries of every ticket, newest first.

    Read-only: it exposes the existing ``history`` rows and never creates
    them. Ordering is ``created_at`` descending (most recent first) with
    ``id`` descending as tiebreaker; there is no pagination.
    """
    entries = session.scalars(
        select(History)
        .order_by(History.created_at.desc(), History.id.desc())
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


def update_ticket(
    session,
    ticket_id: int,
    payload: TicketUpdate,
    current_user: User | None = None,
) -> Ticket | None:
    """Apply a partial update to an existing ticket.

    Returns ``None`` when the ticket does not exist (the router answers 404).
    Only the fields present in ``TicketUpdate`` are touched; the ORM triggers
    ``updated_at`` through the model's ``onupdate=utc_now``.
    A history entry is recorded for each changed field (RF9).
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        return None

    changes = {
        field: value
        for field, value in payload.model_dump(mode="json", exclude_unset=True).items()
        if value is not None
    }
    # Build history entries for changed fields, signed by the authenticated user
    author_name, author_id = _audit_author(current_user)
    for field, new_value in changes.items():
        old_value = getattr(ticket, field)
        if old_value != new_value:
            session.add(
                History(
                    ticket_id=ticket.id,
                    action="updated",
                    field=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                    author=author_name,
                    author_id=author_id,
                )
            )
    for field, value in changes.items():
        setattr(ticket, field, value)

    session.commit()
    session.refresh(ticket)
    return ticket


def assign_ticket(
    session,
    ticket_id: int,
    assigned_to_id: int | None,
    current_user: User | None = None,
) -> Ticket:
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

    old_assignee_name = ticket.assignee.name if ticket.assignee is not None else None
    ticket.assigned_to_id = assigned_to_id
    session.commit()
    session.refresh(ticket)
    # Registry of assignment/unassignment in history (RF9), signed by the
    # authenticated user that performed the assignment.
    author_name, author_id = _audit_author(current_user)
    session.add(
        History(
            ticket_id=ticket.id,
            action="assigned",
            field="assigned_to_id",
            # Names, not ids, so the history reads on its own ("Ana → Luis").
            old_value=old_assignee_name,
            new_value=ticket.assignee.name if ticket.assignee is not None else None,
            author=author_name,
            author_id=author_id,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def change_ticket_state(
    session,
    ticket_id: int,
    new_state: TicketState,
    current_user: User | None = None,
) -> Ticket:
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
    author_name, author_id = _audit_author(current_user)
    session.add(
        History(
            ticket_id=ticket.id,
            action="Cambio de estado",
            field="state",
            old_value=current_state.value,
            new_value=new_state.value,
            author=author_name,
            author_id=author_id,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def create_comment(
    session,
    ticket_id: int,
    payload: CommentCreate,
    current_user: User | None = None,
) -> Comment:
    """Persist a comment on an existing ticket (RF5).

    Raises:
        ``TicketNotFoundError``: the ticket does not exist.
    """
    if session.get(Ticket, ticket_id) is None:
        raise TicketNotFoundError(ticket_id)

    # El autor es el usuario autenticado que escribe el comentario; el
    # ``author`` que envíe el cliente se ignora. "Anónimo" solo queda para
    # llamadas internas sin usuario.
    author = current_user.name if current_user is not None else "Anónimo"

    comment = Comment(
        ticket_id=ticket_id,
        author=author,
        content=payload.content,
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    # Registry of comment in history (RF9), signed by the same user.
    author_name, author_id = _audit_author(current_user)
    session.add(
        History(
            ticket_id=ticket_id,
            action="commented",
            field="comment",
            old_value=None,
            new_value=payload.content,
            author=author_name,
            author_id=author_id,
        )
    )
    session.commit()
    session.refresh(comment)
    return comment


def delete_ticket(session, ticket_id: int, current_user: User) -> None:
    """Elimina un ticket con sus comentarios, su historial y su explicación de
    la IA, en una transacción: un ticket nuevo con el mismo número no hereda nada.

    El registro del correo que lo creó (si vino por correo) se conserva con
    ``ticket_id`` en ``NULL``: así ese correo nunca vuelve a crear un ticket.
    Como el historial desaparece con el ticket, quién lo eliminó y cuándo
    queda en el log de la aplicación.

    Raises:
        ``TicketNotFoundError``: el ticket no existe.
    """
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise TicketNotFoundError(ticket_id)
    titulo = ticket.title
    try:
        session.execute(
            update(ProcessedEmail)
            .where(ProcessedEmail.ticket_id == ticket_id)
            .values(ticket_id=None)
        )
        session.delete(ticket)  # comentarios e historial: cascade en el modelo
        session.commit()
    except Exception:
        session.rollback()
        raise
    momento = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(
        "%s (%s, id %s) eliminó el ticket #%s «%s» el %s",
        current_user.name, current_user.email, current_user.id, ticket_id, titulo, momento,
    )
