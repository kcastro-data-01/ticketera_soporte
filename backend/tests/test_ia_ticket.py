"""La IA responde con el contenido real del ticket (Ollama simulado)."""

import json
import logging

import httpx
import pytest

from backend.main import app
from backend.models import Comment, Ticket
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service as a
from backend.services.asistente_service import MENSAJE_NO_DISPONIBLE, ProveedorQwen
from backend.tests.test_asistente import login_as


class OllamaFalso:
    """Ollama simulado: guarda cada pedido y responde lo que se le diga."""

    def __init__(self, respuesta="Respuesta de Qwen", estado=200, error=None):
        self.pedidos = []
        self.respuesta = respuesta
        self.estado = estado
        self.error = error

    def manejar(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.pedidos.append(cuerpo)
        if self.error is not None:
            raise self.error
        if cuerpo.get("stream"):
            lineas = [json.dumps({"message": {"content": self.respuesta}, "done": True})]
            return httpx.Response(self.estado, content="\n".join(lineas).encode())
        return httpx.Response(self.estado, json={"message": {"content": self.respuesta}})

    def system(self, i=-1) -> str:
        return self.pedidos[i]["messages"][0]["content"]


@pytest.fixture
def ollama():
    falso = OllamaFalso()
    proveedor = ProveedorQwen("http://ollama:11434", "qwen3:0.6b",
                              http=httpx.Client(transport=httpx.MockTransport(falso.manejar)))
    app.dependency_overrides[get_proveedor] = lambda: proveedor
    yield falso
    app.dependency_overrides.pop(get_proveedor, None)


@pytest.fixture
def log_ia(caplog, monkeypatch):
    monkeypatch.setattr(a.logger, "propagate", True)
    caplog.set_level(logging.INFO, logger=a.logger.name)
    return caplog


@pytest.fixture
def dos_tickets(session):
    t1 = Ticket(title="Impresora no imprime", description="La HP del 2do piso marca error 49.",
                category="Hardware", priority="Alta")
    t2 = Ticket(title="No puedo entrar al VPN", description="Desde ayer dice credenciales inválidas.",
                category="Red", priority="Media", state="En proceso")
    session.add_all([t1, t2])
    session.commit()
    for i in range(7):
        session.add(Comment(ticket_id=t1.id, author="José Solano", content=f"Comentario {i}"))
    session.commit()
    return t1, t2


def preguntar(client, headers, texto, ticket_id=None, ruta="/api/asistente"):
    cuerpo = {"messages": [{"role": "user", "content": texto}]}
    if ticket_id is not None:
        cuerpo["ticket_id"] = ticket_id
    return client.post(ruta, json=cuerpo, headers=headers)


def test_two_tickets_give_two_different_prompts_with_full_content(client, session, ollama, dos_tickets):
    t1, t2 = dos_tickets
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")

    for t in (t1, t2):
        resp = preguntar(client, headers, f"¿Cómo resuelvo el ticket #{t.id}?")
        assert resp.json() == {"respuesta": "Respuesta de Qwen", "fuente": "ia"}

    p1, p2 = ollama.system(0), ollama.system(1)
    assert p1 != p2
    assert "Título: Impresora no imprime" in p1 and "error 49" in p1
    assert "Categoría: Hardware · Prioridad: Alta · Estado: Nuevo" in p1
    assert "Título: No puedo entrar al VPN" in p2 and "credenciales inválidas" in p2
    assert "Categoría: Red · Prioridad: Media · Estado: En proceso" in p2
    # Solo los últimos 5 comentarios.
    assert "Últimos comentarios (5 de 7)" in p1
    assert "Comentario 6" in p1 and "Comentario 1" not in p1
    assert "Sin comentarios." in p2


@pytest.mark.parametrize("pregunta", [
    "¿Cómo resuelvo el ticket #{id}?",
    "¿Qué hago con el ticket #{id}?",
    "¿Qué me recomiendas para el ticket #{id}?",
    "¿Por qué falla el ticket #{id}?",
    "Necesito ayuda con el ticket #{id}",
    "Resume el ticket #{id}",
])
def test_content_questions_go_to_the_ai_not_to_fixed_text(client, session, ollama, dos_tickets, pregunta):
    t1, _ = dos_tickets
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, pregunta.format(id=t1.id))
    assert resp.json()["fuente"] == "ia"
    assert "error 49" in ollama.system()


