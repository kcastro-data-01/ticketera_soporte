"""Tests for the global history endpoint (read-only, across all tickets)."""

from datetime import datetime, timezone

from backend.constants import TicketCategory, TicketPriority
from backend.models import History

VALID_TICKET = {
    "title": "Ticket para historial global",
    "description": "Descripción del ticket usado en las pruebas de historial global.",
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


def test_global_history_returns_empty_list_when_no_entries(client):
    response = client.get("/api/history")

    assert response.status_code == 200
    assert response.json() == []


def test_global_history_returns_entries_newest_first(client, session):
    ticket = create_ticket(client)
    add_history(session, ticket["id"], utc(2026, 10, 7, 10, 0), action="created")
    add_history(session, ticket["id"], utc(2026, 10, 7, 10, 5), action="assigned")

    response = client.get("/api/history")

    assert response.status_code == 200
    entries = response.json()
    assert [e["action"] for e in entries] == ["assigned", "created"]


def test_global_history_includes_entries_from_multiple_tickets(client, session):
    ticket_a = create_ticket(client, title="Ticket A")
    ticket_b = create_ticket(client, title="Ticket B")
    add_history(session, ticket_a["id"], utc(2026, 10, 7, 9, 0), action="created")
    add_history(session, ticket_b["id"], utc(2026, 10, 7, 11, 0), action="created")

    response = client.get("/api/history")

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
    ticket_ids = {e["ticket_id"] for e in entries}
    assert ticket_ids == {ticket_a["id"], ticket_b["id"]}


def test_global_history_exposes_the_model_fields(client, session):
    ticket = create_ticket(client)
    add_history(session, ticket["id"], utc(2026, 10, 7, 10, 0), action="created")

    response = client.get("/api/history")

    assert response.status_code == 200
    entry = response.json()[0]
    assert set(entry) == HISTORY_KEYS
    assert entry["ticket_id"] == ticket["id"]
    assert entry["action"] == "created"
    assert entry["field"] is None
    assert entry["old_value"] is None
    assert entry["new_value"] is None
    assert entry["author"] is None


def test_global_history_entry_describes_change_when_available(client, session):
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

    response = client.get("/api/history")

    entry = response.json()[0]
    assert entry["action"] == "updated"
    assert entry["field"] == "priority"
    assert entry["old_value"] == "Baja"
    assert entry["new_value"] == "Alta"
    assert entry["author"] == "Ana"


def test_global_history_is_read_only(client):
    response = client.get("/api/history")

    assert response.status_code == 200
    # The endpoint only accepts GET; other methods should be rejected.
    assert client.post("/api/history").status_code == 405
    assert client.patch("/api/history").status_code == 405
    assert client.delete("/api/history").status_code == 405
