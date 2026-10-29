"""Preguntas sobre USUARIOS («¿cuántos administradores hay?», «¿quiénes son
los técnicos?»): las responde el servidor, sin IA, con los usuarios activos de
la base. Administrador y Técnico ven cantidad y nombres; el Solicitante, solo
la cantidad. «¿cuántos tickets tiene el administrador?» sigue contando tickets.

En producción «cuantos administradores hay» respondía «¿Qué tickets desea que
cuente?»."""

import pytest

from backend.models import Ticket, User
from backend.services.asistente_service import NO_ENTENDI, build_context, pide_usuarios
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401


@pytest.fixture
def equipo(session):
    """2 administradores y 3 técnicos activos (más uno desactivado de cada uno)
    y 2 solicitantes. Quien pregunta se agrega con ``login_as``."""
    gente = [
        ("Laura Méndez", "Administrador", True), ("Mario Rojas", "Administrador", True),
        ("Viejo Admin", "Administrador", False),
        ("José Solano", "Técnico", True), ("Carlos Solís", "Técnico", True),
        ("Ana Vargas", "Técnico", True), ("Técnico Retirado", "Técnico", False),
        ("Pedro Mora", "Solicitante", True), ("Sofía Arias", "Solicitante", True),
    ]
    for n, (nombre, rol, activo) in enumerate(gente):
        session.add(User(name=nombre, email=f"u{n}@data.cr", role=rol, password_hash="x",
                         is_active=activo))
    session.commit()


@pytest.fixture
def admin(client, session, equipo):
    return login_as(client, session, "Administrador", "kc@data.cr", "Kristin Castro")


@pytest.fixture
def tecnico(client, session, equipo):
    return login_as(client, session, "Técnico", "tec@data.cr", "Luis Mora")


@pytest.fixture
def solicitante(client, session, equipo):
    return login_as(client, session, "Solicitante", "sol@data.cr", "Andrea Castillo")


def _sin_ia(ia):
    assert ia.interpretaciones == [] and ia.calls == []


@pytest.mark.parametrize("pregunta", ["cuantos administradores hay", "¿Cuántos administradores hay?",
                                      "cuantos administradroes hay?", "cuatos admins ay"])
def test_how_many_admins(client, ia, admin, pregunta):
    respuesta = _respuesta(ask(client, admin, pregunta), "directa")
    # Los 2 del equipo y quien pregunta; el desactivado no cuenta.
    assert respuesta == "Hay **3** administradores activos: Kristin Castro, Laura Méndez y Mario Rojas."
    assert respuesta not in NO_ENTENDI
    _sin_ia(ia)


@pytest.mark.parametrize("pregunta", ["cuantos tecnicos hay", "cuántos técnicos hay?", "cuantos tecnicso hay"])
def test_how_many_technicians(client, ia, admin, pregunta):
    respuesta = _respuesta(ask(client, admin, pregunta), "directa")
    assert respuesta == "Hay **3** técnicos activos: Ana Vargas, Carlos Solís y José Solano."
    _sin_ia(ia)


@pytest.mark.parametrize("pregunta", ["cuantos usuarios hay", "cuantos usuraios hay en total?"])
def test_how_many_users(client, ia, admin, pregunta):
    respuesta = _respuesta(ask(client, admin, pregunta), "directa")
    assert respuesta.splitlines() == [
        "Hay **8** usuarios activos: **3** administradores, **3** técnicos y **2** solicitantes.",
        "- Administradores: Kristin Castro, Laura Méndez y Mario Rojas",
        "- Técnicos: Ana Vargas, Carlos Solís y José Solano",
        "- Solicitantes: Pedro Mora y Sofía Arias",
    ]
    _sin_ia(ia)


@pytest.mark.parametrize("pregunta", ["quienes son los tecnicos", "¿Quiénes son los técnicos?",
                                      "quienes son los tecnico"])
def test_who_are_the_technicians_for_a_technician(client, ia, tecnico, pregunta):
    respuesta = _respuesta(ask(client, tecnico, pregunta), "directa")
    assert respuesta == ("Hay **4** técnicos activos: Ana Vargas, Carlos Solís, José Solano y "
                         "Luis Mora.")
    _sin_ia(ia)


@pytest.mark.parametrize("pregunta", ["dame los nombres de administradores",
                                      "dame los nombres de los administradores",
                                      "nombres de los admins"])
