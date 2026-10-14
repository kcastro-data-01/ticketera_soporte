"""Tests for the ticket history endpoint (Task 14: RF9, read-only)."""

from datetime import datetime, timezone

from backend.constants import TicketCategory, TicketPriority
from backend.models import History

VALID_TICKET = {
    "title": "Ticket con historial",
    "description": "Descripción del ticket consultado en su historial.",
    "category": TicketCategory.SOFTWARE.value,
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
    "author_id",
    "created_at",
}


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
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


def test_history_returns_empty_list_for_ticket_without_entries(auth_client):
    """After creating a ticket, one history entry (creation) exists by default."""

    ticket = create_ticket(auth_client)

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "created"


def test_history_returns_404_for_missing_ticket(auth_client):
    response = auth_client.get("/api/tickets/999/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket 999 no encontrado"


def test_history_returns_entries_oldest_first(auth_client, session):
    ticket = create_ticket(auth_client)
    # The ticket creation adds a "created" entry with current timestamp.
    # Add an "assigned" entry with an earlier timestamp.
    add_history(
        session,
        ticket["id"],
        utc(2026, 10, 7, 10, 0),  # earlier than creation
        action="assigned",
        field="assigned_to_id",
        new_value="1",
    )

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    entries = response.json()
    # Oldest first: assigned (10:00) before creation (current time).
    assert [entry["action"] for entry in entries] == ["assigned", "created"]


def test_history_exposes_the_model_fields_with_null_optionals(auth_client, session):
    ticket = create_ticket(auth_client)
    # The ticket creation already adds a "created" entry (RF9).
    # No need to add another one here.
    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    entry = response.json()[0]
    assert set(entry) == HISTORY_KEYS
    assert entry["ticket_id"] == ticket["id"]
    assert entry["action"] == "created"
    assert entry["field"] is None
    assert entry["old_value"] is None
    assert entry["new_value"] is None
    # The creation entry is signed by the authenticated user (auth_client
    # registers "Test Admin"), never by "Anónimo".
    assert entry["author"] == "Test Admin"
    assert entry["author_id"] is not None
    assert entry["created_at"].startswith("2026-")


def test_history_entry_describes_the_change_when_available(auth_client, session):
    ticket = create_ticket(auth_client)
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

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    entry = response.json()[0]
    assert entry["action"] == "updated"
    assert entry["field"] == "priority"
    assert entry["old_value"] == "Baja"
    assert entry["new_value"] == "Alta"
    assert entry["author"] == "Ana"


def test_legacy_history_rows_keep_working_without_author(auth_client, session):
    """Registros antiguos sin usuario (author NULL, author_id NULL) se
    devuelven tal cual: la UI los muestra como "Sistema". """

    ticket = create_ticket(auth_client)
    add_history(
        session,
        ticket["id"],
        utc(2026, 10, 6, 9, 0),
        action="updated",
        field="priority",
        old_value="Baja",
        new_value="Alta",
        author=None,
        author_id=None,
    )

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    legacy = [e for e in response.json() if e["created_at"].startswith("2026-10-06")]
    assert len(legacy) == 1
    assert legacy[0]["author"] is None
    assert legacy[0]["author_id"] is None


def test_every_write_action_records_the_authenticated_author(auth_client):
    """Creación, edición, asignación, cambio de estado y comentario firman
    el historial con el usuario autenticado (no "Anónimo")."""

    ticket = create_ticket(auth_client)

    edited = auth_client.patch(
        f"/api/tickets/{ticket['id']}", json={"priority": "Alta"}
    )
    assert edited.status_code == 200

    other_user = auth_client.post(
        "/api/users",
        json={"name": "Ana Pérez", "email": "ana-auditoria@test.local"},
    )
    assert other_user.status_code == 201

    assigned = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": other_user.json()["id"]},
    )
    assert assigned.status_code == 200

    changed = auth_client.patch(
        f"/api/tickets/{ticket['id']}/state",
        json={"state": "En proceso"},
    )
    assert changed.status_code == 200

    commented = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario firmado por el usuario autenticado."},
    )
    assert commented.status_code == 201

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")
    entries = response.json()
    actions = [e["action"] for e in entries]
    assert actions == ["created", "updated", "assigned", "Cambio de estado", "commented"]
    for entry in entries:
        assert entry["author"] == "Test Admin"
        assert entry["author"] != "Anónimo"
        assert entry["author_id"] is not None


def test_history_does_not_include_entries_of_other_tickets(auth_client, session):
    ticket = create_ticket(auth_client)
    other_ticket = create_ticket(auth_client, title="Otro ticket sin historial")
    # Each ticket now has its own creation entry (RF9). Check that entries
    # are per-ticket and don't cross-contaminate.
    add_history(session, other_ticket["id"], utc(2026, 10, 7, 10, 0), action="created")

    response = auth_client.get(f"/api/tickets/{ticket['id']}/history")

    assert response.status_code == 200
    # This ticket has its own creation entry; the other ticket's entries
    # are separate.
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["ticket_id"] == ticket["id"]
