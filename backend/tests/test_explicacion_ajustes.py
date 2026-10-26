"""Pedidos sobre la última explicación del chat («más corto», «más
detalle»): se arman con la explicación guardada, sin volver a llamar a la
IA. «sin preguntas» y «solo las preguntas» ya no existen (la explicación no
trae preguntas). Y el tono formal (usted) de los textos de la explicación."""

import json
import re

import pytest

from backend.services import asistente_service
from backend.services import explicacion_service as ex
from backend.tests.test_explicacion import BUENA, nuevo_ticket, ollama, tecnico  # noqa: F401
from backend.tests.test_asistente import login_as


CORTO = BUENA["explicacion"] + "\n\nPor dónde empezar: " + BUENA["que_revisar_primero"][0]


def conversar(client, headers, mensajes, ticket_id=None):
    """Envía la conversación completa (como el chat) y devuelve la respuesta."""
    cuerpo = {"messages": [{"role": "user" if i % 2 == 0 else "assistant", "content": m}
                           for i, m in enumerate(mensajes)]}
    if ticket_id is not None:
        cuerpo["ticket_id"] = ticket_id
    return client.post("/api/asistente", json=cuerpo, headers=headers).json()


def explicado(client, session, ollama, tecnico):
    """Un ticket ya explicado en el chat: (ticket, mensajes de la conversación)."""
    ticket = nuevo_ticket(session)
    primera = conversar(client, tecnico, [f"explicá el ticket #{ticket.id}"])
    assert primera["respuesta"].startswith(BUENA["explicacion"])
    assert len(ollama.pedidos) == 1
    return ticket, [f"explicá el ticket #{ticket.id}", primera["respuesta"]]


@pytest.mark.parametrize("pedido", ["mas corto", "resumilo", "en una línea", "más cortp"])
def test_mas_corto_es_la_explicacion_y_el_primer_paso(client, session, ollama, tecnico, pedido):
    _, historia = explicado(client, session, ollama, tecnico)
    datos = conversar(client, tecnico, historia + [pedido])
    assert datos == {"respuesta": CORTO, "fuente": "directa"}
    assert len(ollama.pedidos) == 1


@pytest.mark.parametrize("pedido", ["más detalle", "explicalo mejor"])
def test_mas_detalle_muestra_todos_los_campos(client, session, ollama, tecnico, pedido):
    _, historia = explicado(client, session, ollama, tecnico)
    texto = conversar(client, tecnico, historia + [pedido])["respuesta"]
    assert texto.startswith(BUENA["explicacion"])
    for parte in ["Certeza: baja", "Posibles causas:\n- El programa se actualizó",
                  "Qué revisar primero:\n1. Revisar en la consola", "4. Probar con otra cuenta",
                  "Categoría sugerida: Hardware (Parece un equipo.)", "Prioridad sugerida: Media"]:
        assert parte in texto
    assert "Pregunta" not in texto
    assert len(ollama.pedidos) == 1


def test_ajustes_encadenados_usan_el_mismo_ticket(client, session, ollama, tecnico):
    _, historia = explicado(client, session, ollama, tecnico)
    corto = conversar(client, tecnico, historia + ["mas corto"])["respuesta"]
    datos = conversar(client, tecnico, historia + ["mas corto", corto, "más detalle"])
    assert "Categoría sugerida: Hardware" in datos["respuesta"]
    assert len(ollama.pedidos) == 1


def test_ajuste_del_ticket_abierto_en_pantalla(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    primera = conversar(client, tecnico, ["explicame este ticket"], ticket_id=ticket.id)
    datos = conversar(client, tecnico, ["explicame este ticket", primera["respuesta"], "mas corto"],
                      ticket_id=ticket.id)
    assert datos["respuesta"] == CORTO
    assert len(ollama.pedidos) == 1


@pytest.mark.parametrize("mensajes", [
    ["más detalle"],
    ["hola", "¡Hola! ¿En qué le puedo ayudar?", "mas corto"],
])
def test_sin_explicacion_previa_pregunta_de_que_ticket(client, session, ollama, tecnico, mensajes):
    datos = conversar(client, tecnico, mensajes)
    assert datos == {"respuesta": "¿De qué ticket desea la explicación?", "fuente": "directa"}
    assert ollama.pedidos == []


def test_ticket_hablado_sin_explicacion_guardada_pregunta_de_que_ticket(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    datos = conversar(client, tecnico, [f"explicá el ticket #{ticket.id}", "La IA no está disponible", "mas corto"])
    assert datos["respuesta"] == "¿De qué ticket desea la explicación?"
    assert ollama.pedidos == []


@pytest.mark.parametrize("pregunta,modo", [
    ("sin preguntas para no molestar", None),
    ("solo las preguntas", None),
    ("quitá las preguntas", None),
    ("Más detalles por favor", "detalle"),
    ("resumí el #5", None),
    ("dame un resumen de los tickets criticos", None),
    ("cuantos tickets hay", None),
    ("listado completo de tickets", None),
    ("Resume la situación de mi trabajo", None),
    ("detallá los críticos", None),
    ("el resumen", "corto"),
    ("detallalo", "detalle"),
])
def test_deteccion_de_ajustes(pregunta, modo):
    assert asistente_service.ajuste_pedido(pregunta) == modo


def test_solicitante_no_usa_ajustes(client, session, ollama):
    headers = login_as(client, session, "Solicitante", "so@x.local", "Laura Méndez")
    ollama.respuestas = ["Le puedo ayudar con sus tickets."]
    datos = conversar(client, headers, ["mas corto"])
    assert datos["respuesta"] != "¿De qué ticket desea la explicación?"


# --- Tono formal ----------------------------------------------------------------

TUTEO = re.compile(r"\b(podés|puedes|tenés|tienes|querés|quieres|intentaste|probaste|copia el|envía una|"
                   r"tu|tus|eres|responde en|usa solo|inventes|adivines|di qué|ti)\b", re.I)


def test_textos_de_la_explicacion_tratan_de_usted():
    textos = [ex.INSTRUCCIONES, ex.REINTENTO, ex.MENSAJE_INVALIDA, ex.TITULO_CAUSAS, ex.TITULO_REVISAR,
              asistente_service.PIDE_TICKET_A_EXPLICAR]
    for _, salida in ex.EJEMPLOS:
        textos += [salida["explicacion"], *salida["posibles_causas"], *salida["que_revisar_primero"]]
    for texto in textos:
        assert not TUTEO.search(texto), texto
    assert "tono formal (usted)" in ex.INSTRUCCIONES
    assert "Qué revisar primero:" in ex.texto_para_chat({"explicacion": BUENA})


def test_modos_del_chat_sin_preguntas():
    assert ex.MODOS_CHAT == ("completa", "corto", "detalle")
    for modo in ex.MODOS_CHAT:
        assert "pregunta" not in ex.texto_para_chat({"explicacion": BUENA}, modo).lower()
