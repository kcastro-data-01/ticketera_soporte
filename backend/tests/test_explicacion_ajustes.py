"""Pedidos sobre la última explicación del chat («sin preguntas», «más
corto», «solo las preguntas», «más detalle»): se arman con la explicación
guardada, sin volver a llamar a la IA. Y el tono formal (usted) de los
textos de la explicación."""

import json
import re

import pytest

from backend.services import asistente_service
from backend.services import explicacion_service as ex
from backend.tests.test_explicacion import BUENA, nuevo_ticket, ollama, tecnico  # noqa: F401
from backend.tests.test_asistente import login_as


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


def test_sin_preguntas_para_no_molestar(client, session, ollama, tecnico):
    _, historia = explicado(client, session, ollama, tecnico)
    datos = conversar(client, tecnico, historia + ["sin preguntas para no molestar"])
    assert datos == {"respuesta": BUENA["explicacion"], "fuente": "directa"}
    assert "Preguntas" not in datos["respuesta"]
    assert len(ollama.pedidos) == 1, "no se vuelve a llamar a la IA"


@pytest.mark.parametrize("pedido", ["no quiero preguntas", "quitá las preguntas", "sin pregutnas"])
def test_variantes_sin_preguntas(client, session, ollama, tecnico, pedido):
    _, historia = explicado(client, session, ollama, tecnico)
    assert conversar(client, tecnico, historia + [pedido])["respuesta"] == BUENA["explicacion"]
    assert len(ollama.pedidos) == 1


@pytest.mark.parametrize("pedido", ["mas corto", "resumilo", "en una línea", "más cortp"])
def test_mas_corto_es_solo_el_resumen(client, session, ollama, tecnico, pedido):
    _, historia = explicado(client, session, ollama, tecnico)
    datos = conversar(client, tecnico, historia + [pedido])
    assert datos == {"respuesta": BUENA["resumen"], "fuente": "directa"}
    assert len(ollama.pedidos) == 1


def test_solo_las_preguntas(client, session, ollama, tecnico):
    _, historia = explicado(client, session, ollama, tecnico)
    datos = conversar(client, tecnico, historia + ["solo las preguntas"])
    assert datos["respuesta"] == ("Preguntas que puede hacerle:\n"
                                  "1. ¿Qué equipo es?\n2. ¿Desde cuándo pasa?\n3. ¿Qué error ves?")
    assert len(ollama.pedidos) == 1


@pytest.mark.parametrize("pedido", ["más detalle", "explicalo mejor"])
def test_mas_detalle_muestra_todos_los_campos(client, session, ollama, tecnico, pedido):
    _, historia = explicado(client, session, ollama, tecnico)
    texto = conversar(client, tecnico, historia + [pedido])["respuesta"]
    assert texto.startswith(BUENA["explicacion"])
    for parte in ["Resumen: " + BUENA["resumen"], "Información que falta:\n- Qué equipo falla",
                  "Siguiente paso: " + BUENA["siguiente_paso"], "Categoría sugerida: Hardware (Parece un equipo.)",
                  "Preguntas que puede hacerle:\n1. ¿Qué equipo es?"]:
        assert parte in texto
    assert len(ollama.pedidos) == 1


def test_ajustes_encadenados_usan_el_mismo_ticket(client, session, ollama, tecnico):
    _, historia = explicado(client, session, ollama, tecnico)
    corto = conversar(client, tecnico, historia + ["mas corto"])["respuesta"]
    datos = conversar(client, tecnico, historia + ["mas corto", corto, "solo las preguntas"])
    assert datos["respuesta"].startswith("Preguntas que puede hacerle:")
    assert len(ollama.pedidos) == 1


def test_ajuste_del_ticket_abierto_en_pantalla(client, session, ollama, tecnico):
    ticket = nuevo_ticket(session)
    primera = conversar(client, tecnico, ["explicame este ticket"], ticket_id=ticket.id)
    datos = conversar(client, tecnico, ["explicame este ticket", primera["respuesta"], "mas corto"],
                      ticket_id=ticket.id)
    assert datos["respuesta"] == BUENA["resumen"]
    assert len(ollama.pedidos) == 1


@pytest.mark.parametrize("mensajes", [
    ["sin preguntas para no molestar"],
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
    ("sin preguntas para no molestar", "sin_preguntas"),
    ("solo las preguntsa", "solo_preguntas"),
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
    datos = conversar(client, headers, ["sin preguntas"])
    assert datos["respuesta"] != "¿De qué ticket desea la explicación?"


# --- Tono formal ----------------------------------------------------------------

TUTEO = re.compile(r"\b(podés|puedes|tenés|tienes|querés|quieres|intentaste|probaste|copia el|envía una|"
                   r"tu|tus|eres|responde en|usa solo|inventes|adivines|di qué|ti)\b", re.I)


def test_textos_de_la_explicacion_tratan_de_usted():
    textos = [ex.INSTRUCCIONES, ex.REINTENTO, ex.MENSAJE_INVALIDA, ex.TITULO_PREGUNTAS,
              ex.SIN_PREGUNTAS_GUARDADAS, asistente_service.PIDE_TICKET_A_EXPLICAR,
              *(pregunta for _, _, pregunta in ex.DATOS_BASICOS),
              *ex.EJEMPLO_SALIDA["preguntas_sugeridas"], ex.EJEMPLO_SALIDA["explicacion"]]
    for texto in textos:
        assert not TUTEO.search(texto), texto
    assert "trate a las personas de usted" in ex.INSTRUCCIONES
    assert "Preguntas que puede hacerle:" in ex.texto_para_chat({"explicacion": BUENA})


def test_preguntas_base_del_servidor_en_usted():
    preguntas = [p for _, _, p in ex.DATOS_BASICOS]
    assert "¿Aparece algún mensaje de error? Si puede, copie el texto exacto o envíe una foto." in preguntas
    assert "¿Qué intentó ya (reiniciar, revisar cables, cerrar y abrir el programa)?" in preguntas
