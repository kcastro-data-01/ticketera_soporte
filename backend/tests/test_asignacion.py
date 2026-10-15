"""Tests for ticket assignment and unassignment (Task 8: RF4)."""

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole
from backend.models import Ticket, User

VALID_USER = {
    "name": "Ana Pérez",
    "email": "ana@soporte.local",
    "role": UserRole.TECHNICIAN.value,
}
VALID_TICKET = {
    "title": "Ticket para asignar",
    "description": "Descripción del ticket que será asignado.",
    "category": TicketCategory.HARDWARE.value,
    "priority": TicketPriority.HIGH.value,
}
TICKET_RESPONSE_KEYS = {
    "id",
    "title",
    "description",
    "category",
    "priority",
    "state",
    "assigned_to_id",
    "created_by_id",
    "created_at",
    "updated_at",
}


def create_user(auth_client, **overrides) -> dict:
    payload = {**VALID_USER, **overrides}
    response = auth_client.post("/api/users", json=payload)
    assert response.status_code == 201
    return response.json()


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def test_assign_ticket_returns_200(auth_client):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)

    response = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    assert response.status_code == 200


def test_assign_stores_assigned_to_id(auth_client):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)

    data = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert data["assigned_to_id"] == user["id"]


def test_assignment_persists_in_sqlite(auth_client, engine):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)

    auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.get(Ticket, ticket["id"])
        assert stored.assigned_to_id == user["id"]
        assignee = fresh_session.get(User, user["id"])
        assert assignee is not None
    finally:
        fresh_session.close()


def test_assign_to_missing_user_returns_404(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": 9999},
    )

    assert response.status_code == 404


def test_assign_to_missing_ticket_returns_404(auth_client):
    user = create_user(auth_client)

    response = auth_client.patch(
        "/api/tickets/9999/assign",
        json={"assigned_to_id": user["id"]},
    )

    assert response.status_code == 404


def test_assign_without_field_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.patch(f"/api/tickets/{ticket['id']}/assign", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Unassignment
# ---------------------------------------------------------------------------

def test_unassign_with_null_returns_200(auth_client):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)
    auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    response = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["assigned_to_id"] is None


def test_unassignment_persists_in_sqlite(auth_client, engine):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)
    auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
    )

    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.get(Ticket, ticket["id"])
        assert stored.assigned_to_id is None
    finally:
        fresh_session.close()


# ---------------------------------------------------------------------------
# Side effects and structure
# ---------------------------------------------------------------------------

def test_assign_does_not_change_other_ticket_fields(auth_client):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)

    data = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert data["title"] == ticket["title"]
    assert data["description"] == ticket["description"]
    assert data["category"] == ticket["category"]
    assert data["priority"] == ticket["priority"]
    assert data["state"] == TicketState.NEW.value
    assert data["created_at"] == ticket["created_at"]


def test_assign_updates_updated_at(auth_client):
    user = create_user(auth_client, name="Ana", email="ana@test.local")
    other = create_user(auth_client, name="Luis", email="luis@test.local")
    ticket = create_ticket(auth_client)

    # The ticket is auto-assigned to `user`; reassign to `other` to change it.
    data = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": other["id"]},
    ).json()

    assert datetime.fromisoformat(data["updated_at"]) > datetime.fromisoformat(
        ticket["updated_at"]
    )


def test_assign_response_structure(auth_client):
    user = create_user(auth_client)
    ticket = create_ticket(auth_client)

    data = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert set(data.keys()) == TICKET_RESPONSE_KEYS
    assert isinstance(data["assigned_to_id"], int)


def test_assignment_endpoints_are_exposed_in_openapi(auth_client):
    schema = auth_client.get("/openapi.json").json()

    assert "/api/users" in schema["paths"]
    assert "/api/tickets/{ticket_id}/assign" in schema["paths"]
    assert "patch" in schema["paths"]["/api/tickets/{ticket_id}/assign"]
