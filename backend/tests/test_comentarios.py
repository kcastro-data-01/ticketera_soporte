"""Tests for comment creation on tickets (Task 9: RF5)."""

from sqlalchemy.orm import sessionmaker

from backend.constants import TicketCategory, TicketPriority
from backend.models import Comment, Ticket

VALID_TICKET = {
    "title": "Ticket con comentarios",
    "description": "Descripción del ticket que recibirá comentarios.",
    "category": TicketCategory.INQUIRY.value,
    "priority": TicketPriority.MEDIUM.value,
}
COMMENT_RESPONSE_KEYS = {"id", "ticket_id", "author", "content", "created_at"}


def create_ticket(client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_comment_returns_201(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Primer comentario del ticket."},
    )

    assert response.status_code == 201


def test_create_comment_response_contains_sent_data(client):
    ticket = create_ticket(client)

    data = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Primer comentario del ticket."},
    ).json()

    assert data["id"] is not None
    assert data["ticket_id"] == ticket["id"]
    assert data["content"] == "Primer comentario del ticket."
    assert data["author"] == "Anónimo"
    assert data["created_at"] is not None


def test_create_comment_with_explicit_author(client):
    ticket = create_ticket(client)

    data = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Respuesta de soporte.", "author": "Ana Pérez"},
    ).json()

    assert data["author"] == "Ana Pérez"


def test_comment_is_linked_to_the_correct_ticket(client):
    first = create_ticket(client, title="Primer ticket")
    second = create_ticket(client, title="Segundo ticket")

    data = client.post(
        f"/api/tickets/{second['id']}/comments",
        json={"content": "Comentario del segundo ticket."},
    ).json()

    assert data["ticket_id"] == second["id"]
    assert data["ticket_id"] != first["id"]


def test_comment_persists_in_sqlite(client, engine):
    ticket = create_ticket(client)

    client.post(
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


def test_comment_on_missing_ticket_returns_404(client):
    response = client.post(
        "/api/tickets/9999/comments",
        json={"content": "Comentario sin ticket."},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_content_returns_422(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": ""},
    )

    assert response.status_code == 422


def test_blank_content_returns_422(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "     "},
    )

    assert response.status_code == 422


def test_content_above_max_length_returns_422(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "a" * 2001},
    )

    assert response.status_code == 422


def test_blank_author_returns_422(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Contenido válido.", "author": "   "},
    )

    assert response.status_code == 422


def test_comment_without_content_returns_422(client):
    ticket = create_ticket(client)

    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"author": "Ana Pérez"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Structure and OpenAPI
# ---------------------------------------------------------------------------


def test_comment_response_structure(client):
    ticket = create_ticket(client)

    data = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario para revisar la estructura."},
    ).json()

    assert set(data.keys()) == COMMENT_RESPONSE_KEYS
    assert isinstance(data["id"], int)
    assert isinstance(data["ticket_id"], int)
    assert isinstance(data["content"], str)


def test_comment_endpoint_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    path = "/api/tickets/{ticket_id}/comments"
    assert path in schema["paths"]
    assert "post" in schema["paths"][path]
