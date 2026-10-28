"""La ticketera tiene 3 roles: Administrador, Técnico y Solicitante.

El rol Supervisor se eliminó: sus usuarios pasan a Técnico con una migración
al arrancar, la API lo rechaza con 422, lo que compartía con el Administrador
(editar, asignar, métricas) queda solo para el Administrador, y ni el chat ni
la ayuda lo nombran."""

import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.constants import USER_ROLES
from backend.database import init_db
from backend.migrate_remove_supervisor_role import migrate_remove_supervisor_role
from backend.models import Ticket
from backend.services.asistente_service import (
    DESCRIPCION_ROL,
    GUIA_APP,
    PERMISOS_POR_ROL,
    REGLAS_PARA_IA,
    TRES_ROLES,
)
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401

AYUDA = Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html"
ROLES = ("Administrador", "Técnico", "Solicitante")


def test_there_are_three_roles():
    assert USER_ROLES == ROLES


# --- Migración Supervisor → Técnico -------------------------------------------


def test_migration_moves_supervisors_to_technicians_and_logs_it(tmp_path, caplog):
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), role VARCHAR(30))"))
        conn.execute(text(
            "INSERT INTO users (id, email, role) VALUES "
            "(1, 'marta@data.cr', 'Supervisor'), (2, 'laura@data.cr', 'Administrador'), "
            "(3, 'carlos@data.cr', 'Supervisor'), (4, 'ana@data.cr', 'Solicitante')"
        ))

    with caplog.at_level(logging.WARNING, logger="backend.migrate_remove_supervisor_role"):
        assert migrate_remove_supervisor_role(engine) == 2
    assert "2 usuario(s) pasaron a Técnico (marta@data.cr, carlos@data.cr)" in caplog.text

    caplog.clear()
    assert migrate_remove_supervisor_role(engine) == 0  # idempotente
    assert caplog.text == ""  # sin cambios, sin log

    with engine.connect() as conn:
        roles = conn.execute(text("SELECT role FROM users ORDER BY id")).scalars().all()
    assert roles == ["Técnico", "Administrador", "Técnico", "Solicitante"]
    engine.dispose()


def test_migration_runs_by_itself_on_startup(tmp_path, caplog):
    """``init_db`` (lo que corre al arrancar, en Docker y en Vercel) la aplica."""
    engine = create_engine(f"sqlite:///{tmp_path / 'ticketera.db'}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (name, email, role, is_active) "
            "VALUES ('Marta Rojas', 'marta@data.cr', 'Supervisor', 1)"
        ))

    with caplog.at_level(logging.WARNING, logger="backend.migrate_remove_supervisor_role"):
        init_db(engine)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT role FROM users")).scalar() == "Técnico"
    assert "marta@data.cr" in caplog.text
    engine.dispose()


def test_migration_is_plain_sql_for_sqlite_and_postgres():
    """Solo ``SELECT``/``UPDATE`` con parámetros: sin nada propio de SQLite."""
    fuente = Path(__file__).resolve().parents[1] / "migrate_remove_supervisor_role.py"
    codigo = fuente.read_text(encoding="utf-8")
    assert "UPDATE users SET role = :new WHERE role = :old" in codigo
    assert "PRAGMA" not in codigo and "es_sqlite" not in codigo


# --- La API rechaza el rol Supervisor ----------------------------------------


def test_creating_a_supervisor_is_rejected(auth_client):
    resp = auth_client.post(
        "/api/users", json={"name": "Marta", "email": "marta@data.cr", "role": "Supervisor"}
    )
    assert resp.status_code == 422
    nombres = [u["email"] for u in auth_client.get("/api/users").json()]
    assert "marta@data.cr" not in nombres


def test_changing_a_user_to_supervisor_is_rejected(auth_client):
    creado = auth_client.post(
        "/api/users", json={"name": "Marta", "email": "marta@data.cr", "role": "Técnico"}
    ).json()
    resp = auth_client.patch(f"/api/users/{creado['id']}", json={"role": "Supervisor"})
    assert resp.status_code == 422
    usuario = next(u for u in auth_client.get("/api/users").json() if u["id"] == creado["id"])
    assert usuario["role"] == "Técnico"


# --- Permisos de cada uno de los 3 roles --------------------------------------

# (acción, roles que pueden). La tabla «Permisos por rol» de ayuda.html.
PERMISOS = {
    "editar": {"Administrador"},
    "asignar": {"Administrador"},
    "metricas": {"Administrador"},
    "eliminar": {"Administrador"},
    "usuarios": {"Administrador"},
    "cambiar_estado": {"Administrador", "Técnico"},
    "historial_global": {"Administrador", "Técnico"},
    "explicar_ia": {"Administrador", "Técnico"},
    "crear": set(ROLES),
}


