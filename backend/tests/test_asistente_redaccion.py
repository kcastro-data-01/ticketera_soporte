"""La IA redacta las respuestas de conteo con los datos que calculó el
servidor; si cambia un número, inventa un ticket, tarda o falla, se usa el
texto fijo («Respuesta del sistema») y queda en el log."""

import json
import time

import pytest

from backend.main import app
from backend.models import User
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service
from backend.services.asistente_service import (
    INSTRUCCIONES_REDACCION,
    AsistenteNoDisponible,
    verificar_redaccion,
)
from backend.tests.test_asistente import add_ticket, ask, login_as


class IASimulada:
    """Devuelve ``texto`` (o lanza ``error``, o tarda ``demora`` segundos)."""

    def __init__(self):
        self.calls = []
        self.texto = ""
        self.error = None
        self.demora = 0

    def responder(self, system, messages):
        self.calls.append({"system": system, "messages": messages})
        if self.demora:
            time.sleep(self.demora)
        if self.error is not None:
            raise self.error
        return self.texto


@pytest.fixture
def ia(monkeypatch):
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "true")
    simulada = IASimulada()
    app.dependency_overrides[get_proveedor] = lambda: simulada
    yield simulada
    app.dependency_overrides.pop(get_proveedor, None)


@pytest.fixture
def log(monkeypatch):
    mensajes = []
    monkeypatch.setattr(asistente_service.logger, "info", lambda msg, *args: mensajes.append(msg % args))
    return mensajes


@pytest.fixture
def en_proceso(client, session):
    """Técnico con un ticket en proceso; devuelve (headers, ticket, texto fijo)."""
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    jose = session.query(User).filter_by(email="tec@tec.local").one()
    ticket = add_ticket(session, "Problemas")
    ticket.state = "En proceso"
    ticket.assigned_to_id = jose.id
    session.commit()
    fijo = (f"Hay 1 ticket en proceso:\n- #{ticket.id} «Problemas» (Red, prioridad Alta, "
            "estado En proceso, asignado a José Solano (Técnico))")
    return headers, ticket, fijo


def test_ai_drafts_the_verified_data(client, ia, log, en_proceso):
    headers, ticket, fijo = en_proceso
    ia.texto = f"Hay 1 ticket en proceso: el #{ticket.id} «Problemas», que atiende José Solano."

    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")

    assert resp.json() == {"respuesta": ia.texto, "fuente": "ia_datos"}
    llamada = ia.calls[0]
    assert llamada["system"] == INSTRUCCIONES_REDACCION
    assert "Respondé la pregunta usando SOLO estos datos. No cambies ningún número ni nombre." in llamada["system"]
    # Dos ejemplos (pregunta + respuesta) y el pedido real al final.
    assert [m["role"] for m in llamada["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert llamada["messages"][-1]["content"] == (
        f"Pregunta: ¿cuántos tickets hay en proceso?\nDatos verificados:\n{fijo}"
    )
    assert log == []


@pytest.mark.parametrize(
    "redactada, motivo",
    [
        ("Hay 3 tickets en proceso.", "dice 3"),
        ("Hay 1 ticket en proceso: el #999 «Problemas».", "#999"),
        ("Hay tickets en proceso, uno de ellos «Problemas».", "falta el número principal"),
        ("", "respuesta vacía"),
    ],
)
def test_wrong_draft_falls_back_to_the_system_answer(client, ia, log, en_proceso, redactada, motivo):
    headers, _, fijo = en_proceso
    ia.texto = redactada

    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")

    assert resp.json() == {"respuesta": fijo, "fuente": "directa"}
    assert len(log) == 1
    assert log[0].startswith("respuesta descartada, se usó la del sistema")
    assert motivo in log[0]


@pytest.mark.parametrize("error", [AsistenteNoDisponible("sin Ollama"), RuntimeError("inesperado")])
def test_ai_failure_falls_back(client, ia, log, en_proceso, error):
    headers, _, fijo = en_proceso
    ia.error = error
    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")
    assert resp.json() == {"respuesta": fijo, "fuente": "directa"}
    assert "falló" in log[0]


def test_slow_ai_falls_back(client, ia, log, en_proceso, monkeypatch):
    headers, ticket, fijo = en_proceso
    monkeypatch.setattr(asistente_service, "REDACCION_TIMEOUT", 0.2)
    ia.demora = 1
    ia.texto = f"Hay 1 ticket en proceso: el #{ticket.id}."

    inicio = time.monotonic()
    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")

    assert time.monotonic() - inicio < 1
    assert resp.json() == {"respuesta": fijo, "fuente": "directa"}
    assert "tardó más de 0.2 s" in log[0]


def test_zero_count_accepts_saying_there_are_none(client, ia, log, en_proceso):
    headers, *_ = en_proceso
    ia.texto = "Por ahora no hay ningún ticket crítico sin resolver."
    resp = ask(client, headers, "¿hay tickets críticos?")
    assert resp.json() == {"respuesta": ia.texto, "fuente": "ia_datos"}


def test_ticket_state_is_drafted_with_its_number(client, ia, log, en_proceso):
    headers, ticket, _ = en_proceso
    ia.texto = f"El ticket #{ticket.id} «Problemas» está En proceso y lo atiende José Solano."
    resp = ask(client, headers, f"¿en qué estado está el ticket #{ticket.id}?")
    assert resp.json() == {"respuesta": ia.texto, "fuente": "ia_datos"}


@pytest.mark.parametrize(
    "pregunta",
    ["¿cómo cambio mi contraseña?", "cuantos tickets estan congelados", "¿en qué estado está el ticket #999?"],
)
def test_fixed_answers_that_are_not_counts_skip_the_ai(client, ia, en_proceso, pregunta):
    headers, *_ = en_proceso
    resp = ask(client, headers, pregunta)
    assert resp.json()["fuente"] == "directa"
    assert ia.calls == []


def test_can_be_turned_off(client, ia, en_proceso, monkeypatch):
    headers, _, fijo = en_proceso
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "false")
    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")
    assert resp.json() == {"respuesta": fijo, "fuente": "directa"}
    assert ia.calls == []


def test_stream_sends_the_draft_with_its_label(client, ia, en_proceso):
    headers, ticket, _ = en_proceso
    ia.texto = f"Hay 1 ticket en proceso: el #{ticket.id} «Problemas»."
    resp = client.post(
        "/api/asistente/stream",
        json={"messages": [{"role": "user", "content": "¿cuántos tickets hay en proceso?"}]},
        headers=headers,
    )
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    assert eventos == [{"t": ia.texto}, {"fin": True, "fuente": "ia_datos"}]


DATOS = "Hay 2 tickets nuevos:\n- #4 «Impresora 3» (…)\n- #7 «VPN» (…)"


@pytest.mark.parametrize(
    "texto, principal, valido",
    [
        ("Hay 2 tickets nuevos: el #4 y el #7.", 2, True),
        ("Hay dos tickets nuevos: el #4 «Impresora 3» y el #7.", 2, True),
        ("Hay tres tickets nuevos.", 2, False),
        ("Hay 2 tickets nuevos: el #4 y el #2.", 2, False),  # #2 no es un ticket de los datos
        ("Hay 2 tickets nuevos, el más antiguo de hace 5 días.", 2, False),
        ("No hay ningún ticket nuevo.", 0, True),
        ("Hay tickets nuevos.", 0, False),
    ],
)
def test_verify_draft(texto, principal, valido):
    assert (verificar_redaccion(texto, DATOS, principal) is None) == valido
