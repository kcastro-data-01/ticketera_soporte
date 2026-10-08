"""Business logic for users (Task 8: creation and listing)."""

from sqlalchemy import select

from backend.models import User
from backend.schemas import UserCreate


def create_user(session, payload: UserCreate) -> User | None:
    """Persist a new user, or return ``None`` when the email already exists."""
    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        return None

    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role.value,
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
