"""Tests for the ticket state machine (Task 18: RF3).

Forward to any later state, even skipping steps (``Nuevo → Cerrado``); the
only move back is reopening ``Resuelto``/``Cerrado → En proceso``. An optional
``motivo`` is saved as a comment of the ticket.
"""

from datetime import datetime

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Ticket

VALID_TICKET = {
    "title": "Ticket con máquina de estados",
    "description": "Descripción del ticket usado para probar RF3.",
    "category": TicketCategory.HARDWARE.value,
    "priority": TicketPriority.HIGH.value,
}
WORKFLOW = [
    TicketState.NEW.value,
    TicketState.IN_PROGRESS.value,
    TicketState.RESOLVED.value,
    TicketState.CLOSED.value,
]

# The linear forward steps (used to walk a ticket through the workflow).
LINEAR_STEPS = [
    (TicketState.NEW.value, TicketState.IN_PROGRESS.value),
    (TicketState.IN_PROGRESS.value, TicketState.RESOLVED.value),
    (TicketState.RESOLVED.value, TicketState.CLOSED.value),
]

# Every allowed transition: forward (also skipping steps) and reopening.
ALLOWED_TRANSITIONS = LINEAR_STEPS + [
    (TicketState.NEW.value, TicketState.RESOLVED.value),  # jump
    (TicketState.NEW.value, TicketState.CLOSED.value),  # jump
    (TicketState.IN_PROGRESS.value, TicketState.CLOSED.value),  # jump
    (TicketState.RESOLVED.value, TicketState.IN_PROGRESS.value),  # reopen
    (TicketState.CLOSED.value, TicketState.IN_PROGRESS.value),  # reopen
]

# Back to Nuevo, other moves back and repeated states.
REJECTED_TRANSITIONS = [
    (TicketState.IN_PROGRESS.value, TicketState.NEW.value),
    (TicketState.RESOLVED.value, TicketState.NEW.value),
    (TicketState.CLOSED.value, TicketState.NEW.value),
    (TicketState.CLOSED.value, TicketState.RESOLVED.value),
    (TicketState.NEW.value, TicketState.NEW.value),
    (TicketState.IN_PROGRESS.value, TicketState.IN_PROGRESS.value),
    (TicketState.RESOLVED.value, TicketState.RESOLVED.value),
    (TicketState.CLOSED.value, TicketState.CLOSED.value),
]


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def change_state(auth_client, ticket_id: int, state: str, motivo: str | None = None):
    payload = {"state": state} if motivo is None else {"state": state, "motivo": motivo}
    return auth_client.patch(f"/api/tickets/{ticket_id}/state", json=payload)


def advance_to(auth_client, ticket_id: int, state: str) -> None:
    """Drive a ticket forward through the allowed transitions until it
    reaches ``state`` (used to set up a given starting point)."""
    current = auth_client.get(f"/api/tickets/{ticket_id}").json()["state"]
    while current != state:
        assert WORKFLOW.index(current) < WORKFLOW.index(state), (
            f"cannot advance from {current} to {state}"
        )
        next_state = WORKFLOW[WORKFLOW.index(current) + 1]
        response = change_state(auth_client, ticket_id, next_state)
        assert response.status_code == 200
        current = next_state


def history_of(auth_client, ticket_id: int) -> list[dict]:
    response = auth_client.get(f"/api/tickets/{ticket_id}/history")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


def test_allowed_transitions_update_the_state(auth_client, session):
    for current, target in ALLOWED_TRANSITIONS:
        ticket = create_ticket(auth_client, title=f"Ticket {current} a {target}")
        advance_to(auth_client, ticket["id"], current)

        response = change_state(auth_client, ticket["id"], target)

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == target
        assert data["id"] == ticket["id"]
        stored = session.get(Ticket, ticket["id"])
        assert stored.state == target


