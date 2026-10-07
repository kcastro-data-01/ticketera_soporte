"""Tests for the database configuration and the ORM models (Task 2)."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole
from backend.database import enable_sqlite_foreign_keys, init_db
from backend.models import Comment, History, Ticket, User

EXPECTED_TABLES = {"users", "tickets", "comments", "history"}


def _new_ticket(**overrides) -> Ticket:
    """Build a ticket with valid defaults; individual fields can be overridden."""
    fields = {
        "title": "No enciende la impresora",
        "description": "La impresora del piso 2 no responde al iniciar el turno.",
        "category": TicketCategory.INCIDENT.value,
        "priority": TicketPriority.HIGH.value,
    }
    fields.update(overrides)
    return Ticket(**fields)


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

def test_tables_are_created(engine):
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))


def test_init_db_creates_database_file(tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path / 'created.db'}")
    enable_sqlite_foreign_keys(test_engine)

    init_db(target_engine=test_engine)

    inspector = inspect(test_engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
    assert (tmp_path / "created.db").exists()
    test_engine.dispose()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def test_create_and_read_user(session):
    user = User(name="Ana Pérez", email="ana@soporte.local")
    session.add(user)
    session.commit()

    stored = session.get(User, user.id)
    assert stored.name == "Ana Pérez"
    assert stored.email == "ana@soporte.local"
    assert stored.role == UserRole.SUPPORT.value
    assert stored.is_active is True


def test_duplicate_user_email_is_rejected(session):
    session.add(User(name="Ana", email="dup@soporte.local"))
    session.commit()

    session.add(User(name="Otra", email="dup@soporte.local"))
    with pytest.raises(IntegrityError):
        session.commit()


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def test_create_and_read_ticket_with_defaults(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.commit()

    stored = session.get(Ticket, ticket.id)
    assert stored.id is not None
    assert stored.title == "No enciende la impresora"
    assert stored.state == TicketState.NEW.value  # initial state (RF3)
    assert stored.assigned_to_id is None  # assignment is optional (RF4)
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_ticket_can_be_assigned_to_user(session):
    user = User(name="Luis Gómez", email="luis@soporte.local")
    ticket = _new_ticket()
    session.add_all([user, ticket])
    session.flush()
    ticket.assigned_to_id = user.id
    session.commit()

    stored = session.get(Ticket, ticket.id)
    assert stored.assigned_to_id == user.id
    assert stored.assignee.name == "Luis Gómez"
    assert user.tickets == [stored]


def test_ticket_update_refreshes_updated_at(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.commit()
    original_updated_at = ticket.updated_at

    ticket.title = "Impresora arreglada parcialmente"
    session.commit()

    assert ticket.updated_at > original_updated_at


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "ab"},  # too short (< 3 characters)
        {"title": "   "},  # blank
        {"description": "   "},  # blank description
        {"category": "Otra categoría"},  # not an approved category
        {"priority": "Urgentísima"},  # not an approved priority
        {"state": "Pendiente"},  # not an approved state
    ],
    ids=["short-title", "blank-title", "blank-description", "bad-category", "bad-priority", "bad-state"],
)
def test_invalid_ticket_values_are_rejected(session, overrides):
    session.add(_new_ticket(**overrides))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ---------------------------------------------------------------------------
# Comments and history
# ---------------------------------------------------------------------------

def test_comments_and_history_persist_and_relate(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.flush()

    session.add_all(
        [
            Comment(ticket_id=ticket.id, author="Ana", content="Primer contacto con el cliente."),
            Comment(ticket_id=ticket.id, author="Luis", content="Repuesto en camino."),
            History(ticket_id=ticket.id, action="created", author="Ana"),
        ]
    )
    session.commit()
    session.expire_all()

    stored = session.get(Ticket, ticket.id)
    assert [comment.content for comment in stored.comments] == [
        "Primer contacto con el cliente.",
        "Repuesto en camino.",
    ]
    assert stored.comments[0].author == "Ana"
    assert len(stored.history) == 1
    assert stored.history[0].action == "created"


def test_comment_requires_existing_ticket(session):
    session.add(Comment(ticket_id=9999, author="Ana", content="Huerfano"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_empty_comment_is_rejected(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.flush()

    session.add(Comment(ticket_id=ticket.id, author="Ana", content="   "))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_history_entry_stores_old_and_new_values(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.flush()

    entry = History(
        ticket_id=ticket.id,
        action="state_changed",
        field="state",
        old_value=TicketState.NEW.value,
        new_value=TicketState.IN_PROGRESS.value,
        author="Luis",
    )
    session.add(entry)
    session.commit()

    stored = session.get(History, entry.id)
    assert stored.field == "state"
    assert stored.old_value == TicketState.NEW.value
    assert stored.new_value == TicketState.IN_PROGRESS.value
    assert stored.author == "Luis"


# ---------------------------------------------------------------------------
# Relationships and cascades
# ---------------------------------------------------------------------------

def test_deleting_ticket_cascades_to_comments_and_history(session):
    ticket = _new_ticket()
    session.add(ticket)
    session.flush()
    session.add(Comment(ticket_id=ticket.id, author="Ana", content="Comentario"))
    session.add(History(ticket_id=ticket.id, action="created"))
    session.commit()

    session.delete(ticket)
    session.commit()

    assert session.query(Comment).count() == 0
    assert session.query(History).count() == 0


def test_foreign_keys_are_enforced(session):
    """A ticket assigned to a non-existent user must fail (PRAGMA foreign_keys)."""
    session.add(_new_ticket(assigned_to_id=9999))
    with pytest.raises(IntegrityError):
        session.commit()