def test_how_to_questions_about_the_app_still_use_the_guide(client, session, ollama, dos_tickets):
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, "¿Cómo cierro un ticket?")
    assert resp.json()["fuente"] == "directa"
    assert ollama.pedidos == []


def test_this_ticket_uses_the_ticket_on_screen(client, session, ollama, dos_tickets):
    _, t2 = dos_tickets
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, "¿Qué hago con este ticket?", ticket_id=t2.id)
    assert resp.json()["fuente"] == "ia"
    assert f"está viendo el ticket #{t2.id}" in ollama.system()
    assert "credenciales inválidas" in ollama.system()


def test_this_ticket_state_is_answered_directly(client, session, ollama, dos_tickets):
    _, t2 = dos_tickets
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, "¿Qué estado tiene este ticket?", ticket_id=t2.id)
    assert resp.json()["fuente"] == "directa"
    assert "En proceso" in resp.json()["respuesta"]


def test_counting_questions_on_detail_page_still_count(client, session, ollama, dos_tickets):
    t1, _ = dos_tickets
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, "¿Cuántos tickets hay?", ticket_id=t1.id)
    assert resp.json() == {"respuesta": "Hay 2 tickets visibles para ti en total.", "fuente": "directa"}


def test_requester_cannot_get_another_ticket_on_screen(client, session, ollama, dos_tickets):
    t1, _ = dos_tickets
    headers = login_as(client, session, "Solicitante", "soli@soli.local", "Andrea Castillo")
    preguntar(client, headers, "¿Qué hago con este ticket?", ticket_id=t1.id)
    system = ollama.system()
    assert "error 49" not in system
    assert "no está entre los que esta persona puede ver" in system


@pytest.mark.parametrize("ruta", ["/api/asistente", "/api/asistente/stream"])
@pytest.mark.parametrize("falla,detalle", [
    (dict(error=httpx.ConnectError("refused")), "No se pudo conectar con Ollama"),
    (dict(error=httpx.ReadTimeout("lento")), "tardó demasiado"),
    (dict(estado=500, respuesta="x"), "Ollama respondió con un error (500)"),
    (dict(respuesta=""), "respuesta vacía"),
    (dict(respuesta="<think>solo pienso</think>"), "respuesta vacía"),
])
def test_ollama_failures_show_generic_message_and_are_logged(
        client, session, ollama, dos_tickets, log_ia, ruta, falla, detalle):
    t1, _ = dos_tickets
    for clave, valor in falla.items():
        setattr(ollama, clave, valor)
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    resp = preguntar(client, headers, f"¿Qué hago con el ticket #{t1.id}?", ticket_id=t1.id, ruta=ruta)
    if ruta == "/api/asistente":
        assert resp.status_code == 502
        assert resp.json()["detail"] == MENSAJE_NO_DISPONIBLE
    else:
        assert [json.loads(l) for l in resp.text.splitlines()] == [{"error": MENSAJE_NO_DISPONIBLE}]
    assert "error con qwen3:0.6b" in log_ia.text
    assert detalle in log_ia.text
    assert f"ticket en pantalla #{t1.id}" in log_ia.text


def test_ollama_parameters_and_timeout(monkeypatch):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "qwen")
    monkeypatch.setenv("QWEN_TIMEOUT", "45")
    monkeypatch.setenv("QWEN_MODELO", "qwen3:1.7b")
    proveedor = a.crear_proveedor()
    assert proveedor.modelo == "qwen3:1.7b"
    assert proveedor.http.timeout.read == 45
    assert proveedor.http.timeout.connect == 5
    monkeypatch.delenv("QWEN_TIMEOUT")
    assert a.crear_proveedor().http.timeout.read == 90


def test_request_ticket_id_must_be_positive(client, session, ollama):
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    assert preguntar(client, headers, "hola", ticket_id=0).status_code == 422
