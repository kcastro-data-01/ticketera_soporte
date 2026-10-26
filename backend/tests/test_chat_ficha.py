"""«explicame el ticket #N» en el chat: responde el servidor, sin IA, con la
ficha del ticket (número, título, estado, prioridad, categoría, quién
reporta, a quién está asignado, cuándo se creó y un extracto de la
descripción) y al final adónde ir para saber más según el permiso
``explicar_ia``. El botón «Explicar con IA» del detalle no cambia."""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import Ticket, TicketExplanation, User
from backend.services import asistente_service as a
from backend.tests.test_asistente import login_as
from backend.tests.test_explicacion import ollama, tecnico  # noqa: F401
from backend.tests.textos_asistente import es_forma, negrita

LINEA_IA = ("Si necesita más información, como las posibles causas y qué revisar primero, "
            "[abra el ticket y use «Explicar con IA»](detalle.html?id={id}&pestana=ia).")
LINEA_DETALLE = "Puede ver el [detalle completo en el ticket](detalle.html?id={id})."
LARGA = ("La impresora del segundo piso no imprime desde ayer en la tarde y marca una luz naranja. "
         "Ya la apagamos y la volvimos a encender, también revisamos el papel y el tóner, pero sigue "
         "igual y hoy tenemos que imprimir los contratos del cliente para la reunión de las tres.")


@pytest.fixture
def solicitante(client, session):
    return login_as(client, session, "Solicitante", "so@x.local", "Laura Méndez")


def usuario(session, correo):
    return session.scalar(select(User).where(User.email == correo))


def ticket_de(session, creador, asignado=None, descripcion=LARGA):
    ticket = Ticket(title="Impresora no imprime", description=descripcion, category="Hardware",
                    priority="Alta", state="En proceso", created_by_id=creador.id,
                    assigned_to_id=asignado.id if asignado else None,
                    created_at=datetime(2026, 10, 20, 15, 5, tzinfo=timezone.utc))
    session.add(ticket)
    session.commit()
    return ticket


