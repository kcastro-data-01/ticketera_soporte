"""Tests for the configuration endpoint (read-only system constants)."""

from backend.constants import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
    USER_ROLES,
)

CONFIG_KEYS = {"categories", "states", "priorities", "roles", "ia_disponible"}


def test_config_returns_200(client):
    response = client.get("/api/config")

    assert response.status_code == 200


def test_config_exposes_the_expected_keys(client):
    response = client.get("/api/config")

    assert set(response.json()) == CONFIG_KEYS


def test_config_categories_match_backend_constants(client):
    response = client.get("/api/config")

    assert response.json()["categories"] == list(TICKET_CATEGORIES)


def test_config_states_match_backend_constants(client):
    response = client.get("/api/config")

    assert response.json()["states"] == list(TICKET_STATES)


def test_config_priorities_match_backend_constants(client):
    response = client.get("/api/config")

    assert response.json()["priorities"] == list(TICKET_PRIORITIES)


def test_config_roles_match_backend_constants(client):
    response = client.get("/api/config")

    assert response.json()["roles"] == list(USER_ROLES)


def test_config_is_read_only(client):
    response = client.get("/api/config")

    assert response.status_code == 200
    assert client.post("/api/config").status_code == 405
    assert client.patch("/api/config").status_code == 405
    assert client.delete("/api/config").status_code == 405