def test_allowed_transition_returns_the_updated_ticket_shape(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.IN_PROGRESS.value)

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
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
    assert data["state"] == TicketState.IN_PROGRESS.value


# ---------------------------------------------------------------------------
# Rejected transitions
# ---------------------------------------------------------------------------


def test_rejected_transitions_answer_409_and_change_nothing(auth_client):
    for current, target in REJECTED_TRANSITIONS:
        ticket = create_ticket(auth_client, title=f"Rechazo de {current} a {target}")
        advance_to(auth_client, ticket["id"], current)
        entries_before = len(history_of(auth_client, ticket["id"]))

        response = change_state(auth_client, ticket["id"], target)

        assert response.status_code == 409, (current, target)
        detail = response.json()["detail"]
        assert detail == f"Transición de '{current}' a '{target}' no permitida"
        assert auth_client.get(f"/api/tickets/{ticket['id']}").json()["state"] == current
        # A rejected transition never reaches the history table.
        assert len(history_of(auth_client, ticket["id"])) == entries_before


def test_cerrado_only_reopens_to_en_proceso(auth_client):
    ticket = create_ticket(auth_client)
    advance_to(auth_client, ticket["id"], TicketState.CLOSED.value)

    for target in (TicketState.NEW.value, TicketState.RESOLVED.value, TicketState.CLOSED.value):
        response = change_state(auth_client, ticket["id"], target)
        assert response.status_code == 409
        assert "no permitida" in response.json()["detail"]

    response = change_state(auth_client, ticket["id"], TicketState.IN_PROGRESS.value)
    assert response.status_code == 200
    assert response.json()["state"] == TicketState.IN_PROGRESS.value


def test_reopened_ticket_can_be_resolved_and_closed_again(auth_client):
    ticket = create_ticket(auth_client)
    for target in ("Resuelto", "En proceso", "Cerrado", "En proceso", "Resuelto", "Cerrado"):
        assert change_state(auth_client, ticket["id"], target).status_code == 200, target

    states = [
        (e["old_value"], e["new_value"])
        for e in history_of(auth_client, ticket["id"])
        if e["action"] == "Cambio de estado"
    ]
    assert states == [
        ("Nuevo", "Resuelto"), ("Resuelto", "En proceso"), ("En proceso", "Cerrado"),
        ("Cerrado", "En proceso"), ("En proceso", "Resuelto"), ("Resuelto", "Cerrado"),
    ]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_state_change_on_missing_ticket_returns_404(auth_client):
    response = change_state(auth_client, 999, TicketState.IN_PROGRESS.value)

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket 999 no encontrado"


def test_unknown_state_value_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], "Pendiente")

    assert response.status_code == 422
    # The ticket is untouched: FastAPI rejects the payload before the route.
    assert auth_client.get(f"/api/tickets/{ticket['id']}").json()["state"] == "Nuevo"


