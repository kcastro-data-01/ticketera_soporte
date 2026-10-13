"""Tests for authentication endpoints (login, register, me)."""

import pytest
from sqlalchemy import func, select

from backend.models import User


# --- Register ---


def test_register_first_user_can_be_admin(client):
    """First user to register can choose their role (Administrador)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Admin User",
            "email": "admin@test.com",
            "password": "securepass123",
            "role": "Administrador",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_register_second_user_forced_to_requester(client):
    """Second registration is forced to Solicitante role regardless of what they send."""
    # Create first user
    client.post(
        "/api/auth/register",
        json={
            "name": "First User",
            "email": "first@test.com",
            "password": "pass123456",
            "role": "Administrador",
        },
    )

    # Second user tries to be Soporte
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Second User",
            "email": "second@test.com",
            "password": "pass123456",
            "role": "Soporte",
        },
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()

    # Verify the user was created as Solicitante
    me_resp = client.get(f"/api/auth/me?token={resp.json()['access_token']}")
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "Solicitante"


def test_register_duplicate_email_returns_409(client):
    """Registering with an already-used email returns 409 Conflict."""
    client.post(
        "/api/auth/register",
        json={
            "name": "User One",
            "email": "dup@test.com",
            "password": "pass123456",
        },
    )

    resp = client.post(
        "/api/auth/register",
        json={
            "name": "User Two",
            "email": "dup@test.com",
            "password": "pass123456",
        },
    )
    assert resp.status_code == 409


def test_register_without_role_defaults_to_requester(client):
    """If no role is provided, default to Solicitante."""
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "No Role User",
            "email": "norole@test.com",
            "password": "pass123456",
        },
    )
    assert resp.status_code == 201

    me_resp = client.get(f"/api/auth/me?token={resp.json()['access_token']}")
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "Solicitante"


def test_register_weak_password_returns_422(client):
    """Passwords shorter than 6 characters are rejected."""
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Weak Pass",
            "email": "weak@test.com",
            "password": "123",
        },
    )
    assert resp.status_code == 422


# --- Login ---


def test_login_success(client):
    """Successful login returns a valid token."""
    client.post(
        "/api/auth/register",
        json={
            "name": "Login User",
            "email": "login@test.com",
            "password": "mypassword",
        },
    )

    resp = client.post(
        "/api/auth/login",
        json={"email": "login@test.com", "password": "mypassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password_returns_401(client):
    """Login with wrong password returns 401."""
    client.post(
        "/api/auth/register",
        json={
            "name": "Login User",
            "email": "login2@test.com",
            "password": "correctpass",
        },
    )

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


def test_login_user_without_password_returns_401(client):
    """A user created via /api/users (no password) cannot login."""
    # Create user via the old endpoint (no password)
    client.post(
        "/api/users",
        json={"name": "No Pass User", "email": "nopass@test.com"},
    )

    resp = client.post(
        "/api/auth/login",
        json={"email": "nopass@test.com", "password": "anypass"},
    )
    assert resp.status_code == 401


# --- Me ---


def test_me_with_valid_token(client):
    """GET /me returns the current user's info when token is valid."""
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "name": "Me Test",
            "email": "me@test.com",
            "password": "pass123456",
            "role": "Administrador",
        },
    )
    token = reg_resp.json()["access_token"]

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


def test_password_is_hashed_in_database(session, client):
    """Passwords are stored as bcrypt hashes, not plain text."""
    client.post(
        "/api/auth/register",
        json={
            "name": "Hash Test",
            "email": "hash@test.com",
            "password": "mysecret",
        },
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
