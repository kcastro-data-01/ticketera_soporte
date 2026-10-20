"""Shared pytest fixtures: a temporary SQLite database per test."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, enable_sqlite_foreign_keys, get_session
from backend.main import app


@pytest.fixture(autouse=True)
def respuestas_fijas(monkeypatch):
    """Por defecto el chat responde los conteos con el texto fijo; las
    pruebas de la redacción con IA la encienden."""
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "false")


@pytest.fixture
def engine(tmp_path):
    """Create a fresh SQLite engine with the full schema for each test."""
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine):
    """Provide an open session bound to the temporary test database."""
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = testing_session()
    yield db
    db.close()


class AuthenticatedClient:
    """Wrapper around TestClient that automatically adds auth headers."""

    def __init__(self, client, token):
        self._client = client
        self._token = token

    def _headers(self, kwargs):
        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def get(self, url, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self._client.post(url, **kwargs)

    def patch(self, url, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self._client.patch(url, **kwargs)

    def put(self, url, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self._client.put(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self._client.delete(url, **kwargs)

    def __getattr__(self, name):
        return getattr(self._client, name)


@pytest.fixture
def client(session):
    """FastAPI test client whose requests use the temporary test database
    WITHOUT authentication. Use for endpoints that are publicly accessible
    (health check, listing tickets, etc.)."""
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_public(session):
    """FastAPI test client whose requests use the temporary test database
    WITHOUT authentication. Alias for ``client`` for clarity in tests
    that explicitly need a public client."""
    return client(session)


@pytest.fixture
def auth_client(client, session):
    """FastAPI test client with automatic authentication.

    Registers a user and wraps the client to include the Bearer token
    in all requests. Use this for tests that hit protected endpoints.
    """
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Test Admin",
            "email": "testadmin@test.com",
            "password": "testpass123",
            "role": "Administrador",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return AuthenticatedClient(client, token)


@pytest.fixture
def auth_token(client):
    """Register a user and return a valid access token for testing."""
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Test Admin",
            "email": "testadmin@test.com",
            "password": "testpass123",
            "role": "Administrador",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with the Authorization Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}