def _ticket(session) -> int:
    ticket = Ticket(title="Impresora", description="No imprime", category="Hardware", priority="Media")
    session.add(ticket)
    session.commit()
    return ticket.id


def _accion(client, session, headers, accion):
    if accion == "crear":
        return client.post("/api/tickets", headers=headers, json={
            "title": "No hay red", "description": "Sin internet", "category": "Red", "priority": "Alta",
        })
    if accion == "metricas":
        return client.get("/api/metricas", headers=headers)
    if accion == "historial_global":
        return client.get("/api/history", headers=headers)
    if accion == "usuarios":
        return client.post("/api/users", headers=headers,
                           json={"name": "Nuevo", "email": "nuevo@data.cr", "role": "Técnico"})
    ticket_id = _ticket(session)
    if accion == "editar":
        return client.patch(f"/api/tickets/{ticket_id}", headers=headers, json={"title": "Editado"})
    if accion == "asignar":
        return client.patch(f"/api/tickets/{ticket_id}/assign", headers=headers, json={"assigned_to_id": None})
    if accion == "cambiar_estado":
        return client.patch(f"/api/tickets/{ticket_id}/state", headers=headers, json={"state": "En proceso"})
    if accion == "eliminar":
        return client.delete(f"/api/tickets/{ticket_id}", headers=headers)
    if accion == "explicar_ia":
        return client.get(f"/api/tickets/{ticket_id}/explicacion", headers=headers)
    raise AssertionError(accion)


@pytest.mark.parametrize("rol", ROLES)
@pytest.mark.parametrize("accion", list(PERMISOS))
def test_permissions_of_each_role(client, session, rol, accion):
    headers = login_as(client, session, rol, "persona@data.cr", "Persona")
    resp = _accion(client, session, headers, accion)
    if rol in PERMISOS[accion]:
        assert resp.status_code in (200, 201, 204), (rol, accion, resp.text)
    else:
        # El Solicitante no ve los tickets ajenos: para él no existen (404).
        assert resp.status_code in (403, 404), (rol, accion, resp.status_code)


# --- Ni el chat ni la ayuda nombran al Supervisor -----------------------------


def test_help_page_has_three_roles_and_no_supervisor():
    ayuda = AYUDA.read_text(encoding="utf-8")
    assert "supervis" not in ayuda.lower()
    assert "El sistema cuenta con 3 roles de usuario" in ayuda
    inicio = ayuda.index("<h3>Permisos por rol</h3>")
    cabecera = ayuda[inicio:ayuda.index("</thead>", inicio)]
    assert [c for c in ROLES if f"<th>{c}</th>" in cabecera] == list(ROLES)


def test_chat_texts_have_no_supervisor():
    textos = [GUIA_APP, REGLAS_PARA_IA, *PERMISOS_POR_ROL.values(), *DESCRIPCION_ROL.values()]
    assert set(PERMISOS_POR_ROL) == set(ROLES)
    for texto in textos:
        assert "supervis" not in texto.lower(), texto
    assert "Hay 3 roles: Administrador, Técnico y Solicitante" in GUIA_APP


@pytest.mark.parametrize("pregunta", [
    "que roles hay", "cuantos roles hay", "que hace cada rol", "que puede hacer un supervisor",
])
def test_chat_says_there_are_three_roles(client, session, ia, pregunta):
    headers = login_as(client, session, "Técnico", "tec@data.cr", "Tomás Técnico")
    respuesta = _respuesta(ask(client, headers, pregunta), "directa")
    assert respuesta.startswith(TRES_ROLES)
    assert "supervis" not in respuesta.lower()


@pytest.mark.parametrize("rol", ROLES)
@pytest.mark.parametrize("pregunta", [
    "quien puede asignar tickets", "como asigno un ticket", "como edito un ticket",
    "donde veo las metricas", "que es explicar con ia", "que prioridades hay",
    "como funciona la ticketera", "como cambio el estado", "como se reparten los tickets",
])
def test_chat_answers_never_mention_supervisor(client, session, ia, rol, pregunta):
    headers = login_as(client, session, rol, "p@data.cr", "Persona")
    respuesta = ask(client, headers, pregunta).json()["respuesta"]
    assert "supervis" not in respuesta.lower(), respuesta
    for llamada in ia.calls:  # lo que se le manda a la IA, si llega
        assert "supervis" not in llamada["system"].lower()
