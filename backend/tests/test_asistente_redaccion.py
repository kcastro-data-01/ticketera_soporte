"""La IA redacta el resumen de las respuestas de conteo con los datos que
calculó el servidor, y el servidor agrega debajo la lista de tickets. Si
cambia un número, inventa un ticket, pierde una palabra clave («cerrados»,
«nuevos»), tarda o falla, se usa el texto fijo («Respuesta del sistema») y
queda en el log."""

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


def _linea(ticket, estado, asignado="José Solano (Técnico)"):
    return (f"- #{ticket.id} «{ticket.title}» (Red, prioridad Alta, estado {estado}, "
            f"asignado a {asignado})")


@pytest.fixture
def en_proceso(client, session):
    """Técnico con un ticket en proceso; devuelve (headers, ticket, texto fijo)."""
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    jose = session.query(User).filter_by(email="tec@tec.local").one()
    ticket = add_ticket(session, "Problemas")
    ticket.state = "En proceso"
    ticket.assigned_to_id = jose.id
    session.commit()
    fijo = f"Hay 1 ticket en proceso:\n{_linea(ticket, 'En proceso')}"
    return headers, ticket, fijo


def test_ai_writes_the_summary_and_the_server_adds_the_list(client, ia, log, en_proceso):
    headers, ticket, _ = en_proceso
    ia.texto = "Hay 1 ticket en proceso y lo atiende José Solano."

    resp = ask(client, headers, "¿cuántos tickets hay en proceso?")

    assert resp.json() == {"respuesta": f"{ia.texto}\n{_linea(ticket, 'En proceso')}", "fuente": "ia_datos"}
    llamada = ia.calls[0]
    assert llamada["system"] == INSTRUCCIONES_REDACCION
    assert "Respondé la pregunta usando SOLO estos datos. No cambies ningún número ni nombre." in llamada["system"]
    assert "No listes los tickets" in llamada["system"]
    # Dos ejemplos (pregunta + respuesta) y el pedido real al final: solo la
    # cabecera, sin la lista de tickets.
    assert [m["role"] for m in llamada["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert llamada["messages"][-1]["content"] == (
        "Pregunta: ¿cuántos tickets hay en proceso?\nDatos verificados:\nHay 1 ticket en proceso."
    )
    assert log == []


@pytest.fixture
def varios(client, session):
    """Técnico con tickets en cada estado: 2 nuevos, 1 en proceso, 1
    resuelto y 1 cerrado."""
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    tickets = {}
    for titulo, estado in [("Monitor", "Nuevo"), ("Teclado", "Nuevo"), ("VPN", "En proceso"),
                           ("Impresora", "Resuelto"), ("Cable", "Cerrado")]:
        tickets[titulo] = add_ticket(session, titulo)
        tickets[titulo].state = estado
    session.commit()
    return headers, tickets


def test_resolved_summary_must_say_closed(client, ia, log, varios):
    headers, t = varios
    ia.texto = "Hay 2 tickets resueltos."
    resp = ask(client, headers, "cuantos se resolvieron")
    assert resp.json()["fuente"] == "directa"
    assert resp.json()["respuesta"].startswith("Hay 2 tickets resueltos o cerrados:")
    assert "falta «cerrados»" in log[0]

    ia.texto = "Hay 2 tickets resueltos o cerrados."
    lineas = ask(client, headers, "cuantos se resolvieron").json()["respuesta"].splitlines()
    assert lineas[0] == ia.texto
    assert {l.split()[1] for l in lineas[1:]} == {f"#{t['Impresora'].id}", f"#{t['Cable'].id}"}


@pytest.mark.parametrize(
    "redactada, valida",
    [
        ("Hay 3 tickets pendientes: 2 nuevos y 1 en proceso.", True),
        ("Hay 3 tickets pendientes, 2 de ellos nuevos.", False),  # falta «en proceso»
        ("Hay 3 tickets pendientes, 1 está en proceso.", False),  # falta «nuevos»
    ],
)
def test_pending_summary_must_keep_the_breakdown(client, ia, log, varios, redactada, valida):
    headers, t = varios
    ia.texto = redactada
    resp = ask(client, headers, "cuantos hay pendientes").json()
    assert resp["fuente"] == ("ia_datos" if valida else "directa")
    lineas = resp["respuesta"].splitlines()
    # La lista completa está siempre, la haya redactado la IA o no.
    assert {l.split()[1] for l in lineas[1:]} == {f"#{t[n].id}" for n in ("Monitor", "Teclado", "VPN")}
    if valida:
        assert lineas[0] == redactada
    else:
        assert lineas[0] == "Hay 3 tickets pendientes (2 nuevos y 1 en proceso):"
        assert "falta" in log[0]


def test_person_summary_gets_the_ticket_list_below(client, session, ia, varios):
    headers, t = varios
    jose = session.query(User).filter_by(email="tec@tec.local").one()
    t["VPN"].assigned_to_id = jose.id
    session.commit()
    ia.texto = "José Solano (Técnico) tiene 1 ticket sin resolver."

    resp = ask(client, headers, "cuantos tickets tiene José Solano").json()

    assert resp == {"respuesta": f"{ia.texto}\n{_linea(t['VPN'], 'En proceso')}", "fuente": "ia_datos"}
    assert ia.calls[0]["messages"][-1]["content"].endswith(
        "Datos verificados:\nJosé Solano (Técnico) tiene 1 ticket sin resolver asignado."
    )


@pytest.mark.parametrize(
    "redactada, motivo",
    [
        ("Hay 3 tickets en proceso.", "dice 3"),
        ("Hay 1 ticket en proceso: el #999 «Problemas».", "#999"),
        # La lista la pone el servidor: un #ticket en el resumen no está en los datos.
        ("Hay 1 ticket en proceso: el #{id}.", "que no está en los datos"),
        ("Hay tickets en proceso, uno de ellos «Problemas».", "falta el número principal"),
        ("", "respuesta vacía"),
    ],
)
def test_wrong_draft_falls_back_to_the_system_answer(client, ia, log, en_proceso, redactada, motivo):
    headers, ticket, fijo = en_proceso
    ia.texto = redactada.format(id=ticket.id)

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
    ia.texto = "Hay 1 ticket en proceso."

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
    ia.texto = "Hay 1 ticket en proceso."
    resp = client.post(
        "/api/asistente/stream",
        json={"messages": [{"role": "user", "content": "¿cuántos tickets hay en proceso?"}]},
        headers=headers,
    )
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    assert eventos == [{"t": f"{ia.texto}\n{_linea(ticket, 'En proceso')}"}, {"fin": True, "fuente": "ia_datos"}]


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


CERRADOS = (("cerrados", r"\bcerrad[oa]s?\b"),)


@pytest.mark.parametrize(
    "texto, valido",
    [
        ("Hay 2 tickets resueltos o cerrados.", True),
        ("Hay 1 ticket resuelto o cerrado.", True),
        ("Hay 2 tickets resueltos.", False),
    ],
)
def test_verify_draft_keywords(texto, valido):
    datos = "Hay 2 tickets resueltos o cerrados. Hay 1 ticket resuelto o cerrado."
    principal = 1 if "1 ticket" in texto else 2
    assert (verificar_redaccion(texto, datos, principal, CERRADOS) is None) == valido
