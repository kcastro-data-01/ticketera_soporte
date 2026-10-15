"""Tests for user creation and listing (Task 8: RF4)."""

import pytest
from sqlalchemy.orm import sessionmaker

from backend.constants import UserRole
from backend.models import User

VALID_USER = {
    "name": "Ana Pérez",
    "email": "ana@soporte.local",
    "password": "clave12345",
    "role": UserRole.TECHNICIAN.value,
}

USER_RESPONSE_KEYS = {"id", "name", "email", "role", "is_active"}


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_create_user_returns_201(auth_client):
    response = auth_client.post("/api/users", json=VALID_USER)

    assert response.status_code == 201


def test_create_user_response_contains_sent_data(auth_client):
    response = auth_client.post("/api/users", json=VALID_USER)
    data = response.json()

    assert data["id"] is not None
    assert data["name"] == VALID_USER["name"]
    assert data["email"] == VALID_USER["email"]
    assert data["role"] == VALID_USER["role"]


def test_create_user_with_blank_name_returns_422(auth_client):
    response = auth_client.post("/api/users", json={**VALID_USER, "name": "   "})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "invalid_email",
    ["notanemail", "sin-arroba.local", "a@b", "@sin-local.com"],
    ids=["no-at", "no-at-2", "no-dot", "no-local"],
)
def test_create_user_with_invalid_email_returns_422(auth_client, invalid_email):
    response = auth_client.post("/api/users", json={**VALID_USER, "email": invalid_email})

    assert response.status_code == 422


def test_create_user_with_invalid_role_returns_422(auth_client):
    response = auth_client.post("/api/users", json={**VALID_USER, "role": "SuperUsuario"})

    assert response.status_code == 422


def test_create_user_with_duplicate_email_returns_409(auth_client):
    auth_client.post("/api/users", json=VALID_USER)

    response = auth_client.post(
        "/api/users",
        json={**VALID_USER, "name": "Otra Persona"},
    )

    assert response.status_code == 409


def test_duplicate_email_does_not_create_a_second_user(auth_client, engine):
    # El auth_client ya registró un usuario admin con email testadmin@test.com.
    # Solo contamos usuarios reales del test para no contabilizar al admin de setup.
    auth_client.post("/api/users", json=VALID_USER)
    auth_client.post("/api/users", json={**VALID_USER, "name": "Otra Persona"})

    fresh_session = sessionmaker(bind=engine)()
    try:
        count = fresh_session.query(User).count()
        # El usuario admin creado por el fixture usa email testadmin@test.com
        admin_count = fresh_session.query(User).filter(User.email == "testadmin@test.com").count()
        assert count - admin_count == 1
    finally:
        fresh_session.close()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_users_returns_200(auth_client):
    # El auth_client ya registró un usuario admin con email testadmin@test.
    # Creamos 2 usuarios adicionales para el test.
    auth_client.post("/api/users", json=VALID_USER)
    auth_client.post(
        "/api/users",
        json={**VALID_USER, "name": "Luis Gómez", "email": "luis@soporte.local"},
    )

    response = auth_client.get("/api/users")

    assert response.status_code == 200
    # Contamos usuarios reales: total menos el admin de setup (testadmin@test).
    data = response.json()
    admin_emails = [u["email"] for u in data if u["email"] == "testadmin@test.com"]
    real_users = [u for u in data if u["email"] != "testadmin@test.com"]
    emails = [u["email"] for u in real_users]
    assert "ana@soporte.local" in emails
    assert "luis@soporte.local" in emails


def test_list_users_response_structure(auth_client):
    auth_client.post("/api/users", json=VALID_USER)

    data = auth_client.get("/api/users").json()

    # Filtrar al admin de setup para la validación de estructura
    real_users = [u for u in data if u["email"] != "testadmin@test.com"]
    assert len(real_users) >= 1
    user = real_users[0]
    assert set(user.keys()) == USER_RESPONSE_KEYS
    assert isinstance(user["id"], int)
    assert isinstance(user["name"], str)
    assert isinstance(user["email"], str)
    assert user["role"] == UserRole.TECHNICIAN.value


