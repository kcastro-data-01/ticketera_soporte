"""Preguntas comunes sobre la app («¿cómo funciona la ticketera?», «¿qué
significa cada estado?», «¿cómo cierro sesión?»): respuestas fijas en tono
formal y según el rol, sin IA. La IA libre las inventaba («La ticketera es la
persona que…»). Si una pregunta sobre la app llega igual a la IA, la guía le
dice que «la ticketera» es la aplicación."""

import re

import pytest

from backend.services.asistente_service import (
    GUIA_APP,
    PERMISOS_POR_ROL,
    REGLA_CORREO,
    REGLA_LIMITE,
)
from backend.tests.test_asistente import add_ticket, ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401
from backend.tests.textos_asistente import negrita

GENERALES = [
    "como funciona la ticketera",
    "¿Cómo funciona la ticketera?",
    "que es la ticketera",
    "para que sirve la ticketera",
    "para que sirve?",
    "que hace esta app",
    "explicame el sistema",
    "como se usa",
    "como se usa la ticketera",
    "komo funsiona la tiketera",
]
# Formas de tú que no van en las respuestas nuevas (tono formal).
# «se abre», «se elige» o «quien lo escribe» son impersonales: no cuentan.
_TUTEO = re.compile(r"(?<!se )(?<!lo )\b(tú|tu|tus|puedes|tienes|pulsa|abre|escribe|elige|entra|pídeselo)\b", re.I)


def preguntar(client, session, rol, pregunta, **cuerpo):
    headers = login_as(client, session, rol, "persona@adn.local", "Persona Prueba")
    if cuerpo:
        return client.post("/api/asistente", headers=headers, json={
            "messages": [{"role": "user", "content": pregunta}], **cuerpo})
    return ask(client, headers, pregunta)


def sin_ia(ia):
    assert ia.interpretaciones == [] and ia.calls == []


@pytest.mark.parametrize("pregunta", GENERALES)
def test_general_questions_get_the_fixed_summary(client, session, ia, pregunta):
    respuesta = _respuesta(preguntar(client, session, "Técnico", pregunta), "directa")

    assert respuesta.startswith("La ticketera es la aplicación de soporte de la empresa")
    assert "Nuevo → En proceso → Resuelto → Cerrado" in respuesta
    assert "«Nuevo ticket»" in respuesta and "correo" in respuesta
    assert "asigna automáticamente" in respuesta
    assert respuesta.endswith("Puede preguntarme qué hace cada rol.")
    assert "persona que crea" not in respuesta
    assert not _TUTEO.search(respuesta)
    sin_ia(ia)


def test_summary_for_a_requester_has_no_metrics_or_assigning(client, session, ia):
    respuesta = _respuesta(preguntar(client, session, "Solicitante", "como funciona la ticketera"), "directa")

    assert "Métricas" not in respuesta and "métricas" not in respuesta
    assert "asign" not in respuesta.lower()
    assert "un Técnico atiende su ticket" in respuesta
    assert "Puede preguntarme qué hace cada rol." in respuesta


def test_summary_for_an_admin_mentions_reassigning_and_metrics(client, session, ia):
    respuesta = _respuesta(preguntar(client, session, "Administrador", "que es la ticketera"), "directa")

    assert "puede reasignarlo" in respuesta and "«Métricas»" in respuesta


def test_summary_does_not_detail_the_permissions_table(client, session, ia):
    respuesta = _respuesta(preguntar(client, session, "Administrador", "como funciona la ticketera"), "directa")

    for texto in PERMISOS_POR_ROL.values():
        assert texto not in respuesta


