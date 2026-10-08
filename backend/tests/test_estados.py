"""Tests for the ticket state machine (Task 18: RF3).

Allowed transitions are the forward linear moves only:
``Nuevo → En proceso → Resuelto → Cerrado`` (``Cerrado`` is terminal).
"""

from datetime import datetime

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Ticket

VALID_TICKET = {
    "title": "Ticket con máquina de estados",
    "description": "Descripción del ticket usado para probar RF3.",
    "category": TicketCategory.INCIDENT.value,
    "priority": TicketPriority.HIGH.value,
}
WORKFLOW = [
    TicketState.NEW.value,
    TicketState.IN_PROGRESS.value,
    TicketState.RESOLVED.value,
    TicketState.CLOSED.value,
]

# The three allowed transitions of the state machine.
ALLOWED_TRANSITIONS = [
    (TicketState.NEW.value, TicketState.IN_PROGRESS.value),
    (TicketState.IN_PROGRESS.value, TicketState.RESOLVED.value),
    (TicketState.RESOLVED.value, TicketState.CLOSED.value),
]

# Jumps, steps back, terminal-state changes and repeated states.
REJECTED_TRANSITIONS = [
    (TicketState.NEW.value, TicketState.RESOLVED.value),  # jump
    (TicketState.NEW.value, TicketState.CLOSED.value),  # jump to terminal
    (TicketState.IN_PROGRESS.value, TicketState.CLOSED.value),  # jump
    (TicketState.IN_PROGRESS.value, TicketState.NEW.value),  # step back
    (TicketState.RESOLVED.value, TicketState.IN_PROGRESS.value),  # step back
    (TicketState.CLOSED.value, TicketState.NEW.value),  # terminal state
    (TicketState.CLOSED.value, TicketState.IN_PROGRESS.value),  # terminal state
    (TicketState.CLOSED.value, TicketState.RESOLVED.value),  # terminal state
    (TicketState.NEW.value, TicketState.NEW.value),  # same state
]


def create_ticket(client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def change_state(client, ticket_id: int, state: str):
    return client.patch(f"/api/tickets/{ticket_id}/state", json={"state": state})


def advance_to(client, ticket_id: int, state: str) -> None:
    """Drive a ticket forward through the allowed transitions until it
    reaches ``state`` (used to set up a given starting point)."""
    current = client.get(f"/api/tickets/{ticket_id}").json()["state"]
    while current != state:
        assert WORKFLOW.index(current) < WORKFLOW.index(state), (
            f"cannot advance from {current} to {state}"
        )
        next_state = WORKFLOW[WORKFLOW.index(current) + 1]
        response = change_state(client, ticket_id, next_state)
        assert response.status_code == 200
        current = next_state


def history_of(client, ticket_id: int) -> list[dict]:
    response = client.get(f"/api/tickets/{ticket_id}/history")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


def test_allowed_transitions_update_the_state(client, session):
    for current, target in ALLOWED_TRANSITIONS:
        ticket = create_ticket(client, title=f"Ticket {current} a {target}")
        advance_to(client, ticket["id"], current)

        response = change_state(client, ticket["id"], target)

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == target
        assert data["id"] == ticket["id"]
        stored = session.get(Ticket, ticket["id"])
        assert stored.state == target


def test_allowed_transition_returns_the_updated_ticket_shape(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], TicketState.IN_PROGRESS.value)

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
        "created_at",
        "updated_at",
    }
    assert data["state"] == TicketState.IN_PROGRESS.value


# ---------------------------------------------------------------------------
# Rejected transitions
# ---------------------------------------------------------------------------


def test_rejected_transitions_answer_409_and_change_nothing(client):
    for current, target in REJECTED_TRANSITIONS:
        ticket = create_ticket(client, title=f"Rechazo de {current} a {target}")
        advance_to(client, ticket["id"], current)
        entries_before = len(history_of(client, ticket["id"]))

        response = change_state(client, ticket["id"], target)

        assert response.status_code == 409, (current, target)
        detail = response.json()["detail"]
        assert detail == f"Transición de '{current}' a '{target}' no permitida"
        assert client.get(f"/api/tickets/{ticket['id']}").json()["state"] == current
        # A rejected transition never reaches the history table.
        assert len(history_of(client, ticket["id"])) == entries_before


def test_cerrado_rejects_every_target_state(client):
    ticket = create_ticket(client)
    advance_to(client, ticket["id"], TicketState.CLOSED.value)

    for target in WORKFLOW:
        response = change_state(client, ticket["id"], target)
        assert response.status_code == 409
        assert "no permitida" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_state_change_on_missing_ticket_returns_404(client):
    response = change_state(client, 999, TicketState.IN_PROGRESS.value)

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket 999 no encontrado"


def test_unknown_state_value_returns_422(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], "Pendiente")

    assert response.status_code == 422
    # The ticket is untouched: FastAPI rejects the payload before the route.
    assert client.get(f"/api/tickets/{ticket['id']}").json()["state"] == "Nuevo"


def test_missing_state_field_returns_422(client):
    ticket = create_ticket(client)

    response = client.patch(f"/api/tickets/{ticket['id']}/state", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_successful_transition_records_exactly_one_history_entry(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], TicketState.IN_PROGRESS.value)

    assert response.status_code == 200
    entries = history_of(client, ticket["id"])
    assert len(entries) == 1


def test_history_entry_describes_the_state_change(client):
    ticket = create_ticket(client)

    change_state(client, ticket["id"], TicketState.IN_PROGRESS.value)

    entry = history_of(client, ticket["id"])[0]
    assert entry["ticket_id"] == ticket["id"]
    assert entry["action"] == "Cambio de estado"
    assert entry["field"] == "state"
    assert entry["old_value"] == TicketState.NEW.value
    assert entry["new_value"] == TicketState.IN_PROGRESS.value
    assert entry["author"] == "Anónimo"


def test_full_workflow_records_history_in_chronological_order(client):
    ticket = create_ticket(client)

    for _, target in ALLOWED_TRANSITIONS:
        assert change_state(client, ticket["id"], target).status_code == 200

    entries = history_of(client, ticket["id"])
    assert len(entries) == 3
    assert [
        (entry["old_value"], entry["new_value"]) for entry in entries
    ] == ALLOWED_TRANSITIONS
    timestamps = [datetime.fromisoformat(entry["created_at"]) for entry in entries]
    assert timestamps == sorted(timestamps)


def test_rejected_transition_records_no_history(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], TicketState.CLOSED.value)

    assert response.status_code == 409
    assert history_of(client, ticket["id"]) == []


# ---------------------------------------------------------------------------
# updated_at
# ---------------------------------------------------------------------------


def test_updated_at_changes_after_a_valid_transition(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], TicketState.IN_PROGRESS.value)

    assert response.status_code == 200
    assert datetime.fromisoformat(
        response.json()["updated_at"]
    ) > datetime.fromisoformat(ticket["updated_at"])


def test_updated_at_is_untouched_by_a_rejected_transition(client):
    ticket = create_ticket(client)

    response = change_state(client, ticket["id"], TicketState.CLOSED.value)

    assert response.status_code == 409
    assert client.get(f"/api/tickets/{ticket['id']}").json()["updated_at"] == (
        ticket["updated_at"]
    )
