"""Tests for comment creation on tickets (Task 9: RF5) and listing (Task 20.2)."""

from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from backend.constants import TicketCategory, TicketPriority
from backend.models import Comment, Ticket

VALID_TICKET = {
    "title": "Ticket con comentarios",
    "description": "Descripción del ticket que recibirá comentarios.",
    "category": TicketCategory.SOFTWARE.value,
    "priority": TicketPriority.MEDIUM.value,
}
COMMENT_RESPONSE_KEYS = {"id", "ticket_id", "author", "content", "created_at"}


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_comment_returns_201(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Primer comentario del ticket."},
    )

    assert response.status_code == 201


def test_create_comment_response_contains_sent_data(auth_client):
    ticket = create_ticket(auth_client)  # ticket sin asignado de forma explícita

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Primer comentario del ticket."},
    ).json()

    assert data["id"] is not None
    assert data["ticket_id"] == ticket["id"]
    assert data["content"] == "Primer comentario del ticket."
    # El autor es el usuario que inició sesión (fixture auth_client).
    assert data["author"] == "Test Admin"


def test_comment_is_linked_to_the_correct_ticket(auth_client):
    first = create_ticket(auth_client, title="Primer ticket")
    second = create_ticket(auth_client, title="Segundo ticket")

    data = auth_client.post(
        f"/api/tickets/{second['id']}/comments",
        json={"content": "Comentario del segundo ticket."},
    ).json()

    assert data["ticket_id"] == second["id"]
    assert data["ticket_id"] != first["id"]


def test_comment_persists_in_sqlite(auth_client, engine):
    ticket = create_ticket(auth_client)

    auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario que debe persistir."},
    )

    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        stored = fresh_session.query(Comment).one()
        assert stored.ticket_id == ticket["id"]
        assert stored.content == "Comentario que debe persistir."

        # The existing Comment <-> Ticket relationship is reused.
        parent = fresh_session.get(Ticket, ticket["id"])
        assert [comment.content for comment in parent.comments] == [
            "Comentario que debe persistir."
        ]
    finally:
        fresh_session.close()


def test_comment_on_missing_ticket_returns_404(auth_client):
    response = auth_client.post(
        "/api/tickets/9999/comments",
        json={"content": "Comentario sin ticket."},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_content_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": ""},
    )

    assert response.status_code == 422


def test_blank_content_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "     "},
    )

    assert response.status_code == 422


def test_content_above_max_length_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "a" * 2001},
    )

    assert response.status_code == 422


def test_blank_author_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Contenido válido.", "author": "   "},
    )

    assert response.status_code == 422


def test_comment_without_content_returns_422(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"author": "Ana Pérez"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Structure and OpenAPI
# ---------------------------------------------------------------------------


def test_comment_response_structure(auth_client):
    ticket = create_ticket(auth_client)

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario para revisar la estructura."},
    ).json()

    assert set(data.keys()) == COMMENT_RESPONSE_KEYS
    assert isinstance(data["id"], int)
    assert isinstance(data["ticket_id"], int)
    assert isinstance(data["content"], str)


def test_comment_endpoint_is_exposed_in_openapi(auth_client):
    schema = auth_client.get("/openapi.json").json()

    path = "/api/tickets/{ticket_id}/comments"
    assert path in schema["paths"]
    assert "post" in schema["paths"][path]
    assert "get" in schema["paths"][path]


# ---------------------------------------------------------------------------
# Listing (Task 20.2)
# ---------------------------------------------------------------------------


def test_list_comments_returns_200(auth_client):
    ticket = create_ticket(auth_client)

    response = auth_client.get(f"/api/tickets/{ticket['id']}/comments")

    assert response.status_code == 200
    assert response.json() == []


def test_list_comments_returns_created_comments_in_order(auth_client):
    ticket = create_ticket(auth_client)
    for content in ("Primero.", "Segundo.", "Tercero."):
        created = auth_client.post(
            f"/api/tickets/{ticket['id']}/comments",
            json={"content": content},
        )
        assert created.status_code == 201

    data = auth_client.get(f"/api/tickets/{ticket['id']}/comments").json()

    assert [comment["content"] for comment in data] == [
        "Primero.",
        "Segundo.",
        "Tercero.",
    ]
    assert [comment["id"] for comment in data] == sorted(
        comment["id"] for comment in data
    )


def test_list_comments_orders_by_created_at_not_by_id(auth_client, session):
    """Rows are sorted chronologically: id order must not drive the result."""
    ticket = create_ticket(auth_client)
    recent = Comment(
        ticket_id=ticket["id"],
        author="Ana",
        content="Más reciente",
        created_at=datetime(2026, 10, 8, 11, 0, tzinfo=timezone.utc),
    )
    older = Comment(
        ticket_id=ticket["id"],
        author="Ana",
        content="Más antiguo",
        created_at=datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc),
    )
    session.add(recent)  # lower id, later timestamp
    session.add(older)
    session.commit()

    data = auth_client.get(f"/api/tickets/{ticket['id']}/comments").json()

    assert [comment["content"] for comment in data] == ["Más antiguo", "Más reciente"]


def test_list_comments_response_structure(auth_client):
    ticket = create_ticket(auth_client)
    auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario para revisar la estructura del listado."},
    )

    data = auth_client.get(f"/api/tickets/{ticket['id']}/comments").json()

    assert isinstance(data, list) and len(data) == 1
    assert set(data[0].keys()) == COMMENT_RESPONSE_KEYS


def test_list_comments_on_missing_ticket_returns_404(auth_client):
    response = auth_client.get("/api/tickets/9999/comments")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket 9999 no encontrado"


def test_list_comments_is_read_only(auth_client, session):
    ticket = create_ticket(auth_client)
    auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario que no debe duplicarse."},
    )

    first = auth_client.get(f"/api/tickets/{ticket['id']}/comments").json()
    second = auth_client.get(f"/api/tickets/{ticket['id']}/comments").json()

    assert first == second
    assert len(session.query(Comment).all()) == 1


def test_comment_author_is_the_logged_in_user_not_the_assignee(auth_client, client):
    """El comentario se firma con quien lo escribe, aunque el ticket esté
    asignado a otra persona y aunque el cliente envíe otro autor."""
    tecnico = auth_client.post(
        "/api/users",
        json={"name": "José Solano", "email": "jose.coment@tec.local", "password": "clave12345"},
    ).json()
    ticket = create_ticket(auth_client)
    assert ticket["assigned_to_id"] == tecnico["id"]  # asignación automática

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Pendiente", "author": "Otra Persona"},
    ).json()
    assert data["author"] == "Test Admin"

    history = auth_client.get(f"/api/tickets/{ticket['id']}/history").json()
    commented = [e for e in history if e["action"] == "commented"]
    assert commented[-1]["author"] == "Test Admin"

    # El técnico asignado comenta con su propia sesión y queda con su nombre.
    login = client.post(
        "/api/auth/login", json={"email": "jose.coment@tec.local", "password": "clave12345"}
    )
    token = login.json()["access_token"]
    data = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Ya lo revisé"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert data["author"] == "José Solano"

