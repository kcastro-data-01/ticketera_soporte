"""Pruebas de control de acceso por rol (auditoría de seguridad).

Cubre tres escenarios:

1. Recursos privados sin token → ``401 Unauthorized``.
2. Rol no autorizado para una operación → ``403 Forbidden``, según la tabla
   de permisos (ver ``ayuda.html``).
3. Propiedad de tickets: un Solicitante solo ve, comenta y consulta el
   historial de los tickets que creó (``created_by_id``); los ajenos
   responden ``404`` para no revelar que existen.
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
    """Create a ``Solicitante`` with login and return its token.

    Self-registration is closed after the first user, so the user is
    inserted directly (as an administrator would create it) and logs in.
    """
    from backend.auth import hash_password
    from backend.database import get_session
    from backend.main import app
    from backend.models import User

    session = next(app.dependency_overrides[get_session]())
    session.add(
        User(
            name="Solicitante Test",
            email=email,
            role=UserRole.REQUESTER.value,
            password_hash=hash_password("clave12345"),
        )
    )
    session.commit()
    resp = client.post("/api/auth/login", json={"email": email, "password": "clave12345"})
    assert resp.status_code == 200
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
    """Un Solicitante no puede cambiar el estado de un ticket que no tiene
    asignado: 403 en uno suyo, 404 en uno ajeno (no se revela que existe)."""
    ajeno = create_ticket(auth_client)
    token = register_requester(client)
    propio = client.post("/api/tickets", json={
        "title": "Mi impresora", "description": "No imprime desde ayer.",
        "category": "Hardware", "priority": "Media"}, headers=headers(token)).json()

    for ticket, codigo in ((propio, 403), (ajeno, 404)):
        resp = client.patch(
            f"/api/tickets/{ticket['id']}/state",
            json={"state": "En proceso"},
            headers=headers(token),
        )
        assert resp.status_code == codigo


def test_solicitante_cannot_create_user(client):
    """Un Solicitante no puede crear usuarios."""
    token = register_requester(client)

    resp = client.post(
        "/api/users",
        json={"password": "clave12345", "name": "Nuevo", "email": "nuevo@correo.local"},
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


def test_solicitante_can_read_and_comment_own_ticket(client):
    """Un Solicitante autenticado sí puede crear, listar, leer y comentar
    sus propios tickets."""
    token = register_requester(client)
    resp = client.post("/api/tickets", json=VALID_TICKET, headers=headers(token))
    assert resp.status_code == 201
    ticket = resp.json()

    listing = client.get("/api/tickets", headers=headers(token))
    assert listing.status_code == 200
    assert [t["id"] for t in listing.json()] == [ticket["id"]]
    assert (
        client.get(f"/api/tickets/{ticket['id']}", headers=headers(token)).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/tickets/{ticket['id']}/history", headers=headers(token)
        ).status_code
        == 200
    )
    resp = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Consulta del solicitante"},
        headers=headers(token),
    )
    assert resp.status_code == 201


def login_role(client, session, role: str, email: str) -> str:
    """Create a user with ``role`` and return a token obtained via login."""
    from backend.auth import hash_password

    make_role_user(session, role, email, hash_password("clave12345"))
    login = client.post(
        "/api/auth/login", json={"email": email, "password": "clave12345"}
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_admin_can_update_and_assign(client, auth_client, session):
    """Un Administrador edita y asigna tickets."""
    token = login_role(
        client, session, UserRole.ADMIN.value, "admin.test@correo.local"
    )
    ticket = create_ticket(auth_client)

    resp = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Editado por el administrador"},
        headers=headers(token),
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
        headers=headers(token),
    )
    assert resp.status_code == 200


def test_tecnico_changes_state_but_cannot_edit_or_assign(client, auth_client, session):
    """Un Técnico cambia el estado, pero no edita ni asigna tickets."""
    token = login_role(
        client, session, UserRole.TECHNICIAN.value, "tecnico.estado@correo.local"
    )
    ticket = create_ticket(auth_client)

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/state",
        json={"state": "En proceso"},
        headers=headers(token),
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"title": "Editado por técnico"},
        headers=headers(token),
    )
    assert resp.status_code == 403

    resp = client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": None},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_admin_can_comment_and_read_global_history(auth_client):
    """El Administrador tiene permisos completos: comenta y ve el historial."""
    ticket = create_ticket(auth_client)

    resp = auth_client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "Comentario del administrador"},
    )
    assert resp.status_code == 201
    assert auth_client.get(f"/api/tickets/{ticket['id']}/comments").status_code == 200
    assert auth_client.get("/api/history").status_code == 200


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
        json={"password": "clave12345", "name": "Nuevo", "email": "nuevo.tecnico@correo.local"},
        headers=headers(token),
    )
    assert resp.status_code == 403


def test_inactive_user_cannot_login(client, auth_client, session):
    """Un usuario desactivado no puede iniciar sesión (regla existente)."""
    from backend.auth import hash_password
    from backend.models import User

    user_id = make_role_user(
        session,
        UserRole.TECHNICIAN.value,
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
# 3. Propiedad: el Solicitante solo accede a los tickets que creó
# ---------------------------------------------------------------------------


def test_ticket_records_its_creator(auth_client):
    """``POST /api/tickets`` guarda al usuario autenticado como creador."""
    me = auth_client.get("/api/auth/me").json()
    ticket = create_ticket(auth_client)
    assert ticket["created_by_id"] == me["id"]


@pytest.mark.parametrize(
    "method, suffix, body",
    [
        ("GET", "", None),
        ("GET", "/history", None),
        ("GET", "/comments", None),
        ("POST", "/comments", {"content": "Intento en ticket ajeno"}),
    ],
)
def test_solicitante_cannot_access_other_tickets(client, auth_client, method, suffix, body):
    """Un ticket creado por otra persona responde 404 al Solicitante."""
    ticket = create_ticket(auth_client)
    token = register_requester(client)

    resp = client.request(
        method,
        f"/api/tickets/{ticket['id']}{suffix}",
        json=body,
        headers=headers(token),
    )
    assert resp.status_code == 404


def test_solicitante_listing_only_shows_own_tickets(client, auth_client):
    """El listado del Solicitante excluye los tickets ajenos."""
    create_ticket(auth_client)
    token = register_requester(client)
    own = client.post("/api/tickets", json=VALID_TICKET, headers=headers(token))
    assert own.status_code == 201

    listing = client.get("/api/tickets", headers=headers(token)).json()
    assert [t["id"] for t in listing] == [own.json()["id"]]

    # El resto de roles sigue viendo todos los tickets.
    assert len(auth_client.get("/api/tickets").json()) == 2
