"""Preguntas sobre roles y permisos («¿qué hace el técnico y el
solicitante?», «permisos del administrador», «y el solicitante?»): se
responden sin IA con la tabla de permisos de ayuda.html, una línea por rol y
sin nombres de personas. Si una pregunta de reglas llega igual a la IA, lleva
los permisos reales y la instrucción de no ponerle nombres a los roles."""

import re
from pathlib import Path

import pytest

from backend.models import User
from backend.services.asistente_service import (
    PERMISOS_POR_ROL,
    REGLAS_PARA_IA,
    ROLES_TABLA,
    TABLA_PERMISOS,
    detectar_consulta,
    roles_nombrados,
)
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401

AYUDA = Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html"
NOMBRES = ("Kristin", "Castro", "Daniel", "Mora", "José", "Solano", "Andrea")


@pytest.fixture
def admin(client, session):
    """Kristin es Administradora; también hay un Técnico y una Solicitante:
    ninguna respuesta sobre roles debe nombrarlos."""
    headers = login_as(client, session, "Administrador", "kristin@adn.local", "Kristin Castro")
    session.add_all([
        User(name="Daniel Mora", email="daniel@adn.local", role="Técnico", password_hash="x"),
        User(name="Andrea Solano", email="andrea@adn.local", role="Solicitante", password_hash="x"),
    ])
    session.commit()
    return headers


def conversar(client, headers, *preguntas_y_respuestas):
    mensajes = [{"role": "user" if i % 2 == 0 else "assistant", "content": m}
                for i, m in enumerate(preguntas_y_respuestas)]
    return client.post("/api/asistente", json={"messages": mensajes}, headers=headers)


def linea(rol):
    return f"**{rol}**: {PERMISOS_POR_ROL[rol]}"


def sin_nombres(respuesta):
    for nombre in NOMBRES:
        assert nombre not in respuesta, respuesta


def test_permissions_table_is_the_same_as_the_help_page():
    html = AYUDA.read_text(encoding="utf-8")
    tabla = html[html.index("<h3>Permisos por rol</h3>"):]
    tabla = tabla[:tabla.index("</table>")]
    cabecera = re.findall(r"<th>(.*?)</th>", tabla)
    assert tuple(cabecera[1:]) == ROLES_TABLA
    filas = [re.findall(r"<td>(.*?)</td>", f) for f in re.findall(r"<tr><td>.*?</tr>", tabla)]
    assert [(f[0], tuple(f[1:])) for f in filas] == [(accion, valores) for accion, _, valores in TABLA_PERMISOS]


def test_role_texts_follow_the_table():
    tecnico = PERMISOS_POR_ROL["Técnico"]
    assert "No puede editar tickets, asignar tickets, ver las métricas, eliminar tickets ni administrar usuarios." in tecnico
    assert "cambiar el estado" in tecnico.split("No puede")[0]
    solicitante = PERMISOS_POR_ROL["Solicitante"]
    assert "ver tickets (los suyos y los asignados a él)" in solicitante
    assert "editar tickets" in solicitante.split("No puede")[1]
    assert "asignar tickets" in solicitante.split("No puede")[1]
    assert "No puede" not in PERMISOS_POR_ROL["Administrador"]


def test_technician_and_requester_one_line_each_without_ai(client, ia, admin):
    respuesta = _respuesta(ask(client, admin, "y que hace el tecnico y el solicitante?"), "directa")

    assert respuesta == f"{linea('Técnico')}\n{linea('Solicitante')}"
    # Ninguno de los dos edita ni asigna (la IA lo había inventado).
    for rol in ("Técnico", "Solicitante"):
        assert "editar tickets" in PERMISOS_POR_ROL[rol].split("No puede")[1]
    sin_nombres(respuesta)
    assert ia.interpretaciones == [] and ia.calls == []


@pytest.mark.parametrize("pregunta,roles", [
    ("que puede hacer un supervisor", ["Supervisor"]),
    ("permisos del administrador", ["Administrador"]),
    ("que hace el tecnico", ["Técnico"]),
    ("¿Qué permisos tiene el Solicitante?", ["Solicitante"]),
    ("para que sirve el rol de supervisor?", ["Supervisor"]),
    ("q hace el tecnco y el solisitante", ["Técnico", "Solicitante"]),
    ("que puede hacer el adminsitrador", ["Administrador"]),
    ("que hace cada rol?", list(ROLES_TABLA)),
])
def test_role_questions_are_answered_by_the_server(client, ia, admin, pregunta, roles):
    respuesta = _respuesta(ask(client, admin, pregunta), "directa")

    assert respuesta == "\n".join(linea(rol) for rol in roles)
    sin_nombres(respuesta)
    assert ia.interpretaciones == [] and ia.calls == []


def test_follow_up_with_another_role(client, ia, admin):
    primera = _respuesta(ask(client, admin, "que hace el tecnico"), "directa")
    assert primera == linea("Técnico")

    segunda = _respuesta(conversar(client, admin, "que hace el tecnico", primera, "y el solicitante?"),
                         "directa")

    assert segunda == linea("Solicitante")
    sin_nombres(segunda)
    assert ia.calls == []


def test_role_questions_are_not_counts():
    assert detectar_consulta("y que hace el tecnico y el solicitante?") is None
    # «administrar usuarios» no nombra al rol Administrador.
    assert roles_nombrados("quien puede administrar usuarios") == []


def test_counts_by_role_still_work(client, ia, admin):
    respuesta = _respuesta(ask(client, admin, "cuantos tickets tienen los tecnicos"), "directa")

    assert "técnicos" in respuesta
    assert PERMISOS_POR_ROL["Técnico"] not in respuesta


def test_rule_question_reaching_the_ai_has_real_permissions(client, ia, admin):
    _respuesta(ask(client, admin, "quienes pueden usar el chat?"), "ia")

    system = ia.calls[0]["system"]
    assert REGLAS_PARA_IA in system
    for rol in ROLES_TABLA:
        assert f"- {rol}: {PERMISOS_POR_ROL[rol]}" in system
    assert "no le pongas nombres de personas" in system
