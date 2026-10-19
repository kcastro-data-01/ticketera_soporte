"""«Explicar con IA» con Ollama simulado: poco texto, texto largo y confuso,
JSON inválido, Ollama caído, caché y permisos."""

import json
import logging

import httpx
import pytest
from sqlalchemy import select

from backend.main import app
from backend.models import Comment, Ticket, TicketExplanation
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service
from backend.services import explicacion_service as ex
from backend.services.asistente_service import ProveedorQwen
from backend.tests.test_asistente import login_as

BUENA = {
    "resumen": "La persona dice que algo no funciona, pero no dice qué.",
    "informacion_faltante": ["Qué equipo falla", "Desde cuándo", "Qué error aparece", "Qué intentó", "Sobra"],
    "preguntas_sugeridas": ["¿Qué equipo es?", "¿Desde cuándo pasa?", "¿Qué error ves?"],
    "puntos_clave": [],
    "siguiente_paso": "Llamar a la persona para preguntar qué equipo falla.",
    "categoria_sugerida": {"valor": "Hardware", "razon": "Parece un equipo."},
    "prioridad_sugerida": {"valor": "Media", "razon": "No dice que esté detenida."},
}


class OllamaFalso:
    """Devuelve las respuestas en orden; guarda cada pedido."""

    def __init__(self, respuestas=None, error=None):
        self.respuestas = list(respuestas or [json.dumps(BUENA, ensure_ascii=False)])
        self.error = error
        self.pedidos = []

    def manejar(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.pedidos.append(cuerpo)
        if self.error is not None:
            raise self.error
        texto = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        return httpx.Response(200, json={"message": {"content": texto}})

    def ultimo_ticket(self) -> str:
        return self.pedidos[-1]["messages"][3]["content"]


@pytest.fixture
def ollama():
    falso = OllamaFalso()
    proveedor = ProveedorQwen("http://ollama:11434", "qwen3:0.6b",
                              http=httpx.Client(transport=httpx.MockTransport(falso.manejar)))
    app.dependency_overrides[get_proveedor] = lambda: proveedor
    yield falso
    app.dependency_overrides.pop(get_proveedor, None)


@pytest.fixture
def tecnico(client, session):
    return login_as(client, session, "Técnico", "tec@tec.local", "José Solano")


def nuevo_ticket(session, title="No sirve", description="no sirve", **extra):
    ticket = Ticket(title=title, description=description, category=extra.get("category", "Software"),
                    priority=extra.get("priority", "Media"))
    session.add(ticket)
    session.commit()
    return ticket


LARGO = "\n\n".join([
    "Hola buenas, les escribo porque desde el lunes la impresora HP 4020 del segundo piso marca "
    "error 49 cada vez que alguien manda a imprimir algo largo.",
    "Mi compañera dice que a ella también le pasaba con la otra impresora el año pasado y que "
    "se arregló sola pero no sé si es lo mismo porque esa era de otra marca y estaba en otro piso.",
    "También quería comentar que el aire acondicionado de la sala está muy frío y que la cafetera "
    "no funciona bien desde hace semanas, aunque eso no es urgente para nada.",
    "Además el wifi a veces anda lento en la tarde pero creo que es porque hay mucha gente.",
    "Ya reinicié la impresora dos veces y cambié el tóner, pero sigue saliendo el mismo error.",
    "Necesitamos imprimir los contratos del viernes, por favor ayúdenme lo antes posible.",
] * 2)


# --- Claridad: la calcula el servidor --------------------------------------


def test_little_text_is_poco_detalle_with_all_basic_data_missing(session):
    claridad = ex.calcular_claridad(nuevo_ticket(session))
    assert claridad["claridad"] == "poco detalle"
    assert len(claridad["faltantes"]) == 4
    assert "2 palabras" in claridad["motivo"]


def test_long_text_is_confusa(session):
    claridad = ex.calcular_claridad(nuevo_ticket(session, "Impresora", LARGO))
    assert claridad["claridad"] == "confusa"
    assert "larga" in claridad["motivo"]


def test_complete_text_is_clara(session):
    ticket = nuevo_ticket(session, "Impresora del 2do piso",
                          "Desde ayer la impresora HP del segundo piso muestra el error 49 al imprimir. "
                          "Ya la reinicié y cambié el tóner, pero sigue igual. Somos cinco personas.")
    claridad = ex.calcular_claridad(ticket)
    assert claridad["claridad"] == "clara"
    assert claridad["faltantes"] == []


# --- Lo que se le manda a Ollama -------------------------------------------


def test_little_text_end_to_end(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    datos = resp.json()
    assert datos["claridad"] == "poco detalle"  # del servidor, no de la IA
    assert datos["vigente"] is True and datos["desde_cache"] is False
    assert datos["modelo"] == "qwen3:0.6b"
    e = datos["explicacion"]
    assert e["resumen"].startswith("La persona dice")
    assert len(e["informacion_faltante"]) == 4  # máximo 4 aunque la IA mande 5
    assert e["categoria_sugerida"] == {"valor": "Hardware", "razon": "Parece un equipo."}

    pedido = ollama.pedidos[0]
    assert pedido["think"] is False
    assert pedido["options"]["temperature"] == 0.1
    assert pedido["options"]["num_ctx"] == asistente_service.QWEN_CONTEXTO
    assert pedido["format"]["required"] == [
        "resumen", "informacion_faltante", "preguntas_sugeridas", "puntos_clave", "siguiente_paso"]
    # Ejemplo completo (entrada y salida) antes del ticket real.
    roles = [m["role"] for m in pedido["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert json.loads(pedido["messages"][2]["content"]) == ex.EJEMPLO_SALIDA
    assert "no adivines" in pedido["messages"][0]["content"]
    texto = ollama.ultimo_ticket()
    assert "Título: No sirve" in texto and "no sirve" in texto
    assert "Datos que el sistema no encontró en el texto: Qué equipo" in texto


def test_long_and_confusing_ticket_sends_only_important_parts(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session, "Impresora", LARGO, category="Hardware")
    for i in range(6):
        session.add(Comment(ticket_id=ticket.id, author="José Solano", content=f"Comentario {i} " + "x" * 500))
    session.commit()
    ollama.respuestas = [json.dumps({**BUENA, "puntos_clave": [
        "La impresora HP 4020 marca error 49 desde el lunes.",
        "Ya la reiniciaron y cambiaron el tóner.",
        "Necesitan imprimir contratos el viernes.",
    ]}, ensure_ascii=False)]

    datos = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico).json()
    assert datos["claridad"] == "confusa"
    assert datos["explicacion"]["puntos_clave"][0].startswith("La impresora HP 4020")

    texto = ollama.ultimo_ticket()
    assert ex.OMITIDO in texto
    assert "desde el lunes la impresora HP 4020" in texto  # primer párrafo
    assert "contratos del viernes" in texto  # último párrafo
    assert "Comentario 5" in texto and "Comentario 2" not in texto  # últimos 3
    # Todo el pedido entra holgado en num_ctx (≈ 4 caracteres por token).
    total = sum(len(m["content"]) for m in ollama.pedidos[0]["messages"])
    assert total < 4096 * 2.5


def test_invalid_json_is_retried_once(client, session, ollama, tecnico, caplog, monkeypatch):
    monkeypatch.setattr(asistente_service.logger, "propagate", True)
    ticket = nuevo_ticket(session)
    ollama.respuestas = ['{"resumen": "a medias', json.dumps(BUENA)]
    with caplog.at_level(logging.WARNING, logger=asistente_service.logger.name):
        resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    assert len(ollama.pedidos) == 2
    reintento = ollama.pedidos[1]["messages"]
    assert reintento[-2] == {"role": "assistant", "content": '{"resumen": "a medias'}
    assert "JSON válido" in reintento[-1]["content"]
    assert "respuesta inválida (intento 1)" in caplog.text


def test_invalid_json_twice_shows_an_error(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    ollama.respuestas = ["esto no es json"]
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 502
    assert resp.json()["detail"] == ex.MENSAJE_INVALIDA
    assert len(ollama.pedidos) == 2
    assert session.scalar(select(TicketExplanation)) is None


def test_missing_required_field_counts_as_invalid(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    sin_paso = {k: v for k, v in BUENA.items() if k != "siguiente_paso"}
    ollama.respuestas = [json.dumps(sin_paso), json.dumps(BUENA)]
    assert client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico).status_code == 200
    assert len(ollama.pedidos) == 2


def test_bad_suggestions_are_dropped_and_the_rest_is_shown(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    ollama.respuestas = [json.dumps({**BUENA, "categoria_sugerida": {"valor": "Telefonía"},
                                     "prioridad_sugerida": "alta"})]
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    e = resp.json()["explicacion"]
    assert e["categoria_sugerida"] is None and e["prioridad_sugerida"] is None
    assert e["resumen"] == BUENA["resumen"]
    assert len(ollama.pedidos) == 1  # no hizo falta reintentar


def test_empty_lists_are_filled_with_server_questions(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    ollama.respuestas = [json.dumps({**BUENA, "informacion_faltante": [], "preguntas_sugeridas": []})]
    e = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico).json()["explicacion"]
    assert e["informacion_faltante"][0].startswith("Qué equipo")
    assert e["preguntas_sugeridas"][0].startswith("¿Qué equipo")


def test_json_inside_code_fence_is_accepted():
    texto = "```json\n" + json.dumps(BUENA) + "\n```"
    assert ex.validar_respuesta(texto)["resumen"] == BUENA["resumen"]


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("lento")])
def test_ollama_down_shows_not_available(client, session, ollama, tecnico, error, caplog, monkeypatch):
    monkeypatch.setattr(asistente_service.logger, "propagate", True)
    ollama.error = error
    ticket = nuevo_ticket(session)
    with caplog.at_level(logging.ERROR, logger=asistente_service.logger.name):
        resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "La IA no está disponible en este momento"
    assert f"explicar ticket #{ticket.id}: error con qwen3:0.6b" in caplog.text


# --- Caché ------------------------------------------------------------------------


def test_saved_explanation_is_reused_until_the_ticket_changes(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    url = f"/api/tickets/{ticket.id}/explicacion"

    assert client.get(url, headers=tecnico).json()["explicacion"] is None
    client.post(url, headers=tecnico)
    assert len(ollama.pedidos) == 1

    # Abrir el ticket otra vez: se usa la guardada, sin llamar a la IA.
    guardada = client.get(url, headers=tecnico).json()
    assert guardada["vigente"] is True and guardada["explicacion"]["resumen"]
    assert client.post(url, headers=tecnico).json()["desde_cache"] is True
    assert len(ollama.pedidos) == 1

    # El ticket cambia (nuevo comentario): queda desactualizada y se regenera.
    client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Es la impresora HP"}, headers=tecnico)
    assert client.get(url, headers=tecnico).json()["vigente"] is False
    nueva = client.post(url, headers=tecnico).json()
    assert nueva["vigente"] is True and nueva["desde_cache"] is False
    assert len(ollama.pedidos) == 2
    assert "Es la impresora HP" in ollama.ultimo_ticket()


def test_regenerar_forces_a_new_call(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    url = f"/api/tickets/{ticket.id}/explicacion"
    client.post(url, headers=tecnico)
    client.post(url + "?regenerar=true", headers=tecnico)
    assert len(ollama.pedidos) == 2
    assert len(session.scalars(select(TicketExplanation)).all()) == 1


def test_explanation_is_deleted_with_the_ticket(client, session, ollama, auth_client):
    ticket = nuevo_ticket(session)
    assert auth_client.post(f"/api/tickets/{ticket.id}/explicacion").status_code == 200
    assert auth_client.delete(f"/api/tickets/{ticket.id}").status_code == 204
    session.expire_all()
    assert session.scalar(select(TicketExplanation)) is None


# --- Permisos ---------------------------------------------------------------------


@pytest.mark.parametrize("rol,correo,codigo", [
    ("Técnico", "t@x.local", 200),
    ("Supervisor", "s@x.local", 200),
    ("Administrador", "a@x.local", 200),
    ("Solicitante", "so@x.local", 403),
])
def test_roles(client, session, ollama, rol, correo, codigo):
    ticket = nuevo_ticket(session)
    headers = login_as(client, session, rol, correo, "Persona")
    assert client.post(f"/api/tickets/{ticket.id}/explicacion", headers=headers).status_code == codigo
    assert client.get(f"/api/tickets/{ticket.id}/explicacion", headers=headers).status_code == codigo


def test_missing_ticket_and_login(client, session, ollama, tecnico):
    assert client.post("/api/tickets/999/explicacion", headers=tecnico).status_code == 404
    assert client.post("/api/tickets/1/explicacion").status_code == 401
