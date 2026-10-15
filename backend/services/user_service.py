"""Business logic for users (Task 8: creation and listing)."""

from sqlalchemy import select

from backend.auth import hash_password
from backend.constants import AUTO_ASSIGN_ROLES
from backend.models import User
from backend.schemas import UserCreate, UserUpdate


def create_user(session, payload: UserCreate) -> User | None:
    """Persist a new user, or return ``None`` when the email already exists."""
    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        return None

    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role.value,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def list_users(session) -> list[User]:
    """Return the active users available to assign tickets, ordered by id.

    Read-only: only rows with ``is_active`` are exposed, so the frontend
    selector never offers an inactive user.
    """
    statement = (
        select(User).where(User.is_active.is_(True)).order_by(User.id)
    )
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

    # Apply changes
    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role.value
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    session.commit()
    session.refresh(user)
    return user
