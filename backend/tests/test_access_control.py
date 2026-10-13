"""Pruebas de control de acceso por rol (auditoría de seguridad).

Cubre tres escenarios:

1. Recursos privados sin token → ``401 Unauthorized``.
2. Rol no autorizado para una operación → ``403 Forbidden``.
3. Límites del control de propiedad de tickets: el modelo actual NO tiene
   un campo que identifique al creador/solicitante del ticket, por lo que
   un Solicitante que conoce el ID puede leer tickets ajenos. Este problema
   se documenta aquí como prueba conocida (ver ``test_solicitante_puede_leer_ticket_ajeno_limitacion``)
   y NO se filtra por ``assigned_to_id`` porque ese campo representa al
   Soporte/Técnico asignado, no al solicitante.
"""

import pytest

from backend.constants import TicketCategory, TicketPriority, UserRole

VALID_TICKET = {
    "title": "Ticket de control de acceso",
    "description": "Usado para verificar las reglas de acceso por rol.",
    "category": TicketCategory.SOFTWARE.value,
    "priority": TicketPriority.MEDIUM.value,
}


def register_requester(client, email="solicitante.test@correo.local") -> dict:
    """Register a user via /api/auth/register and return the token.

    Subsequent registrations are forced to the ``Solicitante`` role by the
    existing business rule, so this returns a Solicitante token.
    """
    resp = client.post(
        "/api/auth/register",
        json={"name": "Solicitante Test", "email": email, "password": "clave12345"},
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_role_user(session, role: str, email: str, password_hash: str) -> int:
    """Create a user with a bcrypt hash so it can log in; return its id."""
    from backend.models import User

    user = User(
        name=f"Usuario {role}",
        email=email,
        role=role,
        is_active=True,
        password_hash=password_hash,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id


# ---------------------------------------------------------------------------
# 1. Recursos privados sin token → 401
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/tickets"),
        ("GET", "/api/tickets/1"),
        ("GET", "/api/tickets/1/history"),
        ("GET", "/api/tickets/1/comments"),
        ("GET", "/api/history"),
        ("GET", "/api/users"),
    ],
)
def test_private_read_endpoints_require_token(client, method, path):
    """Todo recurso privado de lectura responde 401 sin token."""
    response = client.request(method, path)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", "/api/tickets", VALID_TICKET),
        ("PATCH", "/api/tickets/1", {"title": "Cambio sin token"}),
        ("PATCH", "/api/tickets/1/assign", {"assigned_to_id": None}),
        ("PATCH", "/api/tickets/1/state", {"state": "En proceso"}),
        ("POST", "/api/tickets/1/comments", {"content": "Comentario sin token"}),
        ("POST", "/api/users", {"name": "X", "email": "x@correo.local"}),
        ("PATCH", "/api/users/1", {"name": "X"}),
    ],
)
def test_private_write_endpoints_require_token(client, method, path, body):
    """Toda operación de escritura privada responde 401 sin token."""
    response = client.request(method, path, json=body)
    assert response.status_code == 401


