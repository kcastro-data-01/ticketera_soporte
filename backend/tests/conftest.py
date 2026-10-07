"""Shared pytest fixtures: a temporary SQLite database per test."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, enable_sqlite_foreign_keys


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
