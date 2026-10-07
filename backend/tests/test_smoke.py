"""Smoke tests for the API health check (Task 3)."""

from fastapi.testclient import TestClient

from backend.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_response_is_json():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["content-type"].startswith("application/json")


def test_app_exposes_openapi_schema():
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
