"""Tests for ticket search and filters (Task 10: RF7, RF8)."""

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Ticket

BASE_PAYLOAD = {
    "title": "Ticket de prueba",
    "description": "Descripción por defecto del ticket de prueba.",
    "category": TicketCategory.INCIDENT.value,
    "priority": TicketPriority.MEDIUM.value,
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


def create_ticket(client, **overrides) -> dict:
    payload = {**BASE_PAYLOAD, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def set_state(session, ticket_id: int, value: str) -> None:
    """Set a ticket state directly in the database.

    RF3 (state transitions) is still pending as Task 18, so the tests prepare
    the stored value themselves instead of using a non-existent endpoint.
    """
    ticket = session.get(Ticket, ticket_id)
    ticket.state = value
    session.commit()


def create_sample_tickets(client, session) -> list[dict]:
    """Create five deterministic tickets, returned in creation order."""
    tickets = [
        create_ticket(
            client,
            title="Falla de impresión",
            description=(
                "El equipo no responde y falla el correo saliente; "
                "revisar con el servidor de área."
            ),
            category=TicketCategory.INCIDENT.value,
            priority=TicketPriority.HIGH.value,
        ),
        create_ticket(
            client,
            title="Consulta de reportes",
            description="El cliente solicita un resumen de ventas.",
            category=TicketCategory.INQUIRY.value,
            priority=TicketPriority.LOW.value,
        ),
        create_ticket(
            client,
            title="Renovación de licencias",
            description="Mantenimiento programado del servidor de aplicaciones.",
            category=TicketCategory.MAINTENANCE.value,
            priority=TicketPriority.CRITICAL.value,
        ),
        create_ticket(
            client,
            title="Solicitud de acceso",
            description="Necesito permisos al módulo de facturación.",
            category=TicketCategory.REQUEST.value,
            priority=TicketPriority.MEDIUM.value,
        ),
        create_ticket(
            client,
            title="Error al guardar cambios",
            description="La aplicación cierra sin guardar los cambios.",
            category=TicketCategory.INCIDENT.value,
            priority=TicketPriority.LOW.value,
        ),
    ]
    set_state(session, tickets[2]["id"], TicketState.IN_PROGRESS.value)
    return tickets


def response_ids(response) -> list[int]:
    return [ticket["id"] for ticket in response.json()]


# ---------------------------------------------------------------------------
# 1. Default behaviour without parameters
# ---------------------------------------------------------------------------


def test_list_without_filters_keeps_existing_behaviour(client, session):
    created = create_sample_tickets(client, session)

    response = client.get("/api/tickets")

    assert response.status_code == 200
    assert len(response.json()) == 5
    assert set(response_ids(response)) == {ticket["id"] for ticket in created}
    for ticket in response.json():
        assert set(ticket.keys()) == TICKET_RESPONSE_KEYS


# ---------------------------------------------------------------------------
# 2-5. Search by text
# ---------------------------------------------------------------------------


def test_search_matches_title(client, session):
    created = create_sample_tickets(client, session)

    response = client.get("/api/tickets", params={"search": "impresión"})

    assert response.status_code == 200
    assert response_ids(response) == [created[0]["id"]]


def test_search_matches_description(client, session):
    created = create_sample_tickets(client, session)

    response = client.get("/api/tickets", params={"search": "servidor"})

    # "servidor" only appears inside the descriptions of two tickets.
    assert response.status_code == 200
    assert set(response_ids(response)) == {created[0]["id"], created[2]["id"]}
    assert created[2]["id"] in response_ids(response)


def test_search_is_case_insensitive(client, session):
    created = create_sample_tickets(client, session)

    lowercase = client.get("/api/tickets", params={"search": "falla de impresión"})
    uppercase = client.get("/api/tickets", params={"search": "FALLA DE IMPRESIÓN"})
    plain_uppercase = client.get("/api/tickets", params={"search": "CORREO"})

    assert response_ids(lowercase) == [created[0]["id"]]
    assert response_ids(uppercase) == [created[0]["id"]]
    assert response_ids(plain_uppercase) == [created[0]["id"]]


def test_search_without_results_returns_200_and_empty_list(client, session):
    create_sample_tickets(client, session)

    response = client.get("/api/tickets", params={"search": "xyzzy-no-existe"})

    assert response.status_code == 200
    assert response.json() == []


def test_blank_search_behaves_as_if_not_sent(client, session):
    create_sample_tickets(client, session)

    empty = client.get("/api/tickets", params={"search": ""})
    spaces = client.get("/api/tickets", params={"search": "   "})

    assert empty.status_code == 200
    assert len(empty.json()) == 5
    assert spaces.status_code == 200
    assert len(spaces.json()) == 5


def test_search_treats_sql_wildcards_literally(client, session):
    create_sample_tickets(client, session)

    percent = client.get("/api/tickets", params={"search": "%"})
    underscore = client.get("/api/tickets", params={"search": "_"})

    # No sample ticket contains those characters, so they must not behave
    # as LIKE wildcards (which would return every ticket).
    assert percent.status_code == 200
    assert percent.json() == []
    assert underscore.status_code == 200
    assert underscore.json() == []


# ---------------------------------------------------------------------------
# 6-8. Individual filters
# ---------------------------------------------------------------------------


def test_filter_by_category(client, session):
    created = create_sample_tickets(client, session)

    response = client.get("/api/tickets", params={"category": TicketCategory.INCIDENT.value})

    assert response.status_code == 200
    assert set(response_ids(response)) == {created[0]["id"], created[4]["id"]}


def test_filter_by_priority(client, session):
    created = create_sample_tickets(client, session)

    response = client.get("/api/tickets", params={"priority": TicketPriority.LOW.value})

    assert response.status_code == 200
    assert set(response_ids(response)) == {created[1]["id"], created[4]["id"]}


def test_filter_by_state(client, session):
    created = create_sample_tickets(client, session)

    in_progress = client.get(
        "/api/tickets", params={"state": TicketState.IN_PROGRESS.value}
    )
    new = client.get("/api/tickets", params={"state": TicketState.NEW.value})
    closed = client.get("/api/tickets", params={"state": TicketState.CLOSED.value})

    assert in_progress.status_code == 200
    assert response_ids(in_progress) == [created[2]["id"]]
    assert response_ids(new) == [
        created[4]["id"],
        created[3]["id"],
        created[1]["id"],
        created[0]["id"],
    ]
    assert closed.status_code == 200
    assert closed.json() == []


# ---------------------------------------------------------------------------
# 9-10. Combined criteria (AND)
# ---------------------------------------------------------------------------


def test_combination_of_two_filters(client, session):
    created = create_sample_tickets(client, session)

    response = client.get(
        "/api/tickets",
        params={
            "category": TicketCategory.INCIDENT.value,
            "priority": TicketPriority.LOW.value,
        },
    )

    # Category alone returns two tickets and priority alone returns two
    # tickets; only one ticket satisfies both.
    assert response.status_code == 200
    assert response_ids(response) == [created[4]["id"]]


def test_combination_of_search_and_filters(client, session):
    created = create_sample_tickets(client, session)

    example = client.get(
        "/api/tickets",
        params={
            "search": "correo",
            "priority": TicketPriority.HIGH.value,
            "state": TicketState.NEW.value,
        },
    )
    narrowed = client.get(
        "/api/tickets",
        params={"search": "servidor", "priority": TicketPriority.CRITICAL.value},
    )

    assert example.status_code == 200
    assert response_ids(example) == [created[0]["id"]]
    # "servidor" alone matches two tickets; the priority narrows it to one.
    assert response_ids(narrowed) == [created[2]["id"]]


# ---------------------------------------------------------------------------
# 11-13. Invalid enum values
# ---------------------------------------------------------------------------


def test_invalid_category_returns_422(client):
    response = client.get("/api/tickets", params={"category": "Categoría inventada"})

    assert response.status_code == 422


def test_invalid_priority_returns_422(client):
    response = client.get("/api/tickets", params={"priority": "Urgentísima"})

    assert response.status_code == 422


def test_invalid_state_returns_422(client):
    response = client.get("/api/tickets", params={"state": "Bloqueado"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 14-15. Ordering and read-only behaviour
# ---------------------------------------------------------------------------


def test_results_keep_newest_first_order(client, session):
    created = create_sample_tickets(client, session)

    without_filters = client.get("/api/tickets")
    with_filter = client.get("/api/tickets", params={"state": TicketState.NEW.value})

    assert response_ids(without_filters) == [
        created[4]["id"],
        created[3]["id"],
        created[2]["id"],
        created[1]["id"],
        created[0]["id"],
    ]
    assert response_ids(with_filter) == [
        created[4]["id"],
        created[3]["id"],
        created[1]["id"],
        created[0]["id"],
    ]


def test_search_and_filters_do_not_modify_tickets(client, session):
    created = create_sample_tickets(client, session)
    before = client.get("/api/tickets").json()

    client.get("/api/tickets", params={"search": "correo"})
    client.get("/api/tickets", params={"category": TicketCategory.INCIDENT.value})
    client.get("/api/tickets", params={"priority": TicketPriority.LOW.value})
    client.get("/api/tickets", params={"state": TicketState.NEW.value})
    client.get(
        "/api/tickets",
        params={"search": "servidor", "state": TicketState.IN_PROGRESS.value},
    )
    client.get("/api/tickets", params={"category": "Invencible"})

    after = client.get("/api/tickets").json()

    assert before == after
    assert len(after) == len(created)
