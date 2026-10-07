"""SQLAlchemy models of the support ticket system.

Identifiers (tables, columns, relationships) are in English; enum values
stored in ``category``, ``priority`` and ``state`` are the Spanish strings
defined in ``backend.constants`` because they are shown in the UI.
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.constants import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
    TicketState,
    UserRole,
)
from backend.database import Base


def utc_now() -> datetime:
    """Current UTC timestamp used as default for audit columns."""
    return datetime.now(timezone.utc)


def _sql_in(values: tuple[str, ...]) -> str:
    """Render a tuple of strings as a SQL ``IN (...)`` list of literals."""
    return ", ".join(f"'{value}'" for value in values)


class User(Base):
    """Minimal user record: only needed to assign tickets (no authentication)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default=UserRole.SUPPORT.value)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="assignee")


class Ticket(Base):
    """A support ticket: the central entity of the system (RF1, RF2, RF3, RF4)."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) >= 3 AND length(title) <= 200",
            name="ck_tickets_title_length",
        ),
        CheckConstraint(
            "length(trim(description)) >= 1",
            name="ck_tickets_description_not_empty",
        ),
        CheckConstraint(
            f"category IN ({_sql_in(TICKET_CATEGORIES)})",
            name="ck_tickets_category",
        ),
        CheckConstraint(
            f"priority IN ({_sql_in(TICKET_PRIORITIES)})",
            name="ck_tickets_priority",
        ),
        CheckConstraint(
            f"state IN ({_sql_in(TICKET_STATES)})",
            name="ck_tickets_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TicketState.NEW.value,
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    assignee: Mapped[User | None] = relationship(back_populates="tickets")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )
    history: Mapped[list["History"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="History.created_at",
    )


class Comment(Base):
    """A comment written on a ticket (RF5).

    ``author`` is a free-text name because there is no authentication.
    """

    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            "length(trim(content)) >= 1",
            name="ck_comments_content_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="comments")


class History(Base):
    """Audit entry recording one change made to a ticket (RF9).

    ``action`` identifies the kind of change (for example ``created``,
    ``state_changed``, ``assigned``); ``field``, ``old_value`` and ``new_value``
    describe what changed. ``author`` is free text: there is no authentication.
    """

    __tablename__ = "history"
    __table_args__ = (
        CheckConstraint(
            "length(trim(action)) >= 1",
            name="ck_history_action_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    field: Mapped[str | None] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="history")
