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
