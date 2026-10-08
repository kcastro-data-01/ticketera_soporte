"""Tests for the DATABASE_URL environment configuration (Task 15)."""

from backend import database


def test_default_url_keeps_the_project_root_file():
    assert database.DEFAULT_DATABASE_URL == (
        f"sqlite:///{database.PROJECT_ROOT}/ticketera.db"
    )


def test_database_url_env_var_is_used_when_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/ticketera.db")

    assert database.resolve_database_url() == "sqlite:////data/ticketera.db"


def test_plain_path_env_var_is_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "/data/ticketera.db")

    assert database.resolve_database_url() == "sqlite:////data/ticketera.db"


def test_blank_env_var_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")

    assert database.resolve_database_url() == database.DEFAULT_DATABASE_URL


def test_missing_env_var_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert database.resolve_database_url() == database.DEFAULT_DATABASE_URL


def test_explicit_value_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/volume.db")

    assert (
        database.resolve_database_url("sqlite:////other.db")
        == "sqlite:////other.db"
    )


def test_module_url_matches_the_resolution_at_import_time(monkeypatch):
    """The engine built at import honours the same resolution rules."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert database.DATABASE_URL == database.resolve_database_url()
    assert database.DATABASE_URL == database.DEFAULT_DATABASE_URL