def test_admin_names(client, ia, tecnico, pregunta):
    respuesta = _respuesta(ask(client, tecnico, pregunta), "directa")
    assert respuesta == "Hay **2** administradores activos: Laura Méndez y Mario Rojas."
    _sin_ia(ia)


def test_single_and_zero(client, ia, session):
    headers = login_as(client, session, "Técnico", "tec@data.cr", "Luis Mora")
    assert _respuesta(ask(client, headers, "cuantos tecnicos hay"), "directa") == (
        "Hay **1** técnico activo: Luis Mora.")
    assert _respuesta(ask(client, headers, "cuantos administradores hay"), "directa") == (
        "No hay administradores activos en la ticketera.")


def test_tickets_of_the_admin_still_counts_tickets(client, ia, admin, session):
    laura = session.query(User).filter_by(name="Laura Méndez").one()
    ticket = Ticket(title="Servidor caído", description="Descripción", category="Red",
                    priority="Alta", assigned_to_id=laura.id)
    session.add(ticket)
    session.commit()

    respuesta = _respuesta(ask(client, admin, "cuantos tickets tiene el administrador"), "directa")

    assert f"#{ticket.id}" in respuesta and "Laura Méndez" in respuesta
    assert "activos" not in respuesta
    assert pide_usuarios("cuantos tickets tiene el administrador") is None


# --- Solicitante: solo la cantidad ------------------------------------------------


@pytest.mark.parametrize("pregunta,esperada", [
    ("cuantos administradores hay", "Hay **2** administradores activos."),
    ("cuantos tecnicos hay", "Hay **3** técnicos activos."),
    ("cuantos usuarios hay",
     "Hay **8** usuarios activos: **2** administradores, **3** técnicos y **3** solicitantes."),
])
def test_requester_only_gets_the_count(client, ia, solicitante, pregunta, esperada):
    respuesta = _respuesta(ask(client, solicitante, pregunta), "directa")
    assert respuesta == esperada
    _sin_ia(ia)


@pytest.mark.parametrize("pregunta", ["quienes son los tecnicos", "dame los nombres de administradores"])
def test_requester_gets_no_names(client, ia, solicitante, pregunta):
    respuesta = _respuesta(ask(client, solicitante, pregunta), "directa")
    assert "activos." in respuesta
    assert "no tiene acceso a la lista de usuarios" in respuesta
    for nombre in ("Laura", "Mario", "José", "Carlos", "Ana Vargas", "@"):
        assert nombre not in respuesta
    _sin_ia(ia)


# --- No son preguntas de usuarios -------------------------------------------------


@pytest.mark.parametrize("pregunta", [
    "cuantos tickets tiene el administrador",
    "cuantos tienen los tecnicos",
    "que hace un tecnico",
    "como creo un usuario",
    "cuantos roles hay",
    "quien puede asignar tickets",
    "cuantos tickets hay",
])
def test_other_questions_are_not_about_users(pregunta):
    from backend.services.asistente_service import _normalizar
    assert pide_usuarios(_normalizar(pregunta)) is None


# --- Contexto de la IA ------------------------------------------------------------


def test_context_has_real_users_by_role(session, equipo):
    tecnico = User(name="Luis Mora", email="tec@data.cr", role="Técnico", password_hash="x")
    session.add(tecnico)
    session.commit()
    contexto = build_context(session, tecnico)
    assert "Usuarios activos por rol (los únicos que existen; no inventes otros):" in contexto
    assert "- Administradores: 2 (Laura Méndez y Mario Rojas)" in contexto
    assert "- Técnicos: 4 (Ana Vargas, Carlos Solís, José Solano y Luis Mora)" in contexto
    assert "Retirado" not in contexto and "@" not in contexto


def test_requester_context_has_only_counts(session, equipo):
    andrea = User(name="Andrea Castillo", email="sol@data.cr", role="Solicitante", password_hash="x")
    session.add(andrea)
    session.commit()
    contexto = build_context(session, andrea)
    assert "- Administradores: 2" in contexto
    assert "- Técnicos: 3" in contexto
    assert "- Solicitantes: 3" in contexto
    for nombre in ("Laura", "José Solano", "Pedro Mora", "@"):
        assert nombre not in contexto
