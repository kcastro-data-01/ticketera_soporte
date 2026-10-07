"""Tests for ticket creation (Task 4), listing (Task 5) and edition (Task 6)."""

from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Ticket

VALID_PAYLOAD = {
    "title": "No enciende la impresora",
    "description": "La impresora del piso 2 no responde desde ayer.",
    "category": TicketCategory.INCIDENT.value,
    "priority": TicketPriority.HIGH.value,
}


# ---------------------------------------------------------------------------
# Successful creation
# ---------------------------------------------------------------------------

def test_create_ticket_returns_201(client):
    response = client.post("/api/tickets", json=VALID_PAYLOAD)

    assert response.status_code == 201


def test_create_ticket_response_contains_sent_data(client):
    response = client.post("/api/tickets", json=VALID_PAYLOAD)
    data = response.json()

    assert data["title"] == VALID_PAYLOAD["title"]
    assert data["description"] == VALID_PAYLOAD["description"]
    assert data["category"] == VALID_PAYLOAD["category"]
    assert data["priority"] == VALID_PAYLOAD["priority"]
    assert data["id"] is not None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_ticket_is_persisted_in_sqlite(client, engine):
    response = client.post("/api/tickets", json=VALID_PAYLOAD)
    ticket_id = response.json()["id"]

    # Read through a brand new session to prove the row is really stored.
    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.get(Ticket, ticket_id)
        assert stored is not None
        assert stored.title == VALID_PAYLOAD["title"]
        assert stored.category == VALID_PAYLOAD["category"]
        assert stored.priority == VALID_PAYLOAD["priority"]
        assert fresh_session.query(Ticket).count() == 1
    finally:
        fresh_session.close()


def test_initial_state_is_the_new_value_from_constants(client):
    response = client.post("/api/tickets", json=VALID_PAYLOAD)

    assert response.json()["state"] == TicketState.NEW.value


def test_create_ticket_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/tickets" in schema["paths"]
    assert "post" in schema["paths"]["/api/tickets"]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_create_ticket_without_title_returns_422(client):
    payload = {key: value for key, value in VALID_PAYLOAD.items() if key != "title"}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


def test_create_ticket_without_description_returns_422(client):
    payload = {key: value for key, value in VALID_PAYLOAD.items() if key != "description"}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("invalid_title", ["", "  ", "ab"])
def test_create_ticket_with_invalid_title_returns_422(client, invalid_title):
    payload = {**VALID_PAYLOAD, "title": invalid_title}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


def test_create_ticket_with_blank_description_returns_422(client):
    payload = {**VALID_PAYLOAD, "description": "   "}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


def test_create_ticket_with_invalid_category_returns_422(client):
    payload = {**VALID_PAYLOAD, "category": "Categoría inventada"}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


def test_create_ticket_with_invalid_priority_returns_422(client):
    payload = {**VALID_PAYLOAD, "priority": "Urgentísima"}

    response = client.post("/api/tickets", json=payload)

    assert response.status_code == 422


def test_invalid_payload_does_not_persist_anything(client, engine):
    payload = {**VALID_PAYLOAD, "category": "Categoría inventada"}

    client.post("/api/tickets", json=payload)

    fresh_session = sessionmaker(bind=engine)()
    try:
        assert fresh_session.query(Ticket).count() == 0
    finally:
        fresh_session.close()


def test_create_ticket_stores_trimmed_title(client):
    payload = {**VALID_PAYLOAD, "title": "  No enciende la impresora  "}

    response = client.post("/api/tickets", json=payload)

    assert response.json()["title"] == "No enciende la impresora"


# ---------------------------------------------------------------------------
# Listing (Task 5: GET /api/tickets)
# ---------------------------------------------------------------------------