def test_missing_state_field_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.patch(f"/api/tickets/{ticket['id']}/state", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_successful_transition_records_exactly_one_history_entry(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.IN_PROGRESS.value)

    assert response.status_code == 200
    entries = history_of(auth_client, ticket["id"])
    # Ticket creation adds one entry, state change adds one more.
    assert len(entries) == 2


def test_history_entry_describes_the_state_change(auth_client):
    ticket = create_ticket(auth_client)

    change_state(auth_client, ticket["id"], TicketState.IN_PROGRESS.value)

    entries = history_of(auth_client, ticket["id"])
    # Entries are: creation first, then state change.
    assert len(entries) == 2
    # The state change entry should be the second one.
    assert entries[0]["action"] == "created"
    assert entries[1]["action"] == "Cambio de estado"
    assert entries[1]["field"] == "state"
    assert entries[1]["old_value"] == TicketState.NEW.value
    assert entries[1]["new_value"] == TicketState.IN_PROGRESS.value
    # Signed by the authenticated user that performed the change (auth_client
    # registers "Test Admin").
    assert entries[1]["author"] == "Test Admin"
    assert entries[1]["author_id"] is not None


def test_full_workflow_records_history_in_chronological_order(auth_client):
    ticket = create_ticket(auth_client)

    for _, target in LINEAR_STEPS:
        assert change_state(auth_client, ticket["id"], target).status_code == 200

    entries = history_of(auth_client, ticket["id"])
    # Ticket creation adds one entry, 3 state transitions add 3 more: total 4.
    assert len(entries) == 4
    # First entry is creation, rest are state changes in order.
    assert [entry["action"] for entry in entries] == ["created"] + [ "Cambio de estado" ] * 3


def test_jump_records_one_entry_from_the_old_to_the_new_state(auth_client):
    ticket = create_ticket(auth_client)

    assert change_state(auth_client, ticket["id"], TicketState.CLOSED.value).status_code == 200

    entries = history_of(auth_client, ticket["id"])
    assert [e["action"] for e in entries] == ["created", "Cambio de estado"]
    assert (entries[1]["old_value"], entries[1]["new_value"]) == ("Nuevo", "Cerrado")


def test_rejected_transition_records_no_history(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.NEW.value)

    assert response.status_code == 409
    # Ticket creation adds one entry; rejected transition adds none.
    entries = history_of(auth_client, ticket["id"])
    assert len(entries) == 1
    assert entries[0]["action"] == "created"


# ---------------------------------------------------------------------------
# updated_at
# ---------------------------------------------------------------------------


def test_updated_at_changes_after_a_valid_transition(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.IN_PROGRESS.value)

    assert response.status_code == 200
    assert datetime.fromisoformat(
        response.json()["updated_at"]
    ) > datetime.fromisoformat(ticket["updated_at"])


def test_updated_at_is_untouched_by_a_rejected_transition(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.NEW.value)

    assert response.status_code == 409
    assert auth_client.get(f"/api/tickets/{ticket['id']}").json()["updated_at"] == (
        ticket["updated_at"]
    )


# ---------------------------------------------------------------------------
# Motivo (optional comment)
# ---------------------------------------------------------------------------


def comments_of(auth_client, ticket_id: int) -> list[dict]:
    response = auth_client.get(f"/api/tickets/{ticket_id}/comments")
    assert response.status_code == 200
    return response.json()


def test_motivo_is_saved_as_a_comment_with_its_history_entry(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(
        auth_client, ticket["id"], TicketState.CLOSED.value, "  Ya no se va a hacer.  "
    )

    assert response.status_code == 200
    comments = comments_of(auth_client, ticket["id"])
    assert [(c["author"], c["content"]) for c in comments] == [
        ("Test Admin", "Ya no se va a hacer.")
    ]
    entries = history_of(auth_client, ticket["id"])
    assert [e["action"] for e in entries] == ["created", "Cambio de estado", "commented"]
    assert entries[2]["new_value"] == "Ya no se va a hacer."
    assert entries[2]["author"] == "Test Admin"


def test_blank_or_missing_motivo_adds_no_comment(auth_client):
    ticket = create_ticket(auth_client)

    assert change_state(auth_client, ticket["id"], "En proceso", "   ").status_code == 200
    assert change_state(auth_client, ticket["id"], "Cerrado").status_code == 200

    assert comments_of(auth_client, ticket["id"]) == []
    assert "commented" not in [e["action"] for e in history_of(auth_client, ticket["id"])]


def test_rejected_transition_does_not_save_the_motivo(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.NEW.value, "Motivo")

    assert response.status_code == 409
    assert comments_of(auth_client, ticket["id"]) == []


def test_too_long_motivo_returns_422_and_changes_nothing(auth_client):
    ticket = create_ticket(auth_client)

    response = change_state(auth_client, ticket["id"], TicketState.CLOSED.value, "x" * 2001)

    assert response.status_code == 422
    assert auth_client.get(f"/api/tickets/{ticket['id']}").json()["state"] == "Nuevo"
