"""Si las reglas no reconocen la pregunta («cuatos ticketes estan
terminados ?»), la IA la clasifica en un JSON con valores fijos y el
servidor calcula con las mismas funciones de conteo. Si el JSON no sirve, la
persona o el ticket no existen, es «otra» o tarda, sigue la IA libre, que
recibe igual los conteos por estado."""

import json
import time

import pytest

from backend.main import app
from backend.models import User
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service
from backend.services.asistente_service import (
    ESQUEMA_INTERPRETACION,
    NO_ENTENDI,
    MENSAJE_IA_OCUPADA,
    AsistenteNoDisponible,
    IATardo,
    calcular_desde_interpretacion,
    calcular_directa,
    leer_interpretacion,
)
from backend.tests.test_asistente import add_ticket, ask, login_as


def _json(tipo="conteo", estado=None, periodo=None, persona=None, rol=None, ticket=None):
    return json.dumps({"tipo": tipo, "estado": estado, "periodo": periodo,
                       "persona": persona, "rol": rol, "ticket": ticket})


class IASimulada:
    """``generar_json`` devuelve ``json`` (o lanza ``error``, o tarda
    ``demora`` segundos; como httpx, si pasa el ``timeout`` de la petición
    corta ahí y lanza ``IATardo``); ``responder`` es la IA libre."""

    def __init__(self):
        self.interpretaciones = []
        self.calls = []
        self.json = _json("otra")
        self.error = None
        self.demora = 0

    def generar_json(self, messages, esquema, temperature=0.1, timeout=None):
        self.interpretaciones.append({"messages": messages, "esquema": esquema, "timeout": timeout})
        if timeout is not None and self.demora > timeout:
            time.sleep(timeout)
            raise IATardo("timeout")
        if self.demora:
            time.sleep(self.demora)
        if self.error is not None:
            raise self.error
        return self.json

    def responder(self, system, messages, timeout=None):
        self.calls.append({"system": system, "messages": messages})
        return "Respuesta de la IA libre."


@pytest.fixture
def ia(monkeypatch):
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")
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
def tickets(client, session):
    """Técnico con un ticket de cada estado; el En proceso es de Carlos."""
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    carlos = User(name="Carlos Solís", email="carlos@tec.local", role="Técnico", password_hash="x")
    session.add(carlos)
    session.commit()
    t = {}
    for estado, titulo in [("Nuevo", "Monitor nuevo"), ("En proceso", "VPN caída"),
                           ("Resuelto", "Impresora"), ("Cerrado", "Cable de red")]:
        t[estado] = add_ticket(session, titulo)
        t[estado].state = estado
    t["En proceso"].assigned_to_id = carlos.id
    session.commit()
    return headers, t


def _respuesta(resp, fuente):
    assert resp.status_code == 200, resp.text
    assert resp.json()["fuente"] == fuente, resp.json()
    return resp.json()["respuesta"]


def test_misspelled_finished_is_counted_by_the_server(client, ia, log, tickets):
    headers, t = tickets
    ia.json = _json(estado="resueltos")

    respuesta = _respuesta(ask(client, headers, "tikets terminaos ?"), "directa")

    assert respuesta.startswith("Hay 2 tickets resueltos o cerrados:")
    assert f"#{t['Resuelto'].id}" in respuesta and f"#{t['Cerrado'].id}" in respuesta
    assert ia.calls == []
    enviado = ia.interpretaciones[0]
    assert enviado["esquema"] == ESQUEMA_INTERPRETACION
    assert enviado["timeout"] == 10.0
    assert enviado["messages"][-1] == {"role": "user", "content": "tikets terminaos ?"}
    assert "interpretó «tikets terminaos ?»" in log[0]


def test_rules_go_first_and_answer_without_interpreting(client, ia, tickets):
    headers, _ = tickets
    respuesta = _respuesta(ask(client, headers, "cunatos pendientes hay esta semana"), "directa")
    assert respuesta.startswith("Esta semana se crearon 2 tickets que siguen pendientes")
    assert ia.interpretaciones == []


def test_interpreted_period_uses_the_same_count_as_the_rules(session, tickets):
    _, t = tickets
    jose = session.query(User).filter_by(email="tec@tec.local").one()
    datos = leer_interpretacion(_json(estado="pendientes", periodo="semana"))
    directa, ticket = calcular_desde_interpretacion(session, jose, datos, pregunta="cunatos pendientes hay esta semana")
    assert ticket is None
    assert directa == calcular_directa(session, jose, "cuantos pendientes esta semana")


def test_misspelled_person_counts_their_tickets(client, ia, tickets):
    headers, t = tickets
    ia.json = _json(persona="carlos")
    respuesta = _respuesta(ask(client, headers, "tikets de carlos"), "directa")
    assert respuesta == f"Carlos Solís (Técnico) tiene 1 ticket sin resolver asignado: #{t['En proceso'].id} «VPN caída»."