def preguntar(client, headers, texto, ticket_id=None, stream=False):
    cuerpo = {"messages": [{"role": "user", "content": texto}]}
    if ticket_id is not None:
        cuerpo["ticket_id"] = ticket_id
    if stream:
        resp = client.post("/api/asistente/stream", json=cuerpo, headers=headers)
        return [json.loads(linea) for linea in resp.text.splitlines() if linea.strip()]
    resp = client.post("/api/asistente", json=cuerpo, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def ficha_esperada(ticket, reporta, asignado, cierre):
    return [
        "- Estado: En proceso",
        "- Prioridad: Alta",
        "- Categoría: Hardware",
        f"- Reporta: {reporta}",
        f"- Asignado a: {asignado}",
        "- Creado: 20 de octubre de 2026, 9:05 a. m.",  # hora de Costa Rica
        f"- Descripción: {LARGA[:199]}…",
        "",
        cierre.format(id=ticket.id),
    ]


# --- Técnico (con «Explicar con IA») -------------------------------------------


def test_tecnico_gets_the_card_and_the_ai_line(client, session, ollama, tecnico, solicitante):
    jose, laura = usuario(session, "tec@tec.local"), usuario(session, "so@x.local")
    ticket = ticket_de(session, laura, asignado=jose)
    datos = preguntar(client, tecnico, f"explicame el ticket #{ticket.id}")
    assert datos["fuente"] == "directa"
    primera, *resto = datos["respuesta"].split("\n")
    assert es_forma(primera, "ficha_ticket", id=negrita(f"#{ticket.id}"), titulo="Impresora no imprime"), primera
    assert resto == ficha_esperada(ticket, "Laura Méndez (Solicitante)", "José Solano (Técnico)", LINEA_IA)
    assert ollama.pedidos == [], "no se llama a Ollama"
    assert session.scalar(select(TicketExplanation)) is None, "no se genera ni se guarda una explicación"


def test_explique_el_ticket_1_exactly(client, session, ollama, tecnico):
    """El caso que se probó en la app: «explique» (usted) no se reconocía."""
    ticket = ticket_de(session, usuario(session, "tec@tec.local"))
    assert ticket.id == 1
    datos = preguntar(client, tecnico, "Explique el ticket #1")
    assert datos["fuente"] == "directa"
    assert datos["respuesta"].split("\n")[-1] == LINEA_IA.format(id=1)
    assert "- Estado: En proceso" in datos["respuesta"]
    assert ollama.pedidos == []
    eventos = preguntar(client, tecnico, "Explique el ticket #1", stream=True)
    assert eventos[0]["t"].split("\n")[-1] == LINEA_IA.format(id=1)
    assert ollama.pedidos == []


@pytest.mark.parametrize("pregunta", [
    # usted, tú y vos; con y sin tilde; con y sin «#»
    "Explique el ticket #{id}",
    "explique el ticket {id}",
    "Explíqueme el ticket #{id}",
    "¿Me puede explicar el ticket #{id}?",
    "explícame el ticket #{id}",
    "explica el ticket {id}",
    "explicá el ticket {id}",
    "podés explicarme el ticket {id}?",
    "explique el {id}",
    # errores de escritura
    "explcame el tiket {id}",
    "expilcame el ticket {id}",
    "esplicame el tikete {id}",
    "q pasa con el tiket {id}",
    "d q trata el tiket {id}",
    "resumime el tiket {id}",
    "explicame el tiket {id}",
    "Explicá el tikete #{id}",
    "qué pasa con el tiket {id}",
    "que le pasa al ticket {id}?",
    "de qué trata el ticket {id}?",
    "qué quiere la persona del #{id}",
    "no entiendo el ticket #{id}",
    "resumí el ticket {id}",
])
def test_requests_with_typos_get_the_card_without_ollama(client, session, ollama, tecnico, pregunta):
    ticket = ticket_de(session, usuario(session, "tec@tec.local"))
    datos = preguntar(client, tecnico, pregunta.format(id=ticket.id))
    assert datos["fuente"] == "directa"
    assert "- Asignado a: sin asignar" in datos["respuesta"]
    assert datos["respuesta"].endswith(LINEA_IA.format(id=ticket.id))
    assert ollama.pedidos == []


def test_este_ticket_on_screen_and_streaming(client, session, ollama, tecnico):
    ticket = ticket_de(session, usuario(session, "tec@tec.local"))
    eventos = preguntar(client, tecnico, "explicame este ticket", ticket_id=ticket.id, stream=True)
    assert eventos[0]["t"].endswith(LINEA_IA.format(id=ticket.id))
    assert eventos[-1] == {"fin": True, "fuente": "directa"}
    assert ollama.pedidos == []


@pytest.mark.parametrize("rol", ["Supervisor", "Administrador"])
def test_other_team_roles_also_get_the_ai_line(client, session, ollama, rol):
    headers = login_as(client, session, rol, "eq@x.local", "Persona Equipo")
    ticket = ticket_de(session, usuario(session, "eq@x.local"))
    respuesta = preguntar(client, headers, f"explicame el ticket #{ticket.id}")["respuesta"]
    assert respuesta.endswith(LINEA_IA.format(id=ticket.id))


def test_short_description_is_shown_whole(client, session, ollama, tecnico):
    ticket = ticket_de(session, usuario(session, "tec@tec.local"), descripcion="no sirve")
    respuesta = preguntar(client, tecnico, f"explicame el ticket #{ticket.id}")["respuesta"]
    assert "- Descripción: no sirve\n" in respuesta


# --- Solicitante (sin «Explicar con IA») ---------------------------------------


def test_solicitante_gets_the_card_and_the_detail_line(client, session, ollama, solicitante):
    laura = usuario(session, "so@x.local")
    ticket = ticket_de(session, laura)
    datos = preguntar(client, solicitante, f"explicame mi ticket #{ticket.id}")
    assert datos["fuente"] == "directa"
    resto = datos["respuesta"].split("\n")[1:]
    assert resto == ficha_esperada(ticket, "Laura Méndez (Solicitante)", "sin asignar", LINEA_DETALLE)
    assert "Explicar con IA" not in datos["respuesta"]
    assert "pestana=ia" not in datos["respuesta"]
    assert ollama.pedidos == []


def test_solicitante_cannot_see_someone_elses_ticket(client, session, ollama, solicitante, tecnico):
    ajeno = ticket_de(session, usuario(session, "tec@tec.local"))
    datos = preguntar(client, solicitante, f"explicame el ticket #{ajeno.id}")
    assert datos["fuente"] == "directa"
    assert es_forma(datos["respuesta"], "ticket_no_encontrado", id=f"#{ajeno.id}"), datos
    assert "Impresora no imprime" not in datos["respuesta"]
    assert ollama.pedidos == []


# --- Ticket inexistente ---------------------------------------------------------


@pytest.mark.parametrize("pregunta", ["explicar ticket #999", "qué pasa con el tiket 999"])
def test_missing_ticket_is_the_same_answer_as_before(client, session, ollama, tecnico, pregunta):
    datos = preguntar(client, tecnico, pregunta)
    assert datos["fuente"] == "directa"
    assert es_forma(datos["respuesta"], "ticket_no_encontrado", id="#999"), datos
    assert ollama.pedidos == []


# --- Lo que ya no existe y lo que no cambia ---------------------------------------


@pytest.mark.parametrize("pedido", ["mas corto", "más detalle"])
def test_old_adjustments_are_gone(client, session, ollama, tecnico, pedido):
    ticket = ticket_de(session, usuario(session, "tec@tec.local"))
    primera = preguntar(client, tecnico, f"explicame el ticket #{ticket.id}")["respuesta"]
    ollama.respuestas = ["¿Sobre qué desea más información?"]
    cuerpo = {"messages": [{"role": "user", "content": f"explicame el ticket #{ticket.id}"},
                           {"role": "assistant", "content": primera},
                           {"role": "user", "content": pedido}]}
    datos = client.post("/api/asistente", json=cuerpo, headers=tecnico).json()
    assert datos["respuesta"] != "¿De qué ticket desea la explicación?"
    for nombre in ("ajuste_pedido", "ajustar_ultima_explicacion", "PIDE_TICKET_A_EXPLICAR"):
        assert not hasattr(a, nombre)


def test_the_button_still_generates_the_explanation(client, session, ollama, tecnico):
    ticket = ticket_de(session, usuario(session, "tec@tec.local"))
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=tecnico)
    assert resp.status_code == 200
    assert resp.json()["explicacion"]["que_revisar_primero"]
    assert len(ollama.pedidos) == 1