EXPECTED_TICKET_KEYS = {
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


def test_list_tickets_returns_200_with_empty_list(client):
    response = client.get("/api/tickets")

    assert response.status_code == 200
    assert response.json() == []


def test_list_tickets_returns_created_tickets(client):
    first = client.post("/api/tickets", json=VALID_PAYLOAD).json()
    second = client.post(
        "/api/tickets",
        json={**VALID_PAYLOAD, "title": "Segundo ticket de prueba"},
    ).json()

    response = client.get("/api/tickets")

    assert response.status_code == 200
    returned_ids = {ticket["id"] for ticket in response.json()}
    assert returned_ids == {first["id"], second["id"]}


def test_list_tickets_data_matches_stored_records(client, engine):
    created = client.post("/api/tickets", json=VALID_PAYLOAD).json()

    response = client.get("/api/tickets")
    data = response.json()

    # Compare with a brand new session reading the SQLite file directly.
    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.get(Ticket, created["id"])
        assert stored is not None
        assert data[0]["id"] == stored.id
        assert data[0]["title"] == stored.title
        assert data[0]["description"] == stored.description
        assert data[0]["category"] == stored.category
        assert data[0]["priority"] == stored.priority
        assert data[0]["state"] == stored.state
        assert data[0]["assigned_to_id"] == stored.assigned_to_id
    finally:
        fresh_session.close()


def test_list_tickets_response_structure(client):
    client.post("/api/tickets", json=VALID_PAYLOAD)

    data = client.get("/api/tickets").json()

    assert len(data) == 1
    ticket = data[0]
    assert set(ticket.keys()) == EXPECTED_TICKET_KEYS
    assert isinstance(ticket["id"], int)
    assert isinstance(ticket["title"], str)
    assert isinstance(ticket["category"], str)
    assert isinstance(ticket["priority"], str)
    assert isinstance(ticket["state"], str)
    assert ticket["assigned_to_id"] is None


def test_list_tickets_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/tickets" in schema["paths"]
    assert "get" in schema["paths"]["/api/tickets"]


def test_list_tickets_does_not_modify_stored_data(client, engine):
    client.post("/api/tickets", json=VALID_PAYLOAD)

    def snapshot() -> tuple:
        fresh_session = sessionmaker(bind=engine)()
        try:
            ticket = fresh_session.query(Ticket).one()
            return (
                fresh_session.query(Ticket).count(),
                ticket.title,
                ticket.description,
                ticket.category,
                ticket.priority,
                ticket.state,
                ticket.created_at,
                ticket.updated_at,
            )
        finally:
            fresh_session.close()

    before = snapshot()
    response = client.get("/api/tickets")
    after = snapshot()

    assert response.status_code == 200
    assert before == after


# ---------------------------------------------------------------------------
# Edition (Task 6: PATCH /api/tickets/{ticket_id})
# ---------------------------------------------------------------------------

def create_ticket(client, **overrides) -> dict:
    """Helper: create a ticket and return its response body."""
    payload = {**VALID_PAYLOAD, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def test_patch_existing_ticket_returns_200(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Título actualizado"},
    )

    assert response.status_code == 200


def test_patch_updates_only_title(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Solo cambia el título"},
    )
    data = response.json()

    assert data["title"] == "Solo cambia el título"
    assert data["description"] == ticket["description"]
    assert data["category"] == ticket["category"]
    assert data["priority"] == ticket["priority"]


def test_patch_updates_only_description(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"description": "Solo cambia la descripción."},
    )
    data = response.json()

    assert data["description"] == "Solo cambia la descripción."
    assert data["title"] == ticket["title"]
    assert data["category"] == ticket["category"]
    assert data["priority"] == ticket["priority"]


def test_patch_updates_only_category(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"category": TicketCategory.REQUEST.value},
    )
    data = response.json()

    assert data["category"] == TicketCategory.REQUEST.value
    assert data["title"] == ticket["title"]
    assert data["description"] == ticket["description"]
    assert data["priority"] == ticket["priority"]


def test_patch_updates_only_priority(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"priority": TicketPriority.LOW.value},
    )
    data = response.json()

    assert data["priority"] == TicketPriority.LOW.value
    assert data["title"] == ticket["title"]
    assert data["description"] == ticket["description"]
    assert data["category"] == ticket["category"]


def test_patch_updates_multiple_fields_at_once(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={
            "title": "Título y prioridad cambiados",
            "priority": TicketPriority.CRITICAL.value,
        },
    )
    data = response.json()

    assert data["title"] == "Título y prioridad cambiados"
    assert data["priority"] == TicketPriority.CRITICAL.value
    assert data["description"] == ticket["description"]
    assert data["category"] == ticket["category"]


def test_patch_persists_changes_in_sqlite(client, engine):
    ticket = create_ticket(client)

    client.patch(f"/api/tickets/{ticket['id']}", json={"title": "Persistido en disco"})

    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.get(Ticket, ticket["id"])
        assert stored is not None
        assert stored.title == "Persistido en disco"
    finally:
        fresh_session.close()


def test_patch_missing_ticket_returns_404(client):
    response = client.patch("/api/tickets/9999", json={"title": "Este no existe"})

    assert response.status_code == 404


def test_patch_invalid_title_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(f"/api/tickets/{ticket['id']}", json={"title": "ab"})

    assert response.status_code == 422


def test_patch_blank_description_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(f"/api/tickets/{ticket['id']}", json={"description": "   "})

    assert response.status_code == 422


def test_patch_invalid_category_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"category": "Categoría inventada"},
    )

    assert response.status_code == 422


def test_patch_invalid_priority_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"priority": "Urgentísima"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{}, {"title": None}])
def test_patch_without_modifiable_fields_returns_422(client, payload):
    ticket = create_ticket(client)

    response = client.patch(f"/api/tickets/{ticket['id']}", json=payload)

    assert response.status_code == 422


def test_patch_cannot_modify_protected_fields(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={
            "title": "Título nuevo",
            "id": 999,
            "state": TicketState.CLOSED.value,
            "assigned_to_id": 42,
            "created_at": "2000-01-01T00:00:00",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["id"] == ticket["id"]
    assert data["state"] == TicketState.NEW.value
    assert data["assigned_to_id"] is None
    assert data["created_at"] == ticket["created_at"]


def test_patch_with_only_protected_fields_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={
            "state": TicketState.CLOSED.value,
            "assigned_to_id": 1,
            "id": 7,
            "created_at": "2000-01-01T00:00:00",
        },
    )

    assert response.status_code == 422


def test_patch_updates_updated_at(client):
    ticket = create_ticket(client)

    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "El título también cambia updated_at"},
    )
    data = response.json()

    assert response.status_code == 200
    assert datetime.fromisoformat(data["updated_at"]) > datetime.fromisoformat(
        ticket["updated_at"]
    )
    assert data["created_at"] == ticket["created_at"]
