"""Tests for user creation and listing (Task 8: RF4)."""

import pytest
from sqlalchemy.orm import sessionmaker

from backend.constants import UserRole
from backend.models import User

VALID_USER = {
    "name": "Ana Pérez",
    "email": "ana@soporte.local",
    "role": UserRole.SUPPORT.value,
}

USER_RESPONSE_KEYS = {"id", "name", "email", "role"}


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_create_user_returns_201(client):
    response = client.post("/api/users", json=VALID_USER)

    assert response.status_code == 201


def test_create_user_response_contains_sent_data(client):
    response = client.post("/api/users", json=VALID_USER)
    data = response.json()

    assert data["id"] is not None
    assert data["name"] == VALID_USER["name"]
    assert data["email"] == VALID_USER["email"]
    assert data["role"] == VALID_USER["role"]


def test_create_user_with_blank_name_returns_422(client):
    response = client.post("/api/users", json={**VALID_USER, "name": "   "})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "invalid_email",
    ["notanemail", "sin-arroba.local", "a@b", "@sin-local.com"],
    ids=["no-at", "no-at-2", "no-dot", "no-local"],
)
def test_create_user_with_invalid_email_returns_422(client, invalid_email):
    response = client.post("/api/users", json={**VALID_USER, "email": invalid_email})

    assert response.status_code == 422


def test_create_user_with_invalid_role_returns_422(client):
    response = client.post("/api/users", json={**VALID_USER, "role": "SuperUsuario"})

    assert response.status_code == 422


def test_create_user_with_duplicate_email_returns_409(client):
    client.post("/api/users", json=VALID_USER)

    response = client.post(
        "/api/users",
        json={**VALID_USER, "name": "Otra Persona"},
    )

    assert response.status_code == 409


def test_duplicate_email_does_not_create_a_second_user(client, engine):
    client.post("/api/users", json=VALID_USER)
    client.post("/api/users", json={**VALID_USER, "name": "Otra Persona"})

    fresh_session = sessionmaker(bind=engine)()
    try:
        assert fresh_session.query(User).count() == 1
    finally:
        fresh_session.close()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_users_returns_200(client):
    client.post("/api/users", json=VALID_USER)
    client.post(
        "/api/users",
        json={**VALID_USER, "name": "Luis Gómez", "email": "luis@soporte.local"},
    )

    response = client.get("/api/users")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_users_response_structure(client):
    client.post("/api/users", json=VALID_USER)

    data = client.get("/api/users").json()

    assert len(data) == 1
    user = data[0]
    assert set(user.keys()) == USER_RESPONSE_KEYS
    assert isinstance(user["id"], int)
    assert isinstance(user["name"], str)
    assert isinstance(user["email"], str)
    assert user["role"] == UserRole.SUPPORT.value


def test_list_users_is_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/users" in schema["paths"]
    assert "post" in schema["paths"]["/api/users"]
    assert "get" in schema["paths"]["/api/users"]
