"""Pruebas del script backend.reset_users."""

import pytest
from sqlalchemy import select

from backend.auth import verify_password
from backend.constants import UserRole
from backend.models import History, Ticket, User
from backend.reset_users import TEST_USERS, reset_users


def add_user(session, name, email, role=UserRole.SUPPORT.value):
    user = User(name=name, email=email, role=role, password_hash="x")
    session.add(user)
    session.commit()
    return user


def emails(session):
    return {user.email for user in session.scalars(select(User)).all()}


def test_dry_run_changes_nothing(session):
    add_user(session, "Sofía Cubero", "soficubero@correo.com")
    add_user(session, "Viejo", "viejo@correo.com")

    summary = reset_users(session, "soficubero")

    assert summary["deleted"] == ["viejo@correo.com"]
    assert emails(session) == {"soficubero@correo.com", "viejo@correo.com"}


def test_apply_keeps_match_deletes_rest_and_creates_test_users(session):
    keep = add_user(session, "Sofía Cubero", "soficubero@correo.com", UserRole.ADMIN.value)
    old = add_user(session, "Viejo", "viejo@correo.com")
    ticket = Ticket(
        title="Ticket asignado", description="x", category="Red",
        priority="Alta", assigned_to_id=old.id, created_by_id=old.id,
    )
    session.add(ticket)
    session.commit()
    session.add(History(ticket_id=ticket.id, action="created", author="Viejo", author_id=old.id))
    session.commit()

    reset_users(session, "SOFICUBERO", password="clave-nueva", apply=True)

    expected = {"soficubero@correo.com"} | {email for _, email in TEST_USERS.values()}
    assert emails(session) == expected
    assert session.get(User, keep.id).role == UserRole.ADMIN.value
    session.expire_all()
    stored = session.get(Ticket, ticket.id)
    assert stored.assigned_to_id is None and stored.created_by_id is None
    entry = session.scalars(select(History)).one()
    assert entry.author == "Viejo" and entry.author_id is None
    for role, (_, email) in TEST_USERS.items():
        user = session.scalar(select(User).where(User.email == email))
        assert user.role == role.value and user.is_active
        assert verify_password("clave-nueva", user.password_hash)


def test_rerun_resets_password_without_duplicates(session):
    add_user(session, "Sofía Cubero", "soficubero@correo.com")
    reset_users(session, "soficubero", password="primera", apply=True)
    reset_users(session, "soficubero", password="segunda", apply=True)

    assert len(emails(session)) == 1 + len(TEST_USERS)
    admin = session.scalar(select(User).where(User.email == "admin@ticketera.local"))
    assert verify_password("segunda", admin.password_hash)


def test_aborts_when_nobody_matches(session):
    add_user(session, "Viejo", "viejo@correo.com")
    with pytest.raises(ValueError):
        reset_users(session, "soficubero", apply=True)
    assert emails(session) == {"viejo@correo.com"}
