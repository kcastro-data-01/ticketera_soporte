"""Tests for authentication endpoints: password login (only with
``LOGIN_LOCAL``, development) and me. The Microsoft login is tested in
test_login_microsoft.py."""

import pytest
from sqlalchemy import select

from backend.auth import hash_password
from backend.models import User


def _usuario(session, email, password, name="Login User", role="Solicitante"):
    session.add(User(name=name, email=email, role=role, password_hash=hash_password(password)))
    session.commit()


# --- Login ---


def test_login_success(client, session):
    """Successful login returns a valid token."""
    _usuario(session, "login@test.com", "mypassword")

    resp = client.post(
        "/api/auth/login",
        json={"email": "login@test.com", "password": "mypassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password_returns_401(client, session):
    """Login with wrong password returns 401."""
    _usuario(session, "login2@test.com", "correctpass")

    resp = client.post(
        "/api/auth/login",
        json={"email": "login2@test.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_nonexistent_email_returns_401(client):
    """Login with an email that doesn't exist returns 401."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@test.com", "password": "somepass"},
    )
    assert resp.status_code == 401


def test_login_user_without_password_returns_401(client, session):
    """A legacy user stored without password cannot login."""
    from backend.models import User

    session.add(User(name="No Pass User", email="nopass@test.com", role="Técnico"))
    session.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": "nopass@test.com", "password": "anypass"},
    )
    assert resp.status_code == 401


def test_user_created_by_admin_can_login(auth_client, client):
    """POST /api/users stores the password so the new user can log in."""
    created = auth_client.post(
        "/api/users",
        json={
            "name": "Nueva Persona",
            "email": "nueva@tec.local",
            "role": "Técnico",
            "password": "clave2026",
        },
    )
    assert created.status_code == 201
    assert "password" not in created.json()

    resp = client.post(
        "/api/auth/login",
        json={"email": "nueva@tec.local", "password": "clave2026"},
    )
    assert resp.status_code == 200


def test_user_can_be_created_without_password(auth_client, session):
    """Con la cuenta de Microsoft no hace falta contraseña."""
    resp = auth_client.post("/api/users", json={"name": "Sin Clave", "email": "sinclave@tec.local"})
    assert resp.status_code == 201
    assert session.scalar(select(User).where(User.email == "sinclave@tec.local")).password_hash is None


@pytest.mark.parametrize(
    "extra",
    [{"password": "12345"}, {"password": "x" * 73}],
    ids=["muy-corta", "muy-larga"],
)
def test_create_user_rejects_an_invalid_password(auth_client, extra):
    resp = auth_client.post(
        "/api/users",
        json={"name": "Sin Clave", "email": "sinclave@tec.local", **extra},
    )
    assert resp.status_code == 422


def test_admin_can_reset_a_user_password(auth_client, client):
    """PATCH /api/users/{id} with ``password`` replaces the login password."""
    created = auth_client.post(
        "/api/users",
        json={"name": "Olvido", "email": "olvido@tec.local", "password": "vieja123"},
    ).json()

    resp = auth_client.patch(f"/api/users/{created['id']}", json={"password": "nueva456"})
    assert resp.status_code == 200

    old = client.post("/api/auth/login", json={"email": "olvido@tec.local", "password": "vieja123"})
    new = client.post("/api/auth/login", json={"email": "olvido@tec.local", "password": "nueva456"})
    assert old.status_code == 401
    assert new.status_code == 200


# --- Me ---


def test_me_with_valid_token(client, session):
    """GET /me returns the current user's info when token is valid."""
    _usuario(session, "me@test.com", "pass123456", name="Me Test", role="Administrador")
    token = client.post("/api/auth/login", json={"email": "me@test.com", "password": "pass123456"}).json()["access_token"]

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "me@test.com"
    assert data["name"] == "Me Test"
    assert data["role"] == "Administrador"


def test_me_without_token_returns_error(client):
    """GET /me without a token returns 401."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    """GET /me with an invalid token returns 401."""
    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalidtoken123"},
    )
    assert resp.status_code == 401


def test_me_with_expired_token_returns_401(client):
    """GET /me with an expired token returns 401."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from backend.auth import JWT_SECRET_KEY

    # Create an expired token
    payload = {
        "sub": "1",
        "role": "Solicitante",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    expired_token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


# --- Password hashing ---


def test_password_is_hashed_in_database(session, auth_client):
    """Passwords are stored as bcrypt hashes, not plain text."""
    auth_client.post(
        "/api/users",
        json={"name": "Hash Test", "email": "hash@test.com", "password": "mysecret"},
    )

    user = session.scalar(select(User).where(User.email == "hash@test.com"))
    assert user is not None
    assert user.password_hash is not None
    assert user.password_hash != "mysecret"
    assert user.password_hash.startswith("$2b$")  # bcrypt prefix


# --- Migration ---


def test_migration_adds_password_hash_column(engine):
    """The password_hash column exists after init_db runs."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("users")]
    assert "password_hash" in columns


# --- Sin LOGIN_LOCAL (por defecto): solo Microsoft ---


def test_password_login_is_off_by_default(client, session, monkeypatch):
    monkeypatch.delenv("LOGIN_LOCAL")
    _usuario(session, "local@test.com", "mypassword")
    resp = client.post("/api/auth/login", json={"email": "local@test.com", "password": "mypassword"})
    assert resp.status_code == 404
    monkeypatch.setenv("LOGIN_LOCAL", "false")
    assert client.post("/api/auth/login", json={"email": "local@test.com", "password": "mypassword"}).status_code == 404
    assert client.get("/api/auth/config").json()["login_local"] is False


def test_password_login_works_with_login_local(client, session, monkeypatch):
    monkeypatch.setenv("LOGIN_LOCAL", "true")
    _usuario(session, "local@test.com", "mypassword")
    assert client.post("/api/auth/login", json={"email": "local@test.com", "password": "mypassword"}).status_code == 200
    assert client.get("/api/auth/config").json()["login_local"] is True


@pytest.mark.parametrize("metodo, ruta", [
    ("post", "/api/auth/register"), ("get", "/api/auth/setup"), ("post", "/api/auth/change-password"),
])
def test_registration_and_password_change_no_longer_exist(client, metodo, ruta):
    resp = getattr(client, metodo)(ruta, json={}) if metodo == "post" else client.get(ruta)
    assert resp.status_code in (404, 405)