@pytest.mark.parametrize("persona", [None, "tecnicoss"])  # el rol a veces llega también como persona
def test_role_counts_its_tickets(client, ia, tickets, persona):
    headers, _ = tickets
    ia.json = _json(rol="Técnico", persona=persona)
    respuesta = _respuesta(ask(client, headers, "tikets de los tecnicoss"), "directa")
    assert respuesta.startswith("Hay 1 ticket sin resolver asignado a técnicos: Carlos Solís (Técnico) tiene 1")


@pytest.mark.parametrize("estado", [None, "todos"])
def test_total_only_when_the_question_asks_for_it(client, ia, tickets, estado):
    headers, _ = tickets
    ia.json = _json(estado=estado)
    assert _respuesta(ask(client, headers, "todos los tikets q ai registrados"), "directa") == \
        "Hay 4 tickets visibles para ti en total."
    # El modelo perdió «nuevos»: no se responde el total por error.
    _respuesta(ask(client, headers, "tikets nuebos q ai registrados"), "ia")


def test_what_the_rules_did_not_understand_is_interpreted(client, ia, tickets):
    headers, t = tickets
    ia.json = _json(estado="nuevos")
    respuesta = _respuesta(ask(client, headers, "cuantos tikets ai q nadie atendio"), "directa")
    assert respuesta.startswith(f"Hay 1 ticket nuevo:\n- #{t['Nuevo'].id}")
    # Si la interpretación no sirve, se mantiene «No entendí…».
    ia.json = _json("otra")
    assert _respuesta(ask(client, headers, "cuantos tikets ai q nadie atendio"), "directa") == NO_ENTENDI
    assert ia.calls == []


@pytest.mark.parametrize(
    "interpretacion",
    [
        _json("otra"),
        _json(persona="Fernanda"),  # nadie se llama así
        _json("estado_ticket", ticket=999),  # no existe
        _json(persona="carlos", rol="Técnico"),
        _json(persona="carlos", estado="resueltos"),  # por persona solo hay sin resolver
    ],
)
def test_goes_to_the_free_ai(client, ia, tickets, interpretacion):
    headers, _ = tickets
    ia.json = interpretacion
    respuesta = _respuesta(ask(client, headers, "que significa prioridad alta"), "ia")
    assert respuesta == "Respuesta de la IA libre."
    assert len(ia.interpretaciones) == 1


def test_requester_cannot_name_anyone(client, session, ia, tickets):
    headers = login_as(client, session, "Solicitante", "sol@soli.local", "Andrea Castillo")
    ia.json = _json(persona="carlos")
    _respuesta(ask(client, headers, "tikets de carlos"), "ia")


@pytest.mark.parametrize(
    "texto, motivo",
    [
        ("no es json", "no es JSON"),
        ("[1, 2]", "no es un objeto JSON"),
        (_json(estado="terminados"), "estado inválido"),
        (_json(periodo="anio"), "periodo inválido"),
        (_json(rol="Solicitante"), "rol inválido"),
        (_json("estado_ticket", ticket="5"), "ticket inválido"),
        (json.dumps({"estado": "resueltos"}), "tipo inválido"),
    ],
)
def test_invalid_json_goes_to_the_free_ai(client, ia, log, tickets, texto, motivo):
    headers, _ = tickets
    ia.json = texto
    _respuesta(ask(client, headers, "tikets terminaos ?"), "ia")
    assert "interpretación descartada, se usó la IA libre (JSON inválido" in log[0]
    assert motivo in log[0]


def test_slow_interpretation_is_cancelled_and_does_not_call_the_free_ai(client, ia, log, tickets, monkeypatch):
    headers, _ = tickets
    monkeypatch.setattr(asistente_service, "INTERPRETACION_TIMEOUT", 0.05)
    ia.json = _json(estado="resueltos")
    ia.demora = 0.5

    inicio = time.monotonic()
    respuesta = _respuesta(ask(client, headers, "tikets terminaos ?"), "directa")

    assert time.monotonic() - inicio < 0.5
    assert respuesta == MENSAJE_IA_OCUPADA
    assert ia.interpretaciones[0]["timeout"] == 0.05
    assert ia.calls == []  # la IA libre no se llamó detrás
    assert "interpretación cancelada: tardó más de 0.05 s" in log[0]


def test_slow_interpretation_keeps_the_rules_answer(client, ia, tickets, monkeypatch):
    headers, _ = tickets
    monkeypatch.setattr(asistente_service, "INTERPRETACION_TIMEOUT", 0.05)
    ia.demora = 0.5
    assert _respuesta(ask(client, headers, "cuantos tikets ai q nadie atendio"), "directa") == NO_ENTENDI
    assert ia.calls == []


