"""«Explicar con IA» con Ollama simulado: esquema nuevo (causas, qué revisar
primero y certeza, sin preguntas), poco texto, texto largo y confuso, JSON
inválido, Ollama caído, caché (también la de formato viejo) y permisos. El
chat ya no la genera: ver ``test_chat_ficha.py``."""

import json
import logging
import re

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
    "explicacion": ("José Solano reporta que algo no funciona, sin decir qué es. "
                    "Por la categoría parece un programa que falla al abrir o se cierra solo."),
    "posibles_causas": ["El programa se actualizó y quedó dañado", "Falta espacio en el disco",
                        "Un problema de la cuenta", "Sobra"],
    "que_revisar_primero": ["Revisar en la consola qué equipo tiene asignado José Solano",
                            "Revisar el registro de errores del equipo", "Reinstalar el programa",
                            "Probar con otra cuenta", "Sobra"],
    "certeza": "media",
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
        return self.pedidos[-1]["messages"][-1]["content"]


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
    assert len(e["posibles_causas"]) == 3  # máximo 3 aunque la IA mande 4
    assert len(e["que_revisar_primero"]) == 4  # máximo 4 aunque la IA mande 5
    # Poco texto: certeza baja aunque la IA diga «media», y los pasos igual.
    assert e["certeza"] == "baja"
    assert e["que_revisar_primero"][0].startswith("Revisar en la consola")
    assert e["categoria_sugerida"] == {"valor": "Hardware", "razon": "Parece un equipo."}
    for viejo in ("preguntas_sugeridas", "informacion_faltante", "resumen", "siguiente_paso", "puntos_clave"):
        assert viejo not in e

    pedido = ollama.pedidos[0]
    assert pedido["think"] is False
    assert pedido["options"]["temperature"] == 0.1
    assert pedido["options"]["num_ctx"] == ex.EXPLICACION_NUM_CTX == 2048
    assert pedido["format"]["required"] == ["explicacion", "posibles_causas", "que_revisar_primero", "certeza"]
    # Un solo ejemplo completo (entrada y salida) antes del ticket real.
    roles = [m["role"] for m in pedido["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert len(ex.EJEMPLOS) == 1
    assert json.loads(pedido["messages"][2]["content"]) == ex.EJEMPLOS[0][1]
    assert "NO puede preguntarle nada a la persona" in pedido["messages"][0]["content"]
    texto = ollama.ultimo_ticket()
    assert "Título: No sirve" in texto and "no sirve" in texto
    assert "Datos que el sistema no encontró en el texto: Qué equipo" in texto
    assert "Reporta: no se sabe" in texto


def test_prompt_has_the_example_and_who_reports(client, session, ollama, tecnico):
    autor = session.scalar(select(User).where(User.email == "tec@tec.local"))
    ticket = nuevo_ticket(session, created_by_id=autor.id)
    client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    mensajes = ollama.pedidos[0]["messages"]
    assert "explicacion: de 2 a 4 oraciones" in mensajes[0]["content"]
    assert "Título: Impresora\nReporta: Laura Méndez\nCategoría actual: Hardware" in mensajes[1]["content"]
    assert "Descripción:\nno sirve" in mensajes[1]["content"]
    assert json.loads(mensajes[2]["content"])["certeza"] == "baja"
    assert len(mensajes) == 4
    assert "Reporta: José Solano" in ollama.ultimo_ticket()


def test_schema_and_prompt_have_no_questions():
    propiedades = ex.ESQUEMA_IA["properties"]
    assert "preguntas_sugeridas" not in propiedades and "informacion_faltante" not in propiedades
    assert propiedades["certeza"]["enum"] == ["alta", "media", "baja"]
    assert propiedades["posibles_causas"]["maxItems"] == 3
    assert propiedades["que_revisar_primero"]["maxItems"] == 4
    assert "preguntas_sugeridas" not in ex.INSTRUCCIONES
    assert "informacion_faltante" not in ex.INSTRUCCIONES
    assert "el usuario dijo que" in ex.INSTRUCCIONES  # se le prohíbe
    for _, salida in ex.EJEMPLOS:
        # Los ejemplos pasan la misma validación que la respuesta real.
        validada = ex.validar_respuesta(json.dumps(salida, ensure_ascii=False))
        assert validada["posibles_causas"] == salida["posibles_causas"]
        assert validada["que_revisar_primero"] == salida["que_revisar_primero"]
        assert "?" not in json.dumps(salida, ensure_ascii=False)


def test_steps_that_ask_the_person_are_dropped():
    respuesta = {**BUENA, "que_revisar_primero": [
        "Preguntarle a la persona qué equipo es", "¿Desde cuándo pasa?",
        "Pedirle al usuario una foto del error", "Revisar el registro de errores del equipo"]}
    validada = ex.validar_respuesta(json.dumps(respuesta, ensure_ascii=False))
    assert validada["que_revisar_primero"] == ["Revisar el registro de errores del equipo"]


def test_only_questions_counts_as_invalid(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    solo_preguntas = {**BUENA, "que_revisar_primero": ["¿Qué equipo es?", "Preguntar desde cuándo pasa"]}
    ollama.respuestas = [json.dumps(solo_preguntas, ensure_ascii=False), json.dumps(BUENA)]
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    assert len(ollama.pedidos) == 2


@pytest.mark.parametrize("valor,claridad,esperada", [
    ("alta", "clara", "alta"),
    ("Media", "confusa", "media"),
    ("BAJA", "clara", "baja"),
    ("segura", "clara", "media"),  # inválida: se usa «media»
    (None, "clara", "media"),
    ("alta", "poco detalle", "baja"),  # poco texto: siempre baja
])
def test_certeza_is_normalized(valor, claridad, esperada):
    respuesta = {**BUENA, "certeza": valor}
    validada = ex.validar_respuesta(json.dumps(respuesta), {"claridad": claridad})
    assert validada["certeza"] == esperada


def test_long_explanation_is_cut_to_four_sentences():
    larga = " ".join(f"Esta es la oración número {i} de la explicación." for i in range(1, 7))
    validada = ex.validar_respuesta(json.dumps({**BUENA, "explicacion": larga}, ensure_ascii=False))
    assert validada["explicacion"].endswith("número 4 de la explicación.")


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
    ollama.respuestas = [json.dumps({**BUENA, "posibles_causas": [
        "La impresora HP 4020 tiene una falla en el fusor (error 49).",
        "El firmware de la impresora está desactualizado.",
    ], "certeza": "alta"}, ensure_ascii=False)]

    datos = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico).json()
    assert datos["claridad"] == "confusa"
    assert datos["explicacion"]["posibles_causas"][0].startswith("La impresora HP 4020")
    assert datos["explicacion"]["certeza"] == "alta"

    texto = ollama.ultimo_ticket()
    assert ex.OMITIDO in texto
    assert "desde el lunes la impresora HP 4020" in texto  # primer párrafo
    assert "contratos del viernes" in texto  # último párrafo
    assert "Comentario 5" in texto and "Comentario 2" not in texto  # últimos 3
    # Todo el pedido entra en num_ctx con lugar para la respuesta.
    total = sum(len(m["content"]) for m in ollama.pedidos[0]["messages"])
    assert total < ex.EXPLICACION_NUM_CTX * 2.7


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
    sin_paso = {k: v for k, v in BUENA.items() if k != "que_revisar_primero"}
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
    assert e["explicacion"] == BUENA["explicacion"]
    assert len(ollama.pedidos) == 1  # no hizo falta reintentar


def test_json_inside_code_fence_is_accepted():
    texto = "```json\n" + json.dumps(BUENA) + "\n```"
    assert ex.validar_respuesta(texto)["explicacion"] == BUENA["explicacion"]


@pytest.mark.parametrize("error, motivo", [
    (httpx.ConnectError("refused"), "No se pudo conectar con el servicio de IA (Ollama)"),
    (httpx.ReadTimeout("lento"), "Tardó demasiado en responder"),
])
def test_ollama_down_shows_the_reason(client, session, ollama, tecnico, error, motivo, caplog, monkeypatch):
    monkeypatch.setattr(asistente_service.logger, "propagate", True)
    ollama.error = error
    ticket = nuevo_ticket(session)
    with caplog.at_level(logging.ERROR, logger=asistente_service.logger.name):
        resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 502
    detalle = resp.json()["detail"]
    assert detalle.startswith("La IA no está disponible en este momento. ")
    assert motivo in detalle
    assert f"explicar ticket #{ticket.id}: error con qwen3:0.6b" in caplog.text


@pytest.mark.parametrize("error, motivo", [
    (asistente_service.AsistenteNoDisponible(
        "El modelo qwen3:0.6b todavía no está descargado en Ollama; espera a que termine"),
     "El modelo de IA todavía se está descargando"),
    (asistente_service.AsistenteNoDisponible("No hay memoria suficiente para el modelo qwen3:4b"),
     "No hay memoria suficiente para el modelo de IA."),
    (asistente_service.AsistenteNoConfigurado("falta la clave"), "Falta configurarla"),
])
def test_reason_in_plain_words(error, motivo):
    texto = ex.motivo_para_usuario(error)
    assert texto.startswith("La IA no está disponible en este momento. ")
    assert motivo in texto


def test_usage_limit_has_its_own_message():
    texto = ex.motivo_para_usuario(asistente_service.AsistenteOcupado("429"))
    assert texto == "La IA está ocupada, intente de nuevo en un minuto"


def test_unknown_error_keeps_the_general_message():
    error = asistente_service.AsistenteNoDisponible("Ollama respondió con un error (500)")
    assert ex.motivo_para_usuario(error) == "La IA no está disponible en este momento"


# --- Caché ------------------------------------------------------------------------


def test_saved_explanation_is_reused_until_the_ticket_changes(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    url = f"/api/tickets/{ticket.id}/explicacion"

    assert client.get(url, headers=tecnico).json()["explicacion"] is None
    client.post(url, headers=tecnico)
    assert len(ollama.pedidos) == 1

    # Abrir el ticket otra vez: se usa la guardada, sin llamar a la IA.
    guardada = client.get(url, headers=tecnico).json()
    assert guardada["vigente"] is True and guardada["explicacion"]["que_revisar_primero"]
    assert client.post(url, headers=tecnico).json()["desde_cache"] is True
    assert len(ollama.pedidos) == 1

    # El ticket cambia (nuevo comentario): queda desactualizada y se regenera.
    client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Es la impresora HP"}, headers=tecnico)
    assert client.get(url, headers=tecnico).json()["vigente"] is False
    nueva = client.post(url, headers=tecnico).json()
    assert nueva["vigente"] is True and nueva["desde_cache"] is False
    assert len(ollama.pedidos) == 2
    assert "Es la impresora HP" in ollama.ultimo_ticket()


VIEJA = {
    "explicacion": "En este ticket, José Solano dice que algo no sirve. Falta saber qué equipo falla.",
    "resumen": "Algo no funciona.",
    "informacion_faltante": ["Qué equipo falla"],
    "preguntas_sugeridas": ["¿Qué equipo es?"],
    "puntos_clave": [],
    "siguiente_paso": "Preguntar qué equipo falla.",
}


def test_saved_explanation_with_old_format_is_generated_again(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    url = f"/api/tickets/{ticket.id}/explicacion"
    client.post(url, headers=tecnico)
    guardada = session.scalar(select(TicketExplanation))
    guardada.content = json.dumps(VIEJA, ensure_ascii=False)  # como las guardadas antes del cambio
    session.commit()

    # Al abrir el ticket no se muestra (se pide de nuevo con el botón).
    assert client.get(url, headers=tecnico).json()["explicacion"] is None
    nueva = client.post(url, headers=tecnico).json()
    assert nueva["desde_cache"] is False
    assert nueva["explicacion"]["que_revisar_primero"]
    assert "preguntas_sugeridas" not in nueva["explicacion"]
    assert len(ollama.pedidos) == 2
    session.expire_all()
    assert json.loads(session.scalar(select(TicketExplanation)).content)["version"] == ex.VERSION_EXPLICACION


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


# --- Tono formal ----------------------------------------------------------------

TUTEO = re.compile(r"\b(podés|puedes|tenés|tienes|querés|quieres|intentaste|probaste|copia el|envía una|"
                   r"tu|tus|eres|responde en|usa solo|inventes|adivines|di qué|ti)\b", re.I)


def test_textos_de_la_explicacion_tratan_de_usted():
    textos = [ex.INSTRUCCIONES, ex.REINTENTO, ex.MENSAJE_INVALIDA]
    for _, salida in ex.EJEMPLOS:
        textos += [salida["explicacion"], *salida["posibles_causas"], *salida["que_revisar_primero"]]
    for texto in textos:
        assert not TUTEO.search(texto), texto
    assert "tono formal (usted)" in ex.INSTRUCCIONES
