"""Tests for ticket search and filters (Task 10: RF7, RF8)."""

from backend.constants import TicketCategory, TicketPriority, TicketState
from backend.models import Ticket

BASE_PAYLOAD = {
    "title": "Ticket de prueba",
    "description": "Descripción por defecto del ticket de prueba.",
    "category": TicketCategory.HARDWARE.value,
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
    "created_by_id",
    "created_at",
    "updated_at",
}


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**BASE_PAYLOAD, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
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


def create_sample_tickets(auth_client, session) -> list[dict]:
    """Create five deterministic tickets, returned in creation order."""
    tickets = [
        create_ticket(
            auth_client,
            title="Falla de impresión",
            description=(
                "El equipo no responde y falla el correo saliente; "
                "revisar con el servidor de área."
            ),
            category=TicketCategory.HARDWARE.value,
            priority=TicketPriority.HIGH.value,
        ),
        create_ticket(
            auth_client,
            title="Consulta de reportes",
            description="El cliente solicita un resumen de ventas.",
            category=TicketCategory.SOFTWARE.value,
            priority=TicketPriority.LOW.value,
        ),
        create_ticket(
            auth_client,
            title="Caída de red en el piso 3",
            description="Mantenimiento programado del servidor de aplicaciones por la caída de red.",
            category=TicketCategory.NETWORK.value,
            priority=TicketPriority.CRITICAL.value,
        ),
        create_ticket(
            auth_client,
            title="Solicitud de acceso",
            description="Necesito permisos al módulo de facturación.",
            category=TicketCategory.ACCESS.value,
            priority=TicketPriority.MEDIUM.value,
        ),
        create_ticket(
            auth_client,
            title="Teclado sin respuesta",
            description="Las teclas del teclado del puesto 12 dejaron de responder.",
            category=TicketCategory.HARDWARE.value,
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


def test_list_without_filters_keeps_existing_behaviour(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets")

    assert response.status_code == 200
    assert len(response.json()) == 5
    assert set(response_ids(response)) == {ticket["id"] for ticket in created}
    for ticket in response.json():
        assert set(ticket.keys()) == TICKET_RESPONSE_KEYS


# ---------------------------------------------------------------------------
# 2-5. Search by text
# ---------------------------------------------------------------------------


def test_search_matches_title(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets", params={"search": "impresión"})

    assert response.status_code == 200
    assert response_ids(response) == [created[0]["id"]]


def test_search_matches_description(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets", params={"search": "servidor"})

    # "servidor" only appears inside the descriptions of two tickets.
    assert response.status_code == 200
    assert set(response_ids(response)) == {created[0]["id"], created[2]["id"]}
    assert created[2]["id"] in response_ids(response)


def test_search_is_case_insensitive(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    lowercase = auth_client.get("/api/tickets", params={"search": "falla de impresión"})
    uppercase = auth_client.get("/api/tickets", params={"search": "FALLA DE IMPRESIÓN"})
    plain_uppercase = auth_client.get("/api/tickets", params={"search": "CORREO"})

    assert response_ids(lowercase) == [created[0]["id"]]
    assert response_ids(uppercase) == [created[0]["id"]]
    assert response_ids(plain_uppercase) == [created[0]["id"]]


def test_search_without_results_returns_200_and_empty_list(auth_client, session):
    create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets", params={"search": "xyzzy-no-existe"})

    assert response.status_code == 200
    assert response.json() == []


def test_blank_search_behaves_as_if_not_sent(auth_client, session):
    create_sample_tickets(auth_client, session)

    empty = auth_client.get("/api/tickets", params={"search": ""})
    spaces = auth_client.get("/api/tickets", params={"search": "   "})

    assert empty.status_code == 200
    assert len(empty.json()) == 5
    assert spaces.status_code == 200
    assert len(spaces.json()) == 5


def test_search_treats_sql_wildcards_literally(auth_client, session):
    create_sample_tickets(auth_client, session)

    percent = auth_client.get("/api/tickets", params={"search": "%"})
    underscore = auth_client.get("/api/tickets", params={"search": "_"})

    # No sample ticket contains those characters, so they must not behave
    # as LIKE wildcards (which would return every ticket).
    assert percent.status_code == 200
    assert percent.json() == []
    assert underscore.status_code == 200
    assert underscore.json() == []


# ---------------------------------------------------------------------------
# 6-8. Individual filters
# ---------------------------------------------------------------------------


def test_filter_by_category(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets", params={"category": TicketCategory.HARDWARE.value})

    assert response.status_code == 200
    assert set(response_ids(response)) == {created[0]["id"], created[4]["id"]}


def test_filter_by_priority(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get("/api/tickets", params={"priority": TicketPriority.LOW.value})

    assert response.status_code == 200
    assert set(response_ids(response)) == {created[1]["id"], created[4]["id"]}


def test_filter_by_state(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    in_progress = auth_client.get(
        "/api/tickets", params={"state": TicketState.IN_PROGRESS.value}
    )
    new = auth_client.get("/api/tickets", params={"state": TicketState.NEW.value})
    closed = auth_client.get("/api/tickets", params={"state": TicketState.CLOSED.value})

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


def test_combination_of_two_filters(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    response = auth_client.get(
        "/api/tickets",
        params={
            "category": TicketCategory.HARDWARE.value,
            "priority": TicketPriority.LOW.value,
        },
    )

    # Category alone returns two tickets and priority alone returns two
    # tickets; only one ticket satisfies both.
    assert response.status_code == 200
    assert response_ids(response) == [created[4]["id"]]


def test_combination_of_search_and_filters(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    example = auth_client.get(
        "/api/tickets",
        params={
            "search": "correo",
            "priority": TicketPriority.HIGH.value,
            "state": TicketState.NEW.value,
        },
    )
    narrowed = auth_client.get(
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


def test_invalid_category_returns_422(auth_client):
    response = auth_client.get("/api/tickets", params={"category": "Categoría inventada"})

    assert response.status_code == 422


def test_invalid_priority_returns_422(auth_client):
    response = auth_client.get("/api/tickets", params={"priority": "Urgentísima"})

    assert response.status_code == 422


def test_invalid_state_returns_422(auth_client):
    response = auth_client.get("/api/tickets", params={"state": "Bloqueado"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 14-15. Ordering and read-only behaviour
# ---------------------------------------------------------------------------


def test_results_keep_newest_first_order(auth_client, session):
    created = create_sample_tickets(auth_client, session)

    without_filters = auth_client.get("/api/tickets")
    with_filter = auth_client.get("/api/tickets", params={"state": TicketState.NEW.value})

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


def test_search_and_filters_do_not_modify_tickets(auth_client, session):
    created = create_sample_tickets(auth_client, session)
    before = auth_client.get("/api/tickets").json()

    auth_client.get("/api/tickets", params={"search": "correo"})
    auth_client.get("/api/tickets", params={"category": TicketCategory.HARDWARE.value})
    auth_client.get("/api/tickets", params={"priority": TicketPriority.LOW.value})
    auth_client.get("/api/tickets", params={"state": TicketState.NEW.value})
    auth_client.get(
        "/api/tickets",
        params={"search": "servidor", "state": TicketState.IN_PROGRESS.value},
    )
    auth_client.get("/api/tickets", params={"category": "Invencible"})

    after = auth_client.get("/api/tickets").json()

    assert before == after
    assert len(after) == len(created)


# --- Mis tickets, paginación y resumen ---


def _ticket(auth_client, **overrides):
    payload = {
        "title": "Ticket del panel",
        "description": "Descripción.",
        "category": "Red",
        "priority": "Media",
        **overrides,
    }
    resp = auth_client.post("/api/tickets", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_mios_returns_only_tickets_assigned_to_the_caller(auth_client):
    me = auth_client.get("/api/auth/me").json()
    mine = _ticket(auth_client, title="Mío")
    other = _ticket(auth_client, title="Ajeno")
    auth_client.patch(f"/api/tickets/{mine['id']}/assign", json={"assigned_to_id": me["id"]})

    ids = [t["id"] for t in auth_client.get("/api/tickets?mios=true").json()]
    assert ids == [mine["id"]]
    assert other["id"] not in ids


def test_pagination_with_total_count_header(auth_client):
    created = [_ticket(auth_client, title=f"Ticket {n}") for n in range(5)]

    first = auth_client.get("/api/tickets?limit=2&offset=0")
    second = auth_client.get("/api/tickets?limit=2&offset=2")
    last = auth_client.get("/api/tickets?limit=2&offset=4")

    assert first.headers["X-Total-Count"] == "5"
    newest_first = [t["id"] for t in reversed(created)]
    assert [t["id"] for t in first.json()] == newest_first[0:2]
    assert [t["id"] for t in second.json()] == newest_first[2:4]
    assert [t["id"] for t in last.json()] == newest_first[4:5]
    # Sin limit se mantiene el listado completo.
    assert len(auth_client.get("/api/tickets").json()) == 5


def test_summary_counts_visible_tickets(auth_client):
    me = auth_client.get("/api/auth/me").json()
    a = _ticket(auth_client, priority="Crítica")
    b = _ticket(auth_client)
    c = _ticket(auth_client, priority="Crítica")
    auth_client.patch(f"/api/tickets/{a['id']}/assign", json={"assigned_to_id": me["id"]})
    auth_client.patch(f"/api/tickets/{b['id']}/state", json={"state": "En proceso"})
    for state in ("En proceso", "Resuelto"):
        auth_client.patch(f"/api/tickets/{c['id']}/state", json={"state": state})

    summary = auth_client.get("/api/tickets/summary").json()
    # Cerrar el ticket asignado: sigue contando en «mios», no en abiertos.
    for state in ("En proceso", "Resuelto", "Cerrado"):
        auth_client.patch(f"/api/tickets/{a['id']}/state", json={"state": state})
    after = auth_client.get("/api/tickets/summary").json()
    assert (after["mios"], after["mios_abiertos"]) == (1, 0)

    assert summary == {
        "total": 3,
        "nuevos": 1,
        "en_proceso": 1,
        "resueltos": 1,
        "cerrados": 0,
        "criticos_abiertos": 1,
        "mios": 1,
        "mios_abiertos": 1,
    }