def test_ticket_a_explicar_needs_a_request_and_one_ticket():
    tecnico = User(name="T", email="t@t", role="Técnico")
    solicitante = User(name="S", email="s@s", role="Solicitante")
    assert a.ticket_a_explicar(tecnico, "¿cuál es el estado del #3?") is None
    assert a.ticket_a_explicar(tecnico, "explicame el #3 y el #4") is None
    assert a.ticket_a_explicar(tecnico, "explicame cómo crear un ticket") is None
    assert a.ticket_a_explicar(tecnico, "explicame", ticket_actual=7) is None
    assert a.ticket_a_explicar(tecnico, "explicame este", ticket_actual=7) == 7
    assert a.ticket_a_explicar(tecnico, "explicame el #3", ticket_actual=7) == 3
    assert a.ticket_a_explicar(tecnico, "que pasa con el tiket 5") == 5
    # Ahora también para el Solicitante (recibe la ficha, sin la línea de IA).
    assert a.ticket_a_explicar(solicitante, "explicame el #3") == 3


# --- La línea final también cuando responde la IA libre ---------------------------


def test_free_ai_answer_about_one_ticket_ends_with_the_line(client, session, ollama, tecnico, solicitante):
    """Si un pedido sobre un ticket igual llega a la IA libre («¿cómo resuelvo
    el #N?»), el servidor agrega la misma línea final."""
    laura = usuario(session, "so@x.local")
    ticket = ticket_de(session, laura)
    ollama.respuestas = ["La descripción explica que la impresora no imprime. Revise el tóner."]
    datos = preguntar(client, tecnico, f"¿Cómo resuelvo el ticket #{ticket.id}?")
    assert datos["fuente"] == "ia"
    assert datos["respuesta"] == ("La descripción explica que la impresora no imprime. Revise el tóner."
                                  "\n\n" + LINEA_IA.format(id=ticket.id))
    datos = preguntar(client, solicitante, f"¿Cómo se soluciona mi ticket #{ticket.id}?")
    assert datos["respuesta"].endswith("\n\n" + LINEA_DETALLE.format(id=ticket.id))


def test_free_ai_streaming_also_ends_with_the_line(session, tecnico):
    class Proveedor:
        modelo = "falso"

        def responder_stream(self, system, messages):
            yield "Revise el tóner "
            yield "y el papel."

    jose = usuario(session, "tec@tec.local")
    ticket = ticket_de(session, jose)
    mensajes = [{"role": "user", "content": f"¿Cómo resuelvo el ticket #{ticket.id}?"}]
    eventos = list(a.responder_stream(Proveedor(), session, jose, mensajes))
    assert "".join(e.get("t", "") for e in eventos) == "Revise el tóner y el papel.\n\n" + LINEA_IA.format(id=ticket.id)
    assert eventos[-1] == {"fin": True, "fuente": "ia"}


def test_free_ai_answer_without_a_ticket_has_no_line(client, session, ollama, tecnico):
    ollama.respuestas = ["Puede crear un ticket desde «Nuevo ticket»."]
    datos = preguntar(client, tecnico, "¿Cómo creo un ticket?")
    assert "Explicar con IA" not in datos["respuesta"]
