"""Tests for ticket assignment and unassignment (Task 8: RF4)."""

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole
from backend.models import Ticket, User

VALID_USER = {
    "name": "Ana Pérez",
    "email": "ana@soporte.local",
    "role": UserRole.SUPPORT.value,
}
VALID_TICKET = {
    "title": "Ticket para asignar",
    "description": "Descripción del ticket que será asignado.",
    "category": TicketCategory.INCIDENT.value,
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
    "created_at",
    "updated_at",
}


def create_user(client, **overrides) -> dict:
    payload = {**VALID_USER, **overrides}
    response = client.post("/api/users", json=payload)
    assert response.status_code == 201
    return response.json()


def create_ticket(client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def test_assign_ticket_returns_200(client):
    user = create_user(client)
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    assert response.status_code == 200


def test_assign_stores_assigned_to_id(client):
    user = create_user(client)
    ticket = create_ticket(client)

    data = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert data["assigned_to_id"] == user["id"]


def test_assignment_persists_in_sqlite(client, engine):
    user = create_user(client)
    ticket = create_ticket(client)

    client.patch(
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


def test_assign_to_missing_user_returns_404(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": 9999},
    )

    assert response.status_code == 404


def test_assign_to_missing_ticket_returns_404(client):
    user = create_user(client)

    response = client.patch(
        "/api/tickets/9999/assign",
        json={"assigned_to_id": user["id"]},
    )

    assert response.status_code == 404


def test_assign_without_field_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(f"/api/tickets/{ticket['id']}/assign", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Unassignment
# ---------------------------------------------------------------------------

def test_unassign_with_null_returns_200(client):
    user = create_user(client)
    ticket = create_ticket(client)
    client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    response = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["assigned_to_id"] is None


def test_unassignment_persists_in_sqlite(client, engine):
    user = create_user(client)
    ticket = create_ticket(client)
    client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    )

    client.patch(
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

def test_assign_does_not_change_other_ticket_fields(client):
    user = create_user(client)
    ticket = create_ticket(client)

    data = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert data["title"] == ticket["title"]
    assert data["description"] == ticket["description"]
    assert data["category"] == ticket["category"]
    assert data["priority"] == ticket["priority"]
    assert data["state"] == TicketState.NEW.value
    assert data["created_at"] == ticket["created_at"]


def test_assign_updates_updated_at(client):
    user = create_user(client)
    ticket = create_ticket(client)

    data = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert datetime.fromisoformat(data["updated_at"]) > datetime.fromisoformat(
        ticket["updated_at"]
    )


def test_assign_response_structure(client):
    user = create_user(client)
    ticket = create_ticket(client)

    data = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user["id"]},
    ).json()

    assert set(data.keys()) == TICKET_RESPONSE_KEYS
    assert isinstance(data["assigned_to_id"], int)


def test_assignment_endpoints_are_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/users" in schema["paths"]
    assert "/api/tickets/{ticket_id}/assign" in schema["paths"]
    assert "patch" in schema["paths"]["/api/tickets/{ticket_id}/assign"]