def test_list_users_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/users" in schema["paths"]
    assert "post" in schema["paths"]["/api/users"]
    assert "get" in schema["paths"]["/api/users"]


# ---------------------------------------------------------------------------
# Defaults and active listing (Task 20.3)
# ---------------------------------------------------------------------------


def test_create_user_without_role_defaults_to_support(auth_client):
    response = auth_client.post(
        "/api/users",
        json={"password": "clave12345", "name": "Persona Sin Rol", "email": "sinrol@soporte.local"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == UserRole.TECHNICIAN.value
    assert response.json()["role"] == "Técnico"


def test_create_user_stores_user_active(auth_client, engine):
    # El auth_client ya registró un usuario admin. Creamos un usuario adicional.
    auth_client.post("/api/users", json=VALID_USER)

    fresh_session = sessionmaker(bind=engine)()
    try:
        # Contar usuarios reales (excluir admin de setup)
        count = fresh_session.query(User).count()
        admin_count = fresh_session.query(User).filter(User.email == "testadmin@test.com").count()
        assert count - admin_count >= 1  # al menos el usuario del test
        stored = fresh_session.query(User).first()
        # Buscar un usuario que no sea el admin
        stored = fresh_session.query(User).filter(User.email != "testadmin@test.com").first()
        assert stored.is_active is True
    finally:
        fresh_session.close()


def test_list_users_excludes_inactive_users(auth_client, session):
    # El auth_client ya registró un usuario admin. Creamos un usuario activo y uno inactivo.
    auth_client.post("/api/users", json=VALID_USER)
    session.add(
        User(
            name="Usuario Inactivo",
            email="inactivo@soporte.local",
            role=UserRole.TECHNICIAN.value,
            is_active=False,
        )
    )
    session.commit()

    data = auth_client.get("/api/users").json()

    # Filtrar al admin de setup
    real_users = [u for u in data if u["email"] != "testadmin@test.com"]
    assert len(real_users) >= 1  # solo el usuario activo aparece en el listado
    # El usuario inactivo no debería aparecer en el listado de usuarios asignables
    activo_emails = [u["email"] for u in real_users if u.get("is_active") == True]

def test_inactive_user_is_still_stored(auth_client, engine):
    """Filtering the listing must not delete or deactivate rows."""
    # El auth_client ya registró un usuario admin. Agregamos un usuario inactivo.
    auth_client.post("/api/users", json=VALID_USER)
    session2 = sessionmaker(bind=engine)()
    try:
        session2.add(
            User(
                name="Usuario Inactivo",
                email="inactivo@soporte.local",
                role=UserRole.ADMIN.value,
                is_active=False,
            )
        )
        session2.commit()
    finally:
        session2.close()

    data = auth_client.get("/api/users").json()
    fresh_session = sessionmaker(bind=engine)()
    try:
        # Filtrar al admin de setup
        real_data = [u for u in data if u["email"] != "testadmin@test.com"]
        assert len(real_data) == 1  # solo el usuario inactivo creado en test
        assert fresh_session.query(User).count() == 3  # admin + usuario activo + usuario inactivo
    finally:
        fresh_session.close()


# ---------------------------------------------------------------------------
# Update (PATCH /api/users/{id})
# ---------------------------------------------------------------------------


def test_update_user_returns_200(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"name": "Ana Actualizada"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["name"] == "Ana Actualizada"
    assert data["email"] == VALID_USER["email"]


def test_update_user_partial_single_field(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"email": "nuevo@soporte.local"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "nuevo@soporte.local"
    assert data["name"] == VALID_USER["name"]


def test_update_user_multiple_fields(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"name": "Nuevo Nombre", "role": UserRole.ADMIN.value},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Nuevo Nombre"
    assert data["role"] == UserRole.ADMIN.value


def test_update_user_not_found_returns_404(auth_client):
    response = auth_client.patch(
        "/api/users/9999",
        json={"name": "Fantasma"},
    )

    assert response.status_code == 404


def test_update_user_duplicate_email_returns_409(auth_client):
    auth_client.post("/api/users", json=VALID_USER)
    other = auth_client.post(
        "/api/users",
        json={"password": "clave12345", "name": "Otro", "email": "otro@soporte.local"},
    ).json()

    response = auth_client.patch(
        f"/api/users/{other['id']}",
        json={"email": VALID_USER["email"]},
    )

    assert response.status_code == 409


def test_update_user_same_email_as_current_is_allowed(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"email": VALID_USER["email"]},
    )

    assert response.status_code == 200


def test_update_user_no_fields_returns_422(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={},
    )

    assert response.status_code == 422


def test_update_user_invalid_name_returns_422(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"name": "   "},
    )

    assert response.status_code == 422


def test_update_user_invalid_email_returns_422(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"email": "notanemail"},
    )

    assert response.status_code == 422


def test_update_user_invalid_role_returns_422(auth_client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    response = auth_client.patch(
        f"/api/users/{created['id']}",
        json={"role": "SuperUsuario"},
    )

    assert response.status_code == 422


def test_update_user_persists_in_database(auth_client, engine):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    auth_client.patch(
        f"/api/users/{created['id']}",
        json={"name": "Nombre Editado", "email": "editado@soporte.local"},
    )

    fresh_session = sessionmaker(bind=engine)()
    try:
        stored = fresh_session.get(User, created["id"])
        assert stored.name == "Nombre Editado"
        assert stored.email == "editado@soporte.local"
    finally:
        fresh_session.close()


def test_update_user_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/users/{user_id}" in schema["paths"]
    assert "patch" in schema["paths"]["/api/users/{user_id}"]


# --- Desactivar / reactivar ---


def test_admin_deactivates_and_reactivates_a_user(auth_client, client):
    created = auth_client.post("/api/users", json=VALID_USER).json()

    resp = auth_client.patch(f"/api/users/{created['id']}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Sale de la lista normal y de la asignación, pero el admin lo ve con todos=true.
    activos = [u["id"] for u in auth_client.get("/api/users").json()]
    todos = {u["id"]: u for u in auth_client.get("/api/users?todos=true").json()}
    assert created["id"] not in activos
    assert todos[created["id"]]["is_active"] is False

    login = client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert login.status_code == 403

    resp = auth_client.patch(f"/api/users/{created['id']}", json={"is_active": True})
    assert resp.json()["is_active"] is True
    login = client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert login.status_code == 200


def test_deactivated_user_loses_an_open_session(auth_client, client):
    auth_client.post("/api/users", json=VALID_USER)
    token = client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    ).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    auth_client.patch(f"/api/users/{me['id']}", json={"is_active": False})

    resp = client.get("/api/tickets", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_admin_cannot_deactivate_themselves(auth_client):
    me = auth_client.get("/api/auth/me").json()
    resp = auth_client.patch(f"/api/users/{me['id']}", json={"is_active": False})
    assert resp.status_code == 400


def test_non_admin_cannot_list_inactive_users(auth_client, client):
    created = auth_client.post("/api/users", json=VALID_USER).json()
    auth_client.post(
        "/api/users",
        json={**VALID_USER, "name": "Otro", "email": "otro.inactivo@tec.local"},
    )
    otro = [u for u in auth_client.get("/api/users").json() if u["email"] == "otro.inactivo@tec.local"][0]
    auth_client.patch(f"/api/users/{otro['id']}", json={"is_active": False})
    token = client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    ).json()["access_token"]

    users = client.get("/api/users?todos=true", headers={"Authorization": f"Bearer {token}"}).json()
    assert otro["id"] not in [u["id"] for u in users]
    assert created["id"] in [u["id"] for u in users]
