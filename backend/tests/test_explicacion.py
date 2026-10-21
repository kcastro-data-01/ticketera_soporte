"""«Explicar con IA» con Ollama simulado: poco texto, texto largo y confuso,
JSON inválido, Ollama caído, caché, permisos y el pedido desde el chat."""

import json
import logging

import httpx
import pytest
from sqlalchemy import select

from backend.main import app
from backend.models import Comment, Ticket, TicketExplanation, User
from backend.routers.asistente import get_proveedor
from backend.services import asistente_service
from backend.services import explicacion_service as ex
from backend.services.asistente_service import ProveedorQwen
from backend.tests.test_asistente import login_as

BUENA = {
    "explicacion": ("En este ticket, José Solano dice que algo no sirve, pero no cuenta qué es. "
                    "Lo que busca es que se lo arreglen. Falta saber qué equipo falla y desde cuándo."),
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
                    priority=extra.get("priority", "Media"), created_by_id=extra.get("created_by_id"))
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
    assert e["explicacion"] == BUENA["explicacion"]
    assert e["resumen"].startswith("La persona dice")
    assert len(e["informacion_faltante"]) == 4  # máximo 4 aunque la IA mande 5
    assert e["categoria_sugerida"] == {"valor": "Hardware", "razon": "Parece un equipo."}

    pedido = ollama.pedidos[0]
    assert pedido["think"] is False
    assert pedido["options"]["temperature"] == 0.1
    assert pedido["options"]["num_ctx"] == asistente_service.QWEN_CONTEXTO
    assert pedido["format"]["required"] == [
        "explicacion", "resumen", "informacion_faltante", "preguntas_sugeridas", "puntos_clave", "siguiente_paso"]
    # Ejemplo completo (entrada y salida) antes del ticket real.
    roles = [m["role"] for m in pedido["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert json.loads(pedido["messages"][2]["content"]) == ex.EJEMPLO_SALIDA
    assert "no adivine" in pedido["messages"][0]["content"]
    texto = ollama.ultimo_ticket()
    assert "Título: No sirve" in texto and "no sirve" in texto
    assert "Datos que el sistema no encontró en el texto: Qué equipo" in texto
    assert "Reporta: no se sabe" in texto


def test_prompt_has_the_printer_example_and_who_reports(client, session, ollama, tecnico):
    autor = session.scalar(select(User).where(User.email == "tec@tec.local"))
    ticket = nuevo_ticket(session, created_by_id=autor.id)
    client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    mensajes = ollama.pedidos[0]["messages"]
    assert "explicacion: de 3 a 5 oraciones" in mensajes[0]["content"]
    assert "Título: Impresora\nReporta: Laura Méndez" in mensajes[1]["content"]
    ejemplo = json.loads(mensajes[2]["content"])["explicacion"]
    assert ejemplo.startswith("En este ticket, Laura Méndez reporta que una impresora no enciende.")
    assert "parece un problema de Hardware" in ejemplo
    assert "Reporta: José Solano" in ollama.ultimo_ticket()


@pytest.mark.parametrize("mala", [
    "Título: No sirve\nCategoría: Software\nEstado: Nuevo",
    "- La persona reporta un problema.\n- Falta saber qué equipo es y desde cuándo pasa.",
    "No sirve algo.",
    "",
])
def test_explanation_that_copies_fields_or_is_too_short_is_retried(client, session, ollama, tecnico, mala):
    ticket = nuevo_ticket(session)
    ollama.respuestas = [json.dumps({**BUENA, "explicacion": mala}), json.dumps(BUENA)]
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    assert len(ollama.pedidos) == 2
    assert resp.json()["explicacion"]["explicacion"] == BUENA["explicacion"]


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


def test_saved_explanation_without_narrative_is_generated_again(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    url = f"/api/tickets/{ticket.id}/explicacion"
    client.post(url, headers=tecnico)
    guardada = session.scalar(select(TicketExplanation))
    vieja = {k: v for k, v in BUENA.items() if k != "explicacion"}
    guardada.content = json.dumps(vieja)  # como las guardadas antes del cambio
    session.commit()

    assert client.get(url, headers=tecnico).json()["explicacion"]["explicacion"] == ""
    nueva = client.post(url, headers=tecnico).json()
    assert nueva["desde_cache"] is False
    assert nueva["explicacion"]["explicacion"] == BUENA["explicacion"]
    assert len(ollama.pedidos) == 2


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


# --- Desde el chat -----------------------------------------------------------------


def preguntar(client, headers, texto, ticket_id=None, stream=False):
    cuerpo = {"messages": [{"role": "user", "content": texto}]}
    if ticket_id is not None:
        cuerpo["ticket_id"] = ticket_id
    if stream:
        resp = client.post("/api/asistente/stream", json=cuerpo, headers=headers)
        return [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    return client.post("/api/asistente", json=cuerpo, headers=headers)


def test_chat_explicar_tickete_uses_the_explanation_not_the_template(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    resp = preguntar(client, tecnico, f"explicar tickete #{ticket.id}")
    assert resp.status_code == 200
    datos = resp.json()
    assert datos["fuente"] == "ia"
    assert datos["respuesta"].startswith(BUENA["explicacion"])
    assert "Preguntas que puede hacerle:\n1. ¿Qué equipo es?" in datos["respuesta"]
    # Ni la plantilla del ticket ni el chat libre: el pedido es el de «Explicar con IA».
    assert "Título:" not in datos["respuesta"] and "Categoría" not in datos["respuesta"]
    assert len(ollama.pedidos) == 1
    assert ollama.pedidos[0]["format"] == ex.ESQUEMA_IA
    assert session.scalar(select(TicketExplanation)) is not None  # queda guardada para el panel


@pytest.mark.parametrize("pregunta", [
    "explicame el tiket {id}",
    "Explicá el tikete #{id}",
    "de qué trata el ticket {id}?",
    "qué quiere la persona del #{id}",
    "no entiendo el ticket #{id}",
    "resumí el ticket {id}",
])
def test_chat_detects_explanation_requests_with_typos(client, session, ollama, tecnico, pregunta):
    ticket = nuevo_ticket(session)
    datos = preguntar(client, tecnico, pregunta.format(id=ticket.id)).json()
    assert datos["fuente"] == "ia"
    assert datos["respuesta"].startswith(BUENA["explicacion"])
    assert ollama.pedidos[0]["format"] == ex.ESQUEMA_IA


def test_chat_explains_este_ticket_on_screen_and_streams(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    eventos = preguntar(client, tecnico, "explicame este ticket", ticket_id=ticket.id, stream=True)
    assert eventos[0]["t"].startswith(BUENA["explicacion"])
    assert eventos[-1] == {"fin": True, "fuente": "ia"}
    # La segunda vez se reutiliza la guardada (sigue siendo texto de la IA).
    preguntar(client, tecnico, "explicame este ticket", ticket_id=ticket.id, stream=True)
    assert len(ollama.pedidos) == 1


def test_chat_explanation_when_ollama_fails_is_an_error_not_a_template(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    ollama.error = httpx.ConnectError("refused")
    eventos = preguntar(client, tecnico, f"explicar ticket #{ticket.id}", stream=True)
    assert eventos == [{"error": "La IA no está disponible en este momento"}]
    assert preguntar(client, tecnico, f"explicar ticket #{ticket.id}").status_code == 502


def test_chat_invalid_explanation_twice_is_an_error(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    ollama.respuestas = ["esto no es json"]
    eventos = preguntar(client, tecnico, f"explicar ticket #{ticket.id}", stream=True)
    assert eventos == [{"error": "La IA no está disponible en este momento"}]


def test_chat_explanation_of_missing_ticket_is_a_server_answer(client, session, ollama, tecnico):
    datos = preguntar(client, tecnico, "explicar ticket #999").json()
    assert datos == {"respuesta": "No encontré el ticket #999 entre los tickets que puede ver.",
                     "fuente": "directa"}
    assert ollama.pedidos == []


def test_requester_keeps_the_normal_chat(client, session, ollama):
    headers = login_as(client, session, "Solicitante", "so@x.local", "Laura Méndez")
    propio = nuevo_ticket(session, created_by_id=session.scalar(
        select(User).where(User.email == "so@x.local")).id)
    ajeno = nuevo_ticket(session)
    ollama.respuestas = ["Tu ticket trata de algo que no funciona."]

    datos = preguntar(client, headers, f"explicame mi ticket #{propio.id}").json()
    assert datos["fuente"] == "ia"
    assert "format" not in ollama.pedidos[-1]  # chat normal, no «Explicar con IA»
    assert session.scalar(select(TicketExplanation)) is None

    # Un ticket ajeno nunca llega al modelo con su contenido.
    preguntar(client, headers, f"explicame el ticket #{ajeno.id}")
    system = ollama.pedidos[-1]["messages"][0]["content"]
    assert f"Ticket #{ajeno.id}: no existe o no está entre los que esta persona puede ver." in system


def test_ticket_a_explicar_needs_a_request_and_one_ticket(session):
    tecnico = User(name="T", email="t@t", role="Técnico")
    assert ex_chat("¿cuál es el estado del #3?", tecnico) is None
    assert ex_chat("explicame el #3 y el #4", tecnico) is None
    assert ex_chat("explicame cómo crear un ticket", tecnico) is None
    assert ex_chat("explicame", tecnico, ticket_actual=7) is None
    assert ex_chat("explicame este", tecnico, ticket_actual=7) == 7
    assert ex_chat("explicame el #3", tecnico, ticket_actual=7) == 3


def ex_chat(pregunta, user, ticket_actual=None):
    return asistente_service.ticket_a_explicar(user, pregunta, ticket_actual)
