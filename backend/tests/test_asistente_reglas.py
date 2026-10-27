"""Preguntas sobre las reglas de la ticketera («¿cuántos tickets se le pueden
asignar a una persona?», «¿quién puede asignar tickets?»): no son conteos.
Se responden con la regla real del código, armada por el servidor y sin IA;
si es de reglas pero no hay una preparada, va a la IA libre con las reglas
en el contexto, nunca a «No entendí…»."""

import pytest

from backend.services.asistente_service import (
    NO_ENTENDI,
    REGLA_CORREO,
    REGLA_LIMITE,
    REGLA_QUIEN_ASIGNA,
    REGLA_QUIEN_CAMBIA_ESTADO,
    REGLA_REPARTO,
    REGLA_SOLICITANTE,
    REGLAS_PARA_IA,
    detectar_consulta,
)
from backend.tests.test_asistente import add_ticket, ask, login_as
from backend.tests.test_asistente_interpretacion import _json, _respuesta, ia  # noqa: F401
from backend.tests.textos_asistente import negrita


@pytest.fixture
def tecnico(client, session):
    return login_as(client, session, "Técnico", "tec@tec.local", "José Solano")


@pytest.mark.parametrize("pregunta", [
    "cuantos ticketes se le pueden asignar a una persona?",
    "¿Cuántos tickets se le pueden asignar a una persona?",
    "cual es el maximo de tickets por persona",
    "cual es el maxmo de tikets por persona",
    "cuantos tickets puede tener un tecnico como maximo?",
    "hay un tope de tickets por tecnico?",
    "hay limite de tickets asignados?",
    "cuantos tickets se pueden asignar",
])
def test_limit_questions_answer_the_real_rule_without_ai(client, ia, tecnico, pregunta):
    respuesta = _respuesta(ask(client, tecnico, pregunta), "directa")

    assert respuesta == REGLA_LIMITE
    assert respuesta not in NO_ENTENDI
    # Sin IA: ni la clasifica ni la redacta.
    assert ia.interpretaciones == [] and ia.calls == []


def test_the_limit_rule_matches_the_code():
    # ticket_service.pick_next_assignee no tiene tope: menos tickets, empate al id menor.
    assert "no tiene un límite de tickets por persona" in REGLA_LIMITE
    assert "Técnico activo con menos tickets" in REGLA_LIMITE
    for regla in (REGLA_LIMITE, REGLA_QUIEN_ASIGNA, REGLA_REPARTO, REGLA_QUIEN_CAMBIA_ESTADO,
                  REGLA_SOLICITANTE, REGLA_CORREO):
        # Tono formal: nada de tú.
        palabras = regla.lower().replace(",", " ").replace(".", " ").split()
        assert not {"tú", "tu", "puedes", "tienes", "pulsa", "entra"} & set(palabras)


@pytest.mark.parametrize("pregunta,regla", [
    ("quien puede asignar tickets", REGLA_QUIEN_ASIGNA),
    ("¿Quiénes pueden asignar tickets?", REGLA_QUIEN_ASIGNA),
    ("como se reparten los tickets?", REGLA_REPARTO),
    ("quien puede cambiar el estado de un ticket", REGLA_QUIEN_CAMBIA_ESTADO),
    ("que ve un solicitante?", REGLA_SOLICITANTE),
    ("como se crean los tickets desde el correo?", REGLA_CORREO),
])
def test_other_rules_are_answered_by_the_server(client, ia, tecnico, pregunta, regla):
    respuesta = _respuesta(ask(client, tecnico, pregunta), "directa")

    assert respuesta == regla
    assert ia.interpretaciones == [] and ia.calls == []


def test_who_can_assign_is_the_rule_even_for_a_technician(client, ia, tecnico):
    # Antes: «Con tu rol (Técnico) no puedes asignar tickets.»
    respuesta = _respuesta(ask(client, tecnico, "quien puede asignar tickets"), "directa")

    assert "Solo el Administrador y el Supervisor" in respuesta


def test_rule_question_without_answer_goes_to_ai_with_the_rules(client, ia, tecnico):
    respuesta = _respuesta(ask(client, tecnico, "quienes pueden usar el chat?"), "ia")

    assert respuesta == "Respuesta de la IA libre."
    assert ia.interpretaciones == []  # no se clasifica como conteo
    assert REGLAS_PARA_IA in ia.calls[0]["system"]


@pytest.mark.parametrize("pregunta", [
    "cuantos ticketes se le pueden asignar a una persona?",
    "cual es el maximo de tickets por persona",
    "hay un tope de tickets?",
])
def test_count_detector_ignores_rule_questions(pregunta):
    assert detectar_consulta(pregunta) is None


def test_new_tickets_are_still_counted(client, session, ia, tecnico):
    for titulo in ("Monitor nuevo", "Teclado nuevo"):
        add_ticket(session, titulo)

    respuesta = _respuesta(ask(client, tecnico, "cuantos tickets nuevos hay"), "directa")

    assert negrita(2) in respuesta and "nuevos" in respuesta
    assert detectar_consulta("cuantos tickets nuevos hay") == "nuevos"
    # La IA libre no recibe las reglas en una pregunta que no es de reglas.
    assert ia.calls == []


def test_ai_context_has_no_rules_for_other_questions(client, ia, tecnico):
    _respuesta(ask(client, tecnico, "como resuelvo un problema con la impresora?"), "ia")

    assert REGLAS_PARA_IA not in ia.calls[0]["system"]
