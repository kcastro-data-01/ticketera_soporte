"""Shared pytest fixtures: a temporary SQLite database per test."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, enable_sqlite_foreign_keys, get_session
from backend.main import app


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


@pytest.fixture
def client(session):
    """FastAPI test client whose requests use the temporary test database."""
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
