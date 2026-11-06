"""Business logic for users (Task 8: creation and listing)."""

from sqlalchemy import func, select

from backend.auth import hash_password
from backend.constants import AUTO_ASSIGN_ROLES, IT_ROLES, TicketState, UserRole
from backend.models import Ticket, User
from backend.schemas import UserCreate, UserUpdate

# Nuevo y En proceso (como ticket_service.OPEN_STATES, sin importarlo: el
# servicio de tickets ya importa este módulo).
_ABIERTOS = (TicketState.NEW.value, TicketState.IN_PROGRESS.value)


class RequesterAreaError(ValueError):
    """El Solicitante no tiene área de IT (HTTP 422)."""

    def __init__(self):
        super().__init__("El Solicitante no tiene área de IT: solo Técnicos y Administradores.")


class OpenTicketsAssignedError(ValueError):
    """Pasar a Solicitante a alguien de IT con tickets abiertos (HTTP 409):
    IT solo recibe, primero hay que reasignarlos."""

    def __init__(self, user: User, cantidad: int):
        self.cantidad = cantidad
        plural = "ticket abierto" if cantidad == 1 else "tickets abiertos"
        super().__init__(
            f"{user.name} tiene {cantidad} {plural} asignado(s): reasígnelos antes de "
            "cambiarle el rol a Solicitante.")


def _area_valida(session, area_id: int | None, role: str) -> int | None:
    """Revisa el área para ese rol: el Solicitante no tiene; la de IT tiene
    que existir y estar activa (errores de ``area_service``)."""
    if area_id is None:
        return None
    if role not in IT_ROLES:
        raise RequesterAreaError()
    from backend.services import area_service

    return area_service.get_active_area(session, area_id).id


def open_tickets_assigned(session, user_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(Ticket).where(
            Ticket.assigned_to_id == user_id, Ticket.state.in_(_ABIERTOS))
    ) or 0


def create_user(session, payload: UserCreate) -> User | None:
    """Persist a new user, or return ``None`` when the email already exists."""
    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        return None

    area_id = _area_valida(session, payload.area_id, payload.role.value)
    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role.value,
        password_hash=hash_password(payload.password) if payload.password else None,
        area_id=area_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def list_users(session, include_inactive: bool = False) -> list[User]:
    """Return the users ordered by id; only the active ones by default.

    Read-only. Without ``include_inactive`` only rows with ``is_active`` are
    exposed, so the assignment selector never offers an inactive user; the
    administration page asks for all of them to reactivate accounts.
    """
    statement = select(User).order_by(User.id)
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))
    return list(session.scalars(statement).all())


def get_user(session, user_id: int) -> User | None:
    """Return a user by id, or ``None`` when it does not exist."""
    return session.get(User, user_id)


def get_auto_assignable_users(session) -> list[User]:
    """Return the active users eligible for automatic assignment, by id.

    Read-only: only rows with ``is_active`` are exposed, and the role must be
    one of ``AUTO_ASSIGN_ROLES`` (``Técnico``). Used by the
    automatic ticket assignment (round-robin); the other roles are never
    picked automatically, though they can be assigned manually.
    """
    statement = (
        select(User)
        .where(User.is_active.is_(True))
        .where(User.role.in_(AUTO_ASSIGN_ROLES))
        .order_by(User.id)
    )
    return list(session.scalars(statement).all())


def update_user(session, user_id: int, payload: UserUpdate) -> User | None:
    """Apply a partial update to an existing user.

    Returns ``None`` when the user does not exist. Raises ``ValueError`` when
    the new email is already used by another user.

    Área de IT: solo Técnico y Administrador (:class:`RequesterAreaError`);
    tiene que estar activa. Pasar a Solicitante le quita el área y se
    rechaza si tiene tickets abiertos asignados
    (:class:`OpenTicketsAssignedError`).
    """
    user = session.get(User, user_id)
    if user is None:
        return None

    # Check email uniqueness (excluding the current user)
    if payload.email is not None:
        existing = session.scalar(
            select(User).where(User.email == payload.email, User.id != user_id)
        )
        if existing is not None:
            raise ValueError(f"El email '{payload.email}' ya está en uso")

    nuevo_rol = payload.role.value if payload.role is not None else user.role
    if nuevo_rol == UserRole.REQUESTER.value and user.role != UserRole.REQUESTER.value:
        cantidad = open_tickets_assigned(session, user.id)
        if cantidad:
            raise OpenTicketsAssignedError(user, cantidad)
    if "area_id" in payload.model_fields_set and not (
            payload.area_id == user.area_id and nuevo_rol in IT_ROLES):
        # (Mantener el área que ya tiene vale aunque esté desactivada.)
        area_id = _area_valida(session, payload.area_id, nuevo_rol)
    elif nuevo_rol not in IT_ROLES:
        area_id = None
    else:
        area_id = user.area_id

    # Apply changes
    user.area_id = area_id
    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role.value
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active

    session.commit()
    session.refresh(user)
    return user