def test_public_endpoints_stay_open(client):
    """Los endpoints públicos siguen accesibles sin token."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/config").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_me_requires_token(client):
    """GET /api/auth/me responde 401 sin token."""
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# 2. Rol no autorizado → 403
# ---------------------------------------------------------------------------


def create_ticket(client) -> dict:
    """Create a ticket through the API; requires an authenticated client."""
    resp = client.post("/api/tickets", json=VALID_TICKET)
    assert resp.status_code == 201
    return resp.json()


def test_solicitante_cannot_update_ticket(client, auth_client):
    """Un Solicitante no puede editar tickets (PATCH /api/tickets/{id})."""
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    resp = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Intento de edición no autorizada"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_solicitante_cannot_assign_ticket(client, auth_client):
    """Un Solicitante no puede asignar tickets."""
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_solicitante_cannot_change_state(client, auth_client):
    """Un Solicitante no puede cambiar el estado de un ticket."""
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/state",
        json={"state": "En proceso"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_solicitante_cannot_create_user(client):
    """Un Solicitante no puede crear usuarios."""
    token = register_requester(client)

    resp = client.post(
        "/api/users",
        json={"name": "Nuevo", "email": "nuevo@correo.local"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_solicitante_cannot_update_user(client, auth_client):
    """Un Solicitante no puede actualizar usuarios."""
    token = register_requester(client)

    resp = client.patch(
        "/api/users/1",
        json={"name": "Nombre cambiado"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_solicitante_can_read_and_comment(client, auth_client):
    """Un Solicitante autenticado sí puede listar, leer y comentar."""
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    assert client.get("/api/tickets", headers=headers(token)).status_code == 200
    assert (
        client.get(f"/api/tickets/{ticket['id']}", headers=headers(token)).status_code
        == 200
    )
    resp = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Consulta del solicitante"},
        headers=headers(token),
    )
    assert resp.status_code == 201


def test_soporte_can_update_and_assign(client, auth_client, session):
    """Un usuario Soporte (con login) puede editar y asignar tickets."""
    from backend.auth import hash_password

    make_role_user(
        session,
        UserRole.SUPPORT.value,
        "soporte.test@correo.local",
        hash_password("clave12345"),
    )
    ticket = create_ticket(auth_client)

    login = client.post(
        "/api/auth/login",
        json={"email": "soporte.test@correo.local", "password": "clave12345"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Editado por soporte"},
        headers=headers(token),
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
        headers=headers(token),
    )
    assert resp.status_code == 200


def test_supervisor_cannot_assign_but_can_update(client, auth_client, session):
    """Un Supervisor actualiza tickets pero no los asigna (regla existente)."""
    from backend.auth import hash_password

    make_role_user(
        session,
        UserRole.SUPERVISOR.value,
        "supervisor.test@correo.local",
        hash_password("clave12345"),
    )
    ticket = create_ticket(auth_client)

    login = client.post(
        "/api/auth/login",
        json={"email": "supervisor.test@correo.local", "password": "clave12345"},
    )
    token = login.json()["access_token"]

    resp = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Editado por supervisor"},
        headers=headers(token),
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_tecnico_cannot_manage_users(client, auth_client, session):
    """Un Técnico no administra usuarios (POST /api/users → 403)."""
    from backend.auth import hash_password

    make_role_user(
        session,
        UserRole.TECHNICIAN.value,
        "tecnico.test@correo.local",
        hash_password("clave12345"),
    )

    login = client.post(
        "/api/auth/login",
        json={"email": "tecnico.test@correo.local", "password": "clave12345"},
    )
    token = login.json()["access_token"]

    resp = client.post(
        "/api/users",
        json={"name": "Nuevo", "email": "nuevo.tecnico@correo.local"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_inactive_user_cannot_login(client, auth_client, session):
    """Un usuario desactivado no puede iniciar sesión (regla existente)."""
    from backend.auth import hash_password
    from backend.models import User

    user_id = make_role_user(
        session,
        UserRole.SUPPORT.value,
        "inactivo.test@correo.local",
        hash_password("clave12345"),
    )
    db_user = session.get(User, user_id)
    db_user.is_active = False
    session.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": "inactivo.test@correo.local", "password": "clave12345"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. Limitación conocida: el modelo no identifica al creador del ticket
# ---------------------------------------------------------------------------


def test_solicitante_puede_leer_ticket_ajeno_limitacion(client, auth_client, session):
    """DOCUMENTA UNA LIMITACIÓN CONOCIDA (no es un objetivo de diseño).

    El modelo ``Ticket`` solo tiene ``assigned_to_id`` (la persona de
    Soporte/Técnico que atiende el ticket). No existe un campo
    ``created_by_id``/``requested_by_id``, por lo que hoy no es posible
    distinguir con seguridad al solicitante que creó el ticket.

    Consecuencia: un Solicitante autenticado que conoce el ID puede leer
    tickets ajenos. Esto NO se filtra por ``assigned_to_id`` porque ese
    campo no representa al solicitante (sería incorrecto: el ticket de un
    solicitante está normalmente asignado a un soporte).

    Corrección necesaria (pendiente de decisión): añadir a la tabla
    ``tickets`` una columna ``created_by_id`` FK a ``users.id`` que se
    registre en ``POST /api/tickets`` con el usuario autenticado, y filtrar
    las lecturas de Solicitante por ese campo.
    """
    # Otro solicitante creó este ticket vía la API (como Administrador aquí
    # porque la creación asocia el ticket a quien lo atiende).
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    resp = client.get(
        f"/api/tickets/{ticket['id']}", headers=headers(token)
    )
    # Limitación actual: el acceso NO está bloqueado por propiedad.
    assert resp.status_code == 200


def test_ticket_model_has_no_creator_field():
    """Guardia: mientras no exista ``created_by_id`` no se implementa filtro."""
    from backend.models import Ticket

    columns = {column.name for column in Ticket.__table__.columns}
    assert "created_by_id" not in columns
    assert "requested_by_id" not in columns
