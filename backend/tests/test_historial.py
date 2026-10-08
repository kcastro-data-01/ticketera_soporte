"""Tests for the ticket history endpoint (Task 14: RF9, read-only)."""

from datetime import datetime, timezone

from backend.constants import TicketCategory, TicketPriority
from backend.models import History

VALID_TICKET = {
    "title": "Ticket con historial",
    "description": "Descripción del ticket consultado en su historial.",
    "category": TicketCategory.INQUIRY.value,
    "priority": TicketPriority.MEDIUM.value,
}
HISTORY_KEYS = {
    "id",
    "ticket_id",
    "action",
    "field",
    "old_value",
    "new_value",
    "author",
    "created_at",
}


def create_ticket(client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def add_history(session, ticket_id: int, created_at: datetime, **overrides) -> None:
    """Insert a history row directly (state changes are recorded by the API;
    other actions still have no writer and are inserted here)."""
    entry = History(
        ticket_id=ticket_id,
        action=overrides.pop("action", "created"),
        created_at=created_at,
        **overrides,
    )
    session.add(entry)
    session.commit()


def utc(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_history_returns_empty_list_for_ticket_without_entries(client):
    ticket = create_ticket(client)

    response = client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    assert response.json() == []


def test_history_returns_404_for_missing_ticket(client):
    response = client.get("/api/tickets/999/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket 999 no encontrado"


def test_history_returns_entries_oldest_first(client, session):
    ticket = create_ticket(client)
    add_history(
        session,
        ticket["id"],
        utc(2026, 10, 7, 10, 5),
        action="assigned",
        field="assigned_to_id",
        new_value="1",
    )
    add_history(session, ticket["id"], utc(2026, 10, 7, 10, 0), action="created")

    response = client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    entries = response.json()
    assert [entry["action"] for entry in entries] == ["created", "assigned"]


def test_history_exposes_the_model_fields_with_null_optionals(client, session):
    ticket = create_ticket(client)
    add_history(session, ticket["id"], utc(2026, 10, 7, 10, 0), action="created")

    response = client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    entry = response.json()[0]
    assert set(entry) == HISTORY_KEYS
    assert entry["ticket_id"] == ticket["id"]
    assert entry["action"] == "created"
    assert entry["field"] is None
    assert entry["old_value"] is None
    assert entry["new_value"] is None
    assert entry["author"] is None
    assert entry["created_at"].startswith("2026-10-07T10:00:00")


def test_history_entry_describes_the_change_when_available(client, session):
    ticket = create_ticket(client)
    add_history(
        session,
        ticket["id"],
        utc(2026, 10, 7, 11, 0),
        action="updated",
        field="priority",
        old_value="Baja",
        new_value="Alta",
        author="Ana",
    )

    response = client.get(f"/api/tickets/{ticket['id']}/history")

    entry = response.json()[0]
    assert entry["action"] == "updated"
    assert entry["field"] == "priority"
    assert entry["old_value"] == "Baja"
    assert entry["new_value"] == "Alta"
    assert entry["author"] == "Ana"


def test_history_does_not_include_entries_of_other_tickets(client, session):
    ticket = create_ticket(client)
    other_ticket = create_ticket(client, title="Otro ticket sin historial")
    add_history(session, other_ticket["id"], utc(2026, 10, 7, 10, 0), action="created")

    response = client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    assert response.json() == []
