"""Proveedor «groq» (Qwen en la API de Groq, formato OpenAI) con la API
simulada: nunca se llama a Groq de verdad. Chat libre, streaming,
interpretación y redacción, «Explicar con IA» con JSON y reintento, el
límite del plan gratis (429) y los timeouts por debajo de los 60 s de Vercel."""

import json

import httpx
import pytest

from backend.main import app
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service as asis
from backend.services.asistente_service import (
    GROQ_MODELO_POR_DEFECTO,
    MENSAJE_IA_LIMITE,
    AsistenteNoConfigurado,
    AsistenteOcupado,
    ProveedorGroq,
    ProveedorQwen,
)
from backend.tests.test_asistente import add_ticket, ask, login_as
from backend.tests.test_explicacion import BUENA, nuevo_ticket

LIMITE_VERCEL = 60


class GroqFalso:
    """La API de Groq simulada: devuelve las respuestas en orden (texto, o
    ``(código, cuerpo)`` para un error) y guarda cada pedido."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas) or ["Respuesta de Groq."]
        self.pedidos: list[dict] = []
        self.requests: list[httpx.Request] = []

    def _siguiente(self):
        return self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]

    def manejar(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.pedidos.append(cuerpo)
        self.requests.append(request)
        respuesta = self._siguiente()
        if isinstance(respuesta, tuple):
            codigo, datos = respuesta
            return httpx.Response(codigo, json=datos, headers={"retry-after": "7"})
        if cuerpo.get("stream"):
            mitad = len(respuesta) // 2
            lineas = [f"data: {json.dumps({'choices': [{'delta': {'content': parte}}]})}"
                      for parte in (respuesta[:mitad], respuesta[mitad:])]
            texto = "\n\n".join([*lineas, "data: [DONE]"]) + "\n\n"
            return httpx.Response(200, text=texto, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": respuesta}}]})


LIMITE = (429, {"error": {"message": "Rate limit reached for model", "type": "tokens",
                          "code": "rate_limit_exceeded"}})


def proveedor(falso: GroqFalso, **extra) -> ProveedorGroq:
    return ProveedorGroq("gsk_prueba", http=httpx.Client(transport=httpx.MockTransport(falso.manejar)),
                         **extra)


@pytest.fixture
def groq(monkeypatch):
    """ASISTENTE_PROVEEDOR=groq con la API simulada en la app."""
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_prueba")
    falso = GroqFalso()
    app.dependency_overrides[get_proveedor] = lambda: proveedor(falso)
    yield falso
    app.dependency_overrides.pop(get_proveedor, None)


@pytest.fixture
def tecnico(client, session):
    return login_as(client, session, "Técnico", "tec@data.cr", "Tomás Técnico")


# --- Elegir el proveedor ------------------------------------------------------


def test_groq_is_chosen_with_its_key_and_the_default_qwen_model(monkeypatch):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_prueba")
    monkeypatch.delenv("GROQ_MODELO", raising=False)
    elegido = asis.crear_proveedor()
    assert isinstance(elegido, ProveedorGroq)
    assert elegido.modelo == GROQ_MODELO_POR_DEFECTO == "qwen/qwen3.8-27b"
    assert asis.ia_activa()

    monkeypatch.setenv("GROQ_MODELO", "llama-3.3-70b-versatile")
    assert asis.crear_proveedor().modelo == "llama-3.3-70b-versatile"


def test_groq_without_key_turns_the_ai_off(monkeypatch):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not asis.ia_activa()
    with pytest.raises(AsistenteNoConfigurado, match="GROQ_API_KEY"):
        asis.crear_proveedor()


def test_docker_keeps_local_qwen(monkeypatch):
    monkeypatch.delenv("ASISTENTE_PROVEEDOR", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_prueba")  # aunque esté, Docker no la usa
    assert isinstance(asis.crear_proveedor(), ProveedorQwen)


@pytest.mark.parametrize("valor,esperado", [(None, 20.0), ("10", 10.0), ("90", 25.0), ("x", 20.0)])
def test_timeout_stays_below_the_vercel_limit(monkeypatch, valor, esperado):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_prueba")
    if valor is None:
        monkeypatch.delenv("GROQ_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("GROQ_TIMEOUT", valor)
    elegido = asis.crear_proveedor()
    assert elegido.timeout == esperado
    # «Explicar con IA» hace hasta dos pedidos (reintento): siguen por debajo de 60 s.
    assert 2 * elegido.timeout < LIMITE_VERCEL


def test_a_shorter_timeout_is_respected_but_never_a_longer_one():
    falso = GroqFalso()
    groq = proveedor(falso, timeout=20.0)
    groq.responder("Sistema", [{"role": "user", "content": "hola"}], timeout=10.0)
    groq.responder("Sistema", [{"role": "user", "content": "hola"}], timeout=300.0)
    leidos = [r.extensions["timeout"]["read"] for r in falso.requests]
    assert leidos == [10.0, 20.0]


# --- Interfaz: responder, streaming y generar_json -----------------------------


def test_responder_sends_the_openai_request():
    falso = GroqFalso("<think>pienso</think>Hola, ¿en qué le ayudo?")
    texto = proveedor(falso).responder("Instrucciones", [{"role": "user", "content": "hola"}])

    assert texto == "Hola, ¿en qué le ayudo?"
    request, pedido = falso.requests[0], falso.pedidos[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer gsk_prueba"
    assert pedido["model"] == "qwen/qwen3.8-27b"
    assert pedido["reasoning_effort"] == "none"
    assert pedido["messages"] == [{"role": "system", "content": "Instrucciones"},
                                  {"role": "user", "content": "hola"}]


def test_reasoning_option_only_for_qwen_models():
    falso = GroqFalso()
    proveedor(falso, modelo="llama-3.3-70b-versatile").responder("S", [{"role": "user", "content": "x"}])
    assert "reasoning_effort" not in falso.pedidos[0]


def test_streaming_reads_server_sent_events():
    falso = GroqFalso("Texto que llega por partes.")
    partes = list(proveedor(falso).responder_stream("S", [{"role": "user", "content": "x"}]))
    assert "".join(partes) == "Texto que llega por partes."
    assert len(partes) == 2 and falso.pedidos[0]["stream"] is True


def test_generar_json_asks_for_the_schema():
    falso = GroqFalso('{"tipo": "otra"}')
    esquema = {"type": "object", "properties": {"tipo": {"type": "string"}}}
    texto = proveedor(falso).generar_json([{"role": "system", "content": "S"}], esquema, 0.0)

    assert texto == '{"tipo": "otra"}'
    formato = falso.pedidos[0]["response_format"]
    assert formato["type"] == "json_schema"
    assert formato["json_schema"]["schema"] == esquema
    assert falso.pedidos[0]["temperature"] == 0.0


def test_json_that_does_not_match_the_schema_is_returned_for_validation():
    falso = GroqFalso((400, {"error": {"code": "json_validate_failed", "message": "Generated JSON does not match",
                                       "failed_generation": '{"explicacion": 1}'}}))
    texto = proveedor(falso).generar_json([{"role": "system", "content": "S"}], {"type": "object"})
    assert texto == '{"explicacion": 1}'


def test_429_is_the_usage_limit():
    falso = GroqFalso(LIMITE)
    with pytest.raises(AsistenteOcupado, match="intente de nuevo en un minuto"):
        proveedor(falso).responder("S", [{"role": "user", "content": "x"}])
    with pytest.raises(AsistenteOcupado):
        list(proveedor(falso).responder_stream("S", [{"role": "user", "content": "x"}]))
    with pytest.raises(AsistenteOcupado):
        proveedor(falso).generar_json([{"role": "system", "content": "S"}], {"type": "object"})


# --- Chat con Groq -------------------------------------------------------------


def test_config_says_the_ai_is_available(client, groq, tecnico):
    assert client.get("/api/config").json()["ia_disponible"] is True


def test_free_chat_uses_groq(client, groq, tecnico):
    groq.respuestas = ["Puede usar el chat cualquier persona con cuenta en la ticketera."]
    datos = ask(client, tecnico, "quienes pueden usar el chat?").json()
    assert datos == {"respuesta": "Puede usar el chat cualquier persona con cuenta en la ticketera.",
                     "fuente": "ia"}
    assert groq.pedidos[0]["model"] == "qwen/qwen3.8-27b"


def test_free_chat_streaming_uses_groq(client, groq, tecnico):
    groq.respuestas = ["Puede usar el chat cualquier persona con cuenta."]
    resp = client.post("/api/asistente/stream", headers=tecnico,
                       json={"messages": [{"role": "user", "content": "quienes pueden usar el chat?"}]})
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    texto = "".join(e.get("t", "") for e in eventos)
    assert texto == "Puede usar el chat cualquier persona con cuenta."
    assert eventos[-1] == {"fin": True, "fuente": "ia"}


def test_free_chat_at_the_usage_limit_says_so(client, groq, tecnico):
    groq.respuestas = [LIMITE]
    resp = ask(client, tecnico, "quienes pueden usar el chat?")
    assert resp.status_code == 429
    assert resp.json()["detail"] == MENSAJE_IA_LIMITE == "La IA está ocupada, intente de nuevo en un minuto"

    resp = client.post("/api/asistente/stream", headers=tecnico,
                       json={"messages": [{"role": "user", "content": "quienes pueden usar el chat?"}]})
    eventos = [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    assert {"error": MENSAJE_IA_LIMITE} in eventos


def test_the_rest_of_the_chat_works_at_the_usage_limit(client, session, groq, tecnico, monkeypatch):
    """Con la redacción y la interpretación encendidas y Groq en 429, lo que
    calcula el servidor responde igual."""
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "true")
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")
    add_ticket(session, "Impresora")
    groq.respuestas = [LIMITE]
    for pregunta in ("¿Cuántos tickets hay?", "que hace cada rol", "¿qué hora es?"):
        resp = ask(client, tecnico, pregunta)
        assert resp.status_code == 200, (pregunta, resp.text)
        assert resp.json()["fuente"] == "directa"


def test_interpretation_at_the_usage_limit_does_not_call_the_free_ai(client, groq, tecnico, monkeypatch):
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")
    groq.respuestas = [LIMITE]
    resp = ask(client, tecnico, "zxqw plmok")
    assert resp.status_code == 200
    assert resp.json() == {"respuesta": MENSAJE_IA_LIMITE, "fuente": "directa"}
    assert len(groq.pedidos) == 1  # solo la interpretación: no se insistió con la IA libre
    assert "response_format" in groq.pedidos[0]


def test_misspelled_question_is_interpreted_by_groq(client, session, groq, tecnico, monkeypatch):
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")
    add_ticket(session, "Impresora")
    groq.respuestas = [json.dumps({"tipo": "conteo", "estado": "todos", "periodo": None,
                                   "persona": None, "rol": None, "ticket": None})]
    datos = ask(client, tecnico, "kuantoz tikez ai en total").json()
    assert datos["fuente"] == "directa"
    assert "1" in datos["respuesta"]
    assert groq.pedidos[0]["response_format"]["type"] == "json_schema"


def test_answers_are_written_by_groq(client, session, groq, tecnico, monkeypatch):
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "true")
    add_ticket(session, "Impresora")
    groq.respuestas = ["En total hay **1** ticket."]
    datos = ask(client, tecnico, "¿Cuántos tickets hay?").json()
    assert datos == {"respuesta": "En total hay **1** ticket.", "fuente": "ia_datos"}
    assert groq.pedidos[0]["messages"][0]["content"] == asis.INSTRUCCIONES_REDACCION


# --- «Explicar con IA» con Groq -------------------------------------------------


def test_explain_button_is_available_with_groq(client, session, groq, tecnico):
    ticket = nuevo_ticket(session)
    datos = client.get(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico).json()
    assert datos["ia_disponible"] is True


def test_explain_with_groq(client, session, groq, tecnico):
    groq.respuestas = [json.dumps(BUENA, ensure_ascii=False)]
    ticket = nuevo_ticket(session)
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200, resp.text
    assert resp.json()["explicacion"]["explicacion"].startswith("José Solano reporta")
    pedido = groq.pedidos[0]
    assert pedido["response_format"]["json_schema"]["schema"] == asis_explicacion_esquema()
    assert pedido["temperature"] == 0.1


def asis_explicacion_esquema():
    from backend.services.explicacion_service import ESQUEMA_IA

    return ESQUEMA_IA


def test_explain_retries_once_when_the_json_is_wrong(client, session, groq, tecnico):
    groq.respuestas = ["esto no es JSON", json.dumps(BUENA, ensure_ascii=False)]
    ticket = nuevo_ticket(session)
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200, resp.text
    assert len(groq.pedidos) == 2


def test_explain_gives_up_after_two_wrong_answers(client, session, groq, tecnico):
    groq.respuestas = ["mal", "mal otra vez"]
    ticket = nuevo_ticket(session)
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code >= 400
    assert len(groq.pedidos) == 2


def test_explain_at_the_usage_limit_says_so(client, session, groq, tecnico):
    groq.respuestas = [LIMITE]
    ticket = nuevo_ticket(session)
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code >= 400
    assert resp.json()["detail"] == MENSAJE_IA_LIMITE
    assert len(groq.pedidos) == 1  # un 429 no se reintenta