def test_slow_interpretation_in_the_stream(client, ia, tickets, monkeypatch):
    headers, _ = tickets
    monkeypatch.setattr(asistente_service, "INTERPRETACION_TIMEOUT", 0.05)
    ia.demora = 0.5
    resp = client.post("/api/asistente/stream", headers=headers,
                       json={"messages": [{"role": "user", "content": "tikets terminaos ?"}]})
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea]
    assert eventos == [{"t": MENSAJE_IA_OCUPADA}, {"fin": True, "fuente": "directa"}]
    assert ia.calls == []


def test_failed_interpretation_goes_to_the_free_ai(client, ia, log, tickets):
    headers, _ = tickets
    ia.error = AsistenteNoDisponible("Ollama no responde")
    _respuesta(ask(client, headers, "tikets terminaos ?"), "ia")
    assert "falló: Ollama no responde" in log[0]


def test_ticket_state(client, ia, tickets):
    headers, t = tickets
    ia.json = _json("estado_ticket", ticket=t["En proceso"].id)
    respuesta = _respuesta(ask(client, headers, f"q tal va el tiket {t['En proceso'].id}"), "directa")
    assert respuesta.startswith(f"El ticket #{t['En proceso'].id} «VPN caída» está en estado En proceso")


def test_explain_ticket_uses_explain_with_ai(client, ia, tickets, monkeypatch):
    headers, t = tickets
    from backend.services import explicacion_service

    monkeypatch.setattr(explicacion_service, "explicacion_para_chat",
                        lambda session, proveedor, ticket, user: f"Explicación del #{ticket.id}")
    ia.json = _json("explicar_ticket", ticket=t["Nuevo"].id)
    respuesta = _respuesta(ask(client, headers, f"q kiere decir el tiket {t['Nuevo'].id}"), "ia")
    assert respuesta == f"Explicación del #{t['Nuevo'].id}"


def test_free_ai_gets_the_counts_by_state(client, ia, tickets):
    headers, _ = tickets
    _respuesta(ask(client, headers, "tikets terminaos ?"), "ia")
    assert ("Conteos por estado (terminados, finalizados o solucionados = resueltos o cerrados; "
            "pendientes = nuevos + en proceso): nuevos 1; en proceso 1; pendientes 2; "
            "resueltos o cerrados 2; cerrados 1; total 4.") in ia.calls[0]["system"]


def test_interpreted_count_is_drafted_like_the_others(client, ia, monkeypatch, tickets):
    headers, _ = tickets
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "true")
    ia.json = _json(estado="cerrados")
    ia.responder = lambda system, messages, timeout=None: "Hay 1 ticket cerrado en este momento."
    respuesta = _respuesta(ask(client, headers, "tikets serrados ?"), "ia_datos")
    assert respuesta.splitlines()[0] == "Hay 1 ticket cerrado en este momento."


def test_stream_also_interprets(client, ia, tickets):
    headers, _ = tickets
    ia.json = _json(estado="resueltos")
    resp = client.post("/api/asistente/stream", headers=headers,
                       json={"messages": [{"role": "user", "content": "tikets terminaos ?"}]})
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea]
    assert eventos[0]["t"].startswith("Hay 2 tickets resueltos o cerrados:")
    assert eventos[-1] == {"fin": True, "fuente": "directa"}


def test_can_be_turned_off(client, ia, tickets, monkeypatch):
    headers, _ = tickets
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "false")
    _respuesta(ask(client, headers, "tikets terminaos ?"), "ia")
    assert ia.interpretaciones == []


def test_read_interpretation_accepts_json_in_a_code_block():
    datos = leer_interpretacion(f"```json\n{_json(estado='nuevos', persona='  ')}\n```")
    assert datos == {"tipo": "conteo", "estado": "nuevos", "periodo": None,
                     "persona": None, "rol": None, "ticket": None}


@pytest.mark.parametrize(
    "pregunta, interpretacion",
    [
        # El modelo copió el 12 o «maria» de los ejemplos: no están en la pregunta.
        ("que es un ticket critico", _json("estado_ticket", ticket=12)),
        ("cuantos tikets tiene alguien", _json(persona="carlos")),
    ],
)
def test_ticket_or_person_not_in_the_question_goes_to_the_free_ai(client, ia, tickets, pregunta, interpretacion):
    headers, _ = tickets
    ia.json = interpretacion
    _respuesta(ask(client, headers, pregunta), "ia")


def test_warm_up_also_interprets_once(monkeypatch, log):
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")

    class Ollama(IASimulada):
        def precargar(self):
            return True

    ollama = Ollama()
    ollama.json = _json(estado="resueltos")
    assert asistente_service.precalentar(ollama, espera=0) is True
    assert len(ollama.interpretaciones) == 1
    assert ollama.calls == []  # conftest: la redacción está apagada
    assert log[0].startswith("modelo listo: interpretación de prueba en")
