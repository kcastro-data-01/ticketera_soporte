"""Tests for the timezone handling of the dates exposed by the API (Task 20.2).

The API must always serialize timestamps with an explicit UTC offset. A
naive value (no offset) is interpreted by browsers as local time, which
shifted the hour shown to the user by the viewer's UTC offset (Costa Rica,
UTC-6: the UI displayed 16:49 instead of 10:49).
"""

from datetime import datetime, timedelta, timezone

from backend.constants import TicketCategory, TicketPriority, UserRole
from backend.models import Ticket

VALID_TICKET = {
    "title": "Ticket con fechas",
    "description": "Ticket usado para verificar el manejo de zona horaria.",
    "category": TicketCategory.INQUIRY.value,
    "priority": TicketPriority.MEDIUM.value,
}


def create_ticket(client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def parse_utc(value: str) -> datetime:
    """Parse an API timestamp and require an explicit, zero UTC offset."""
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"marca de tiempo sin desplazamiento: {value}"
    assert parsed.utcoffset() == timedelta(0), f"desplazamiento distinto de UTC: {value}"
    return parsed


# ---------------------------------------------------------------------------
# Explicit UTC offset in every response
# ---------------------------------------------------------------------------


def test_ticket_created_at_carries_explicit_utc_offset(client):
    ticket = create_ticket(client)

    parse_utc(ticket["created_at"])
    parse_utc(ticket["updated_at"])


def test_listed_tickets_carries_explicit_utc_offset(client):
    create_ticket(client)

    data = client.get("/api/tickets").json()

    assert len(data) == 1
    parse_utc(data[0]["created_at"])


def test_comment_created_at_carries_explicit_utc_offset(client):
    ticket = create_ticket(client)

    data = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario con fecha verificada."},
    ).json()

    parse_utc(data["created_at"])

    listed = client.get(f"/api/tickets/{ticket['id']}/comments").json()
    parse_utc(listed[0]["created_at"])


def test_history_created_at_carries_explicit_utc_offset(client):
    ticket = create_ticket(client)
    changed = client.patch(
        f"/api/tickets/{ticket['id']}/state",
        json={"state": "En proceso"},
    )
    assert changed.status_code == 200

    entries = client.get(f"/api/tickets/{ticket['id']}/history").json()

    assert len(entries) == 1
    parse_utc(entries[0]["created_at"])


def test_updated_at_carries_explicit_utc_offset_after_edit(client):
    ticket = create_ticket(client)

    updated = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Título actualizado para la fecha"},
    ).json()

    assert parse_utc(updated["updated_at"]) >= parse_utc(ticket["created_at"])


# ---------------------------------------------------------------------------
# No offset drift: the instant stored is the real UTC instant
# ---------------------------------------------------------------------------


def test_created_at_matches_current_utc_time(client):
    """Catches conversion bugs: a 6-hour shift fails this assertion."""
    before = datetime.now(timezone.utc)

    ticket = create_ticket(client)

    after = datetime.now(timezone.utc)
    created_at = parse_utc(ticket["created_at"])
    assert before - timedelta(seconds=60) <= created_at <= after + timedelta(seconds=60)


def test_orm_read_returns_aware_utc_datetime(client, session):
    ticket = create_ticket(client)

    stored = session.get(Ticket, ticket["id"])

    assert stored.created_at.tzinfo is not None
    assert stored.created_at.utcoffset() == timedelta(0)
    assert (
        abs((stored.created_at - datetime.now(timezone.utc)).total_seconds()) < 60
    )


def test_existing_naive_rows_are_read_as_utc(client, session):
    """Rows stored before the fix (bare wall time) are still returned as UTC."""
    ticket = create_ticket(client)
    session.execute(
        Ticket.__table__.update()
        .where(Ticket.__table__.c.id == ticket["id"])
        .values(created_at=datetime(2026, 10, 8, 16, 49, 56))
    )
    session.commit()
    session.expire_all()

    fetched = client.get(f"/api/tickets/{ticket['id']}").json()

    # Pydantic serializa UTC como "Z" (RFC 3339): sin ambigüedad para el navegador.
    assert fetched["created_at"] == "2026-10-08T16:49:56Z"


def test_user_role_values_still_spanish(client):
    """Guard: the timezone work must not alter the Spanish enums."""
    response = client.post(
        "/api/users",
        json={
            "name": "Persona de prueba",
            "email": "persona.prueba@example.com",
            "role": UserRole.SUPPORT.value,
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "Soporte"
