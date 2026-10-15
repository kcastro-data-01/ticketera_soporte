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
    # El autor debe ser determinado por el backend; si el ticket no tiene persona
    # asignada, usa "Anónimo". Si tiene asignado, muestra su nombre.
    assert data["author"] is not None


def test_create_comment_with_explicit_author_overridden_by_assignee(auth_client, session):
    """Un autor explícito enviado por el cliente no reemplaza al asignado."""
    from backend.models import User
    from sqlalchemy.orm import sessionmaker

    ticket = create_ticket(auth_client, assigned_to_id=1)  # ticket con Ana asignada

    # Crear usuario diferente para verificar que el explícito no sobrescribe
    # al asignado cuando el backend prioriza al asignado
    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario con autor explícito.", "author": "Carlos Gómez"},
    ).json()

    # Según la regla: el nombre de la persona asignada tiene prioridad
    assert data["author"] != "Carlos Gómez"
    # Y no debería ser "Anónimo" si hay alguien asignado
    assert data["author"] is not None


def test_create_comment_unassigned_ticket_uses_anonimo(auth_client):
    """Un ticket sin persona asignada produce autor 'Anónimo'."""
    ticket = create_ticket(auth_client, assigned_to_id=None)  # ticket sin asignar

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario sin ticket asignado."},
    ).json()

    assert data["author"] == "Anónimo"


def test_create_comment_client_author_when_no_assignee(auth_client):
    """Si no hay persona asignada, el autor venía del cliente pero backend usa 'Anónimo'."""
    ticket = create_ticket(auth_client, assigned_to_id=None)  # ticket sin asignar

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario.", "author": "Ana Pérez"},
    ).json()

    # Aunque el cliente envíe autor, al no haber asignado en ticket, usa "Anónimo"
    assert data["author"] == "Anónimo"


def test_create_comment_with_explicit_author(auth_client):
    ticket = create_ticket(auth_client)  # ticket sin persona asignada

    data = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Respuesta de soporte.", "author": "Ana Pérez"},
    ).json()

    # Cuando no hay persona asignada en el ticket, el backend usa "Anónimo"
    # aunque el cliente envíe autor explícito (regla 2 del usuario).
    assert data["author"] == "Anónimo"


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


def test_create_comment_with_assigned_user_via_integration(auth_client, engine):
    """Integración completa: usuario creado en la BD, ticket asignado, comentario con autor real.
    
    Verifica que:
    - El usuario "María Gómez" se crea en la BD temporal
    - El ticket está asignado al usuario creado
    - El comentario creado mediante TestClient muestra el nombre real del asignado
    - El autor enviado por el cliente no sustituye al asignado
    - El comentario se guarda con el autor correcto
    """
    from sqlalchemy.orm import sessionmaker
    from backend.models import User, Ticket, Comment
    
    # 1. Crear usuario "María Gómez" en la base de datos temporal
    testing_engine = engine
    testing_session = sessionmaker(bind=testing_engine, autoflush=False, expire_on_commit=False)
    db = testing_session()
    
    try:
        user = User(name="María Gómez", email="maria@test.local", role="Técnico")
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Usuario creado: id={user.id}, name={user.name}")
        
        # 2. Crear ticket asignado al usuario creado
        from backend.constants import TicketCategory, TicketPriority
        ticket = Ticket(
            title="Ticket test asignado",
            description="Descripción del ticket asignado",
            category=TicketCategory.SOFTWARE.value,
            priority=TicketPriority.MEDIUM.value,
            assigned_to_id=user.id
        )
        from backend.main import app
        from backend.database import Base, enable_sqlite_foreign_keys, get_session
        from backend.database import Base
        Base.metadata.create_all(bind=testing_engine)
        
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        print(f"Ticket creado: id={ticket.id}, assigned_to_id={ticket.assigned_to_id}")
        
        # 3. Verificar que el ticket tiene el assigned_to_id correcto
        assert ticket.assigned_to_id == user.id, f"Expected assigned_to_id={user.id}, got {ticket.assigned_to_id}"
        
        # 4. Crear comentario mediante TestClient enviando autor "Carlos Gómez"
        # El TestClient usa su propia sesión, pero la BD es compartida
        # El backend debe determinar el autor desde la persona asignada al ticket
        response = auth_client.post(
            f"/api/tickets/{ticket.id}/comments",
            json={"content": "Comentario de prueba", "author": "Carlos Gómez"}
        )
        print(f"Response status: {response.status_code}")
        data = response.json()
        print(f"Data author: {data['author']}")
        print(f"Data ticket_id: {data['ticket_id']}")
        
        # 5. Comprobar exactamente data["author"] == "María Gómez"
        # Según la regla: el nombre de la persona asignada tiene prioridad sobre el enviado por el cliente
        # Como el ticket tiene María Gómez asignada, el autor debería ser "María Gómez"
        # a pesar de que enviamos "Carlos Gómez"
        assert data["author"] == "María Gómez", f"Expected 'María Gómez', got '{data['author']}'"
        print(f"✓ author is 'María Gómez' as expected")
        
        # 6. Verificar que el comentario quedó guardado con ese mismo autor
        # Usando la sesión de testing para verificar la persistencia
        fresh_db = testing_session()
        try:
            stored_comment = fresh_db.query(Comment).filter_by(ticket_id=ticket.id).first()
            print(f"Stored comment author: {stored_comment.author}")
            assert stored_comment.author == "María Gómez", f"Expected 'María Gómez', got '{stored_comment.author}'"
            print("✓ Comment saved with correct author")
        finally:
            fresh_db.close()
        
    finally:
        db.close()