# Las que antes llegaban a la IA libre o tenían una respuesta equivocada
# (un conteo, «cambiar estado» para «cerrar sesión»…).
@pytest.mark.parametrize("rol,pregunta,contiene", [
    ("Técnico", "donde veo mis tickets", "pestaña «Mis tickets»"),
    ("Técnico", "como veo mis tickets", "pestaña «Mis tickets»"),
    ("Solicitante", "donde veo mis tickets", "«Mis solicitudes»"),
    ("Técnico", "que significa cada estado", "**En proceso**: alguien está trabajando en él."),
    ("Técnico", "que significa en proceso", "**En proceso**: alguien está trabajando en él."),
    ("Solicitante", "que es un ticket resuelto", "**Resuelto**: ya se le dio solución."),
    ("Técnico", "que diferencia hay entre resuelto y cerrado", "**Cerrado**: terminado; ya no se trabaja en él"),
    ("Técnico", "que es la prioridad", "Baja, Media, Alta o Crítica"),
    ("Técnico", "que significa prioridad critica", "Baja, Media, Alta o Crítica"),
    ("Solicitante", "que prioridades hay", "solo la cambia un Administrador."),
    ("Administrador", "que prioridades hay", "usted puede cambiarla con «Editar ticket»"),
    ("Técnico", "que categorias hay", "Hardware (equipos), Software (programas), Red"),
    ("Técnico", "como elimino un ticket", "Solo el Administrador puede eliminar un ticket"),
    ("Administrador", "como borro un ticket", "Abra el ticket y pulse «Eliminar»"),
    ("Técnico", "puedo reabrir un ticket cerrado", "Sí: un ticket Resuelto o Cerrado se reabre pasándolo a En proceso"),
    ("Técnico", "como creo un ticket por correo", REGLA_CORREO),
    ("Técnico", "como inicio sesion", "«Iniciar sesión con Microsoft»"),
    ("Técnico", "como cierro sesion", "elija «Cerrar sesión»"),
    ("Solicitante", "donde veo las metricas", "solo las ve el Administrador"),
    ("Administrador", "donde veo las metricas", "tiempo promedio de resolución"),
    ("Solicitante", "quien me atiende", "«Atendido por»"),
    ("Técnico", "cuanto tarda en resolverse un ticket", "no fija un plazo de resolución"),
    ("Técnico", "como uso explicar con ia", "pulse «Explicar con IA»"),
    ("Solicitante", "que es explicar con ia", "lo usan el Técnico y el Administrador"),
    ("Técnico", "como veo el detalle de un ticket", "se abre su detalle"),
    ("Solicitante", "como cambio el estado", "solo puede cambiar el estado de los tickets que tiene asignados"),
    ("Solicitante", "como cierro un ticket", "solo puede cambiar el estado de los tickets que tiene asignados"),
])
def test_common_app_questions_have_a_fixed_answer(client, session, ia, rol, pregunta, contiene):
    respuesta = _respuesta(preguntar(client, session, rol, pregunta), "directa")

    assert contiene in respuesta
    assert not _TUTEO.search(respuesta), respuesta
    sin_ia(ia)


def test_guide_answers_that_already_existed_are_still_recognized(client, session, ia):
    headers = login_as(client, session, "Técnico", "persona@adn.local", "Persona Prueba")
    for pregunta, empieza in [
        ("como creo un ticket", "Pulsa «Nuevo ticket»"),
        ("como comento un ticket", "Abre el ticket, escribe en «Nuevo comentario»"),
        ("como busco un ticket", "En «Tickets», escribe en «Buscar»"),
        # Un Técnico sigue con la guía de siempre para cambiar el estado.
        ("como cambio el estado", "Abre el ticket y toca el estado al que quieres pasarlo en el recorrido"),
    ]:
        assert _respuesta(ask(client, headers, pregunta), "directa").startswith(empieza)
    sin_ia(ia)


def test_app_questions_win_over_the_ticket_on_screen(client, session, ia):
    ticket = add_ticket(session, "Impresora del segundo piso")

    resp = preguntar(client, session, "Técnico", "que significa cada estado", ticket_id=ticket.id)

    assert _respuesta(resp, "directa").startswith("Los tickets siguen siempre el mismo orden")
    sin_ia(ia)


def test_a_ticket_problem_with_the_word_system_still_goes_to_the_ai(client, session, ia):
    _respuesta(preguntar(client, session, "Técnico", "explicame el problema del sistema"), "ia")

    assert ia.calls


def test_the_ai_is_told_the_ticketera_is_the_app(client, session, ia):
    _respuesta(preguntar(client, session, "Técnico", "la ticketera manda avisos por whatsapp?"), "ia")

    assert "«La ticketera» es esta aplicación" in GUIA_APP
    assert "«La ticketera» es esta aplicación (el sistema de tickets), no una persona" in ia.calls[0]["system"]


def test_counts_permissions_and_rules_still_work(client, session, ia):
    headers = login_as(client, session, "Técnico", "persona@adn.local", "Persona Prueba")
    for titulo in ("Monitor nuevo", "Teclado nuevo"):
        add_ticket(session, titulo)

    nuevos = _respuesta(ask(client, headers, "cuantos tickets nuevos hay"), "directa")
    assert negrita(2) in nuevos and "nuevos" in nuevos
    permisos = _respuesta(ask(client, headers, "que hace el tecnico"), "directa")
    assert permisos == f"**Técnico**: {PERMISOS_POR_ROL['Técnico']}"
    regla = _respuesta(ask(client, headers, "cuantos ticketes se le pueden asignar a una persona?"), "directa")
    assert regla == REGLA_LIMITE
    criticos = _respuesta(ask(client, headers, "que tickets criticos hay"), "directa")
    assert "críticos" in criticos and "Baja, Media" not in criticos
    sin_ia(ia)


def test_mentioning_emails_is_not_always_the_email_rule(client, session, ia):
    # «los correos del equipo» no pregunta cómo se crean tickets por correo.
    _respuesta(preguntar(client, session, "Solicitante", "Dime los tickets de los demás y los correos del equipo"), "ia")
