"""End-to-end integration flow (Task 20.2).

Covers, in one pass against the real API: creating and reading a ticket,
adding comments and listing them back chronologically, assigning users
(assign, keep, change and unassign) and verifying that the timestamps
carry the correct UTC instant (no offset drift).
"""

from datetime import datetime, timezone

from backend.constants import TicketCategory, TicketPriority, UserRole

VALID_TICKET = {
    "title": "Ticket del flujo integrado",
    "description": "Ticket usado por la prueba de integración de la Tarea 20.2.",
    "category": TicketCategory.INCIDENT.value,
    "priority": TicketPriority.HIGH.value,
}


def create_ticket(client) -> dict:
    response = client.post("/api/tickets", json=VALID_TICKET)
    assert response.status_code == 201
    return response.json()


def create_user(client, email: str) -> dict:
    response = client.post(
        "/api/users",
        json={
            "name": email.split("@")[0].title(),
            "email": email,
            "role": UserRole.SUPPORT.value,
        },
    )
    assert response.status_code == 201
    return response.json()


def assert_utc_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"sin desplazamiento: {value}"
    now = datetime.now(timezone.utc)
    assert abs((parsed - now).total_seconds()) < 60, f"desfase de hora: {value}"
    return parsed


def test_full_flow_create_comment_list_assign(client):
    # 1. Crear y consultar el ticket, con fecha/hora correcta.
    ticket = create_ticket(client)
    assert_utc_now(ticket["created_at"])

    fetched = client.get(f"/api/tickets/{ticket['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["created_at"] == ticket["created_at"]
    assert fetched.json()["state"] == "Nuevo"

    # 2. Agregar comentarios y volver a consultarlos (orden cronológico).
    for content in ("Primer comentario.", "Segundo comentario."):
        posted = client.post(
            f"/api/tickets/{ticket['id']}/comments",
            json={"content": content},
        )
        assert posted.status_code == 201
        assert_utc_now(posted.json()["created_at"])

    comments = client.get(f"/api/tickets/{ticket['id']}/comments")
    assert comments.status_code == 200
    listed = comments.json()
    assert [comment["content"] for comment in listed] == [
        "Primer comentario.",
        "Segundo comentario.",
    ]

    # 3. Asignar, reconsultar (conserva), cambiar y desasignar.
    first_user = create_user(client, "soporte.uno@example.com")
    second_user = create_user(client, "soporte.dos@example.com")

    assigned = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": first_user["id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to_id"] == first_user["id"]

    reloaded = client.get(f"/api/tickets/{ticket['id']}").json()
    assert reloaded["assigned_to_id"] == first_user["id"]

    changed = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": second_user["id"]},
    )
    assert changed.status_code == 200
    assert (
        client.get(f"/api/tickets/{ticket['id']}").json()["assigned_to_id"]
        == second_user["id"]
    )

    unassigned = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_to_id"] is None
    assert (
        client.get(f"/api/tickets/{ticket['id']}").json()["assigned_to_id"] is None
    )

    # 4. La fecha de actualización sigue sin desfase tras los cambios.
    assert_utc_now(
        client.get(f"/api/tickets/{ticket['id']}").json()["updated_at"]
    )


def test_assignment_errors_are_reported(client):
    ticket = create_ticket(client)

    unknown_user = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": 9999},
    )
    assert unknown_user.status_code == 404
    assert unknown_user.json()["detail"] == "Usuario 9999 no encontrado"

    missing_ticket = client.patch(
        "/api/tickets/9999/assign",
        json={"assigned_to_id": None},
    )
    assert missing_ticket.status_code == 404
    assert missing_ticket.json()["detail"] == "Ticket 9999 no encontrado"

    invalid_payload = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": "no-numerico"},
    )
    assert invalid_payload.status_code == 422

    # El ticket no queda asignado por error.
    assert client.get(f"/api/tickets/{ticket['id']}").json()["assigned_to_id"] is None


def test_user_management_and_assignment_integration(client):
    """Task 20.3 flow: create/list users and assign a ticket between them.

    Steps: create a user, list the users, create a ticket, assign it to the
    created user, read the ticket back (the assignment persists), create a
    second user, change the assignment and read it back again.
    """
    # 1. Crear usuario.
    first = client.post(
        "/api/users",
        json={
            "name": "Ana Pérez",
            "email": "ana.perez@soporte.local",
            "role": "Soporte",
        },
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    # 2. Obtener usuarios: el creado aparece y es listable.
    users = client.get("/api/users")
    assert users.status_code == 200
    assert [user["id"] for user in users.json()] == [first_id]
    assert users.json()[0]["name"] == "Ana Pérez"

    # 3. Crear ticket.
    ticket = create_ticket(client)
    assert ticket["assigned_to_id"] is None

    # 4. Asignar el ticket al usuario creado.
    assigned = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": first_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to_id"] == first_id

    # 5-6. Consultar de nuevo: la asignación persiste.
    reloaded = client.get(f"/api/tickets/{ticket['id']}").json()
    assert reloaded["assigned_to_id"] == first_id

    # 7. Crear un segundo usuario (rol por defecto: Soporte).
    second = client.post(
        "/api/users",
        json={"name": "Carlos Gómez", "email": "carlos.gomez@soporte.local"},
    )
    assert second.status_code == 201
    second_id = second.json()["id"]
    assert second.json()["role"] == "Soporte"
    assert {user["id"] for user in client.get("/api/users").json()} == {
        first_id,
        second_id,
    }

    # 8. Cambiar la asignación al segundo usuario.
    changed = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": second_id},
    )
    assert changed.status_code == 200
    assert changed.json()["assigned_to_id"] == second_id

    # 9. Consultar de nuevo: la nueva asignación persiste.
    final = client.get(f"/api/tickets/{ticket['id']}").json()
    assert final["assigned_to_id"] == second_id
    assert final["created_at"] == ticket["created_at"]
