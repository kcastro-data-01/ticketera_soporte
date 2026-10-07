"""Tests for ticket creation (Task 4: RF1, RF2)."""

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
