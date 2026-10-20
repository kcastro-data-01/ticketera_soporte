"""El límite de tiempo va en la propia petición a Ollama: al vencerse se
cierra la conexión (Ollama deja de generar) y no queda una petición
abandonada delante de la siguiente. El total tolera errores de escritura
(«cuatos ticketes hay ?») y el modelo queda siempre cargado."""

import json
import socket
import threading
import time

import httpx
import pytest

from backend.services.asistente_service import (
    QWEN_MAX_TICKETS,
    IATardo,
    ProveedorClaude,
    ProveedorQwen,
    detectar_consulta,
)
from backend.tests.test_asistente import add_ticket, ask, fake_claude, login_as  # noqa: F401 (fixture)


@pytest.fixture
def ollama_lento():
    """Servidor que lee la petición y nunca responde; ``cerrada`` se activa
    cuando el cliente cierra la conexión (lo que hace abortar a Ollama)."""
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    cerrada = threading.Event()

    def atender():
        conexion, _ = servidor.accept()
        conexion.settimeout(5)
        try:
            conexion.recv(65536)
            while conexion.recv(65536):
                pass
            cerrada.set()  # recv() vacío: el cliente cerró
        except OSError:
            cerrada.set()
        finally:
            conexion.close()

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.getsockname()[1]}", cerrada
    servidor.close()


@pytest.mark.parametrize("pedir", [
    lambda q, t: q.generar_json([{"role": "system", "content": "S"}], {"type": "object"}, 0.0, timeout=t),
    lambda q, t: q.responder("S", [{"role": "user", "content": "hola"}], timeout=t),
])
def test_timeout_closes_the_connection(ollama_lento, pedir):
    url, cerrada = ollama_lento
    qwen = ProveedorQwen(url, "qwen3:0.6b", timeout=90)

    inicio = time.monotonic()
    with pytest.raises(IATardo):
        pedir(qwen, 0.3)

    assert time.monotonic() - inicio < 2  # no esperó los 90 s del cliente
    assert cerrada.wait(2), "la conexión siguió abierta: Ollama seguiría generando"


def test_without_timeout_the_client_default_is_used():
    vistos = []

    def handler(request):
        vistos.append(request.extensions["timeout"])
        return httpx.Response(200, json={"message": {"content": "{}"}})

    qwen = ProveedorQwen("http://ollama:11434", "qwen3:0.6b", timeout=90,
                         http=httpx.Client(transport=httpx.MockTransport(handler),
                                           timeout=httpx.Timeout(90, connect=5)))
    qwen.generar_json([{"role": "system", "content": "S"}], {}, timeout=10)
    qwen.generar_json([{"role": "system", "content": "S"}], {})
    assert vistos[0] == {"connect": 5, "read": 10, "write": 10, "pool": 10}
    assert vistos[1]["read"] == 90


def test_claude_timeout_is_ia_tardo():
    import anthropic

    class Mensajes:
        def create(self, **kwargs):
            assert kwargs["timeout"] == 10
            raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com"))

    class Cliente:
        beta = type("Beta", (), {"messages": Mensajes()})()

    with pytest.raises(IATardo):
        ProveedorClaude(Cliente()).generar_json([{"role": "system", "content": "S"}], {}, timeout=10)


def test_keep_alive_forever_in_every_request():
    cuerpos = []

    def handler(request):
        cuerpos.append(json.loads(request.content))
        if request.url.path == "/api/chat" and cuerpos[-1].get("stream"):
            return httpx.Response(200, text=json.dumps({"message": {"content": "Hola"}, "done": True}) + "\n")
        return httpx.Response(200, json={"message": {"content": "Hola"}})

    qwen = ProveedorQwen("http://ollama:11434", "qwen3:0.6b",
                         http=httpx.Client(transport=httpx.MockTransport(handler)))
    qwen.responder("S", [{"role": "user", "content": "hola"}])
    list(qwen.responder_stream("S", [{"role": "user", "content": "hola"}]))
    qwen.generar_json([{"role": "system", "content": "S"}], {})
    qwen.precargar()
    assert len(cuerpos) == 4
    assert all(c["keep_alive"] == -1 for c in cuerpos)


@pytest.mark.parametrize("pregunta", [
    "cuatos ticketes hay ?", "cunatos tikets ai", "cauntos tickets ay", "cuanos tickets hay",
    "cuantos tiketes hay en total", "Cuátos tíckets hay?",
])
def test_total_tolerates_misspellings(pregunta):
    assert detectar_consulta(pregunta) == "total"


@pytest.mark.parametrize("pregunta, clave", [
    ("cuatos resueltos ai", "resueltos"),
    ("cunatos tikets en proceso", "en_proceso"),
    ("cuatro tickets", None),  # «cuatro» no es «cuántos»
    ("ay no se", None),
])
def test_misspelled_how_many_with_a_state(pregunta, clave):
    assert detectar_consulta(pregunta) == clave


def test_misspelled_total_answers_at_once_without_ai(client, session, fake_claude):
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    add_ticket(session, "Impresora sin tinta")
    add_ticket(session, "Monitor apagado")
    resp = ask(client, headers, "cuatos ticketes hay ?").json()
    assert resp == {"respuesta": "Hay 2 tickets visibles para ti en total.", "fuente": "directa"}
    assert fake_claude.calls == []


def test_free_ai_prompt_is_shorter():
    assert QWEN_MAX_TICKETS == 2
