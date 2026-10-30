"""Ciclos de correos (incidente de producción: tickets repetidos sin parar).

Con Graph simulado, en modo cron (Vercel) y en modo hilo (Docker):

* Todo correo que manda la app queda registrado como ``aviso_app`` **antes**
  de enviarse; su copia en Elementos enviados (con o sin la cabecera
  ``X-Ticketera``) nunca vuelve a procesarse.
* Se reconoce por el asunto y por las frases fijas aunque Graph pierda la
  cabecera o le cambie el Message-ID.
* Responder a un aviso o a una confirmación es un comentario, nunca un ticket.
* Una conversación ya procesada nunca crea un ticket nuevo.
* Lo que envía la dueña del buzón solo crea tickets con «Ticket:».
* Freno: como máximo 5 tickets por revisión, con una alerta en el log.
"""

import logging

import pytest
from sqlalchemy import select

from backend.models import Comment, ProcessedEmail, Ticket
from backend.services import correo_service as cs
from backend.tests.test_correo import FakeGraph, crear_correo, factory  # noqa: F401
from backend.tests.test_correo_enviados import crear_enviado
from backend.tests.test_correo_reglas import MODOS, YO, agregar, entorno, gente, revisar  # noqa: F401

CONFIG = cs.ConfigCorreo(usuario=YO, app_url="https://tickets-americandata.vercel.app",
                         dominio_empresa="data.cr", filtro="auto", avisar_asignado=True)


def tickets(session):
    session.expire_all()
    return session.scalars(select(Ticket).order_by(Ticket.id)).all()


def comentarios(session, ticket_id):
    session.expire_all()
    return session.scalars(select(Comment.content).where(Comment.ticket_id == ticket_id)).all()


def registro(session, message_id):
    session.expire_all()
    return session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == message_id))


def pedido_de_ana(msg_id="<pedido@data.cr>", conversacion="conv-pedido", **extra):
    return dict(crear_correo(msg_id=msg_id, **extra), conversationId=conversacion)


# --- Todo lo que manda la app queda registrado antes de enviarse -------------


@pytest.mark.parametrize("modo", MODOS)
def test_confirmation_is_registered_as_app_notice_before_sending(modo, entorno, factory, session, gente):
    graph = FakeGraph([pedido_de_ana()], copiar_a_enviados=True)
    revisar(modo, factory, graph, entorno)

    [ticket] = tickets(session)
    aviso = registro(session, "<app-1@data.cr>")
    assert (aviso.result, aviso.ticket_id, aviso.conversation_id) == ("aviso_app", ticket.id, "conv-pedido")
    # createReply (se conoce el Message-ID) → registro → send.
    rutas = [r for _, r in graph.llamadas]
    assert rutas.index("/me/messages/borrador-1/send") > [i for i, r in enumerate(rutas)
                                                           if r.endswith("/createReply")][0]


def test_a_notice_that_could_not_be_registered_is_not_sent():
    graph = FakeGraph([crear_correo()])
    respuesta = cs.Respuesta(para="ana@data.cr", asunto="Ticket #1 creado: x", texto="…")

    def falla(borrador):
        raise RuntimeError("la base no respondió")

    mensaje_id = next(iter(graph.mensajes))
    with pytest.raises(RuntimeError):
        graph.cliente.responder(mensaje_id, respuesta, registrar=falla)
    assert graph.respuestas == []  # no se envió
    assert ("DELETE", "/me/messages/borrador-1") in graph.llamadas  # ni quedó el borrador


# --- El ciclo del incidente --------------------------------------------------


@pytest.mark.parametrize("perder_cabeceras", [False, True])
@pytest.mark.parametrize("modo", MODOS)
def test_app_notices_in_sent_items_never_create_tickets(modo, perder_cabeceras, entorno, factory,
                                                       session, gente):
    """La dueña envía «Ticket: …» a Pedro → ticket y aviso «Se le asignó…»;
    la copia del aviso queda en Enviados (con o sin cabecera). Varias
    revisiones después sigue habiendo un solo ticket."""
    graph = FakeGraph([], enviados=[crear_enviado()], copiar_a_enviados=True,
                      perder_cabeceras=perder_cabeceras)
    for _ in range(4):
        revisar(modo, factory, graph, entorno)

    assert len(tickets(session)) == 1
    assert len(graph.correos_nuevos) == 1  # un solo aviso a Pedro
    copia = next(m for m in graph.mensajes.values() if m["id"].startswith("enviado-"))
    assert registro(session, copia["internetMessageId"]).result == "aviso_app"


@pytest.mark.parametrize("asunto,cuerpo", [
    # Graph le cambió el Message-ID y perdió la cabecera: el asunto lo delata.
    ("[Ticket #1] Se le asignó el ticket #1: La impresora no imprime", "Hola Pedro"),
    ("Ticket #1 creado: La impresora no imprime", "Hola Ana"),
    # Asunto cambiado: las frases fijas lo delatan.
    ("Aviso", "Hola Pedro,\n\nSe le asignó el ticket #1, creado a partir del correo de Kristin."),
    ("Aviso", "Hola Ana,\n\nRecibimos tu solicitud y creamos el ticket #1."),
    ("Aviso", "Juan agregó un comentario en el ticket #1 (Impresora):\n\nYa la revisé."),
    ("Aviso", "Para crear tickets por correo, primero ingrese a la ticketera con su cuenta"),
])
def test_app_notice_without_header_or_registration_is_recognized_in_sent_items(session, gente, asunto,
                                                                              cuerpo):
    copia = cs.correo_desde_graph(crear_enviado(asunto=asunto, cuerpo=cuerpo, msg_id="<otro-id@data.cr>"))
    assert cs.procesar_enviado(session, copia, CONFIG) == ("ignorado", None)
    assert tickets(session) == []


@pytest.mark.parametrize("cabeceras,cuerpo", [
    ({"X-Ticketera": "1"}, "La impresora no imprime desde ayer, no funciona."),
    ({}, "Hola Kristin,\n\nRecibimos tu solicitud y creamos el ticket #8. La impresora no funciona."),
])
def test_notice_from_another_ticketera_in_the_inbox_never_creates_a_ticket(session, gente, cabeceras, cuerpo):
    """Un aviso de una ticketera (esta u otra) que llega de otra persona, sin
    hilo de un ticket: nunca crea un ticket aunque pase el filtro."""
    correo = cs.correo_desde_graph(dict(crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas",
                                                     asunto="La impresora no funciona", cuerpo=cuerpo,
                                                     cabeceras=cabeceras), conversationId="conv-x"))
    assert cs.procesar_correo(session, correo, CONFIG) == ("ignorado", None)
    assert tickets(session) == []


# --- Responder a un aviso o a una confirmación → comentario -----------------


@pytest.mark.parametrize("modo", MODOS)
def test_reply_to_the_confirmation_is_a_comment(modo, entorno, factory, session, gente):
    graph = FakeGraph([pedido_de_ana()], copiar_a_enviados=True)
    revisar(modo, factory, graph, entorno)
    [ticket] = tickets(session)

    respuesta = pedido_de_ana(msg_id="<re1@data.cr>", asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                              cuerpo="Ya la reinicié y sigue sin funcionar.",
                              cabeceras={"In-Reply-To": "<app-1@data.cr>"})
    agregar(graph, respuesta)
    revisar(modo, factory, graph, entorno)

    assert len(tickets(session)) == 1
    assert comentarios(session, ticket.id) == ["Ya la reinicié y sigue sin funcionar."]


@pytest.mark.parametrize("estado", ["Resuelto", "Cerrado"])
def test_reply_on_a_resolved_or_closed_ticket_is_a_comment_and_keeps_the_state(estado, entorno,
                                                                              factory, session, gente):
    """Responder por correo no reabre el ticket (no hay reapertura automática):
    solo agrega el comentario; reabrir es pasarlo a «En proceso» a mano."""
    graph = FakeGraph([pedido_de_ana()], copiar_a_enviados=True)
    revisar(MODOS[0], factory, graph, entorno)
    [ticket] = tickets(session)
    ticket.state = estado
    session.commit()

    agregar(graph, pedido_de_ana(msg_id="<re-cerrado@data.cr>",
                                 asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                                 cuerpo="Volvió a fallar esta mañana.",
                                 cabeceras={"In-Reply-To": "<app-1@data.cr>"}))
    revisar(MODOS[0], factory, graph, entorno)

    [ticket] = tickets(session)
    assert ticket.state == estado
    assert comentarios(session, ticket.id) == ["Volvió a fallar esta mañana."]


@pytest.mark.parametrize("modo", MODOS)
def test_reply_to_the_confirmation_with_another_subject_is_still_a_comment(modo, entorno, factory,
                                                                          session, gente):
    """Sin número en el asunto ni cabeceras: la conversación del aviso
    registrado basta para encontrar el ticket."""
    graph = FakeGraph([pedido_de_ana()], copiar_a_enviados=True)
    revisar(modo, factory, graph, entorno)
    [ticket] = tickets(session)

    agregar(graph, pedido_de_ana(msg_id="<re2@data.cr>", asunto="Otra cosa: no funciona la impresora",
                                 cuerpo="No funciona todavía."))
    revisar(modo, factory, graph, entorno)

    assert len(tickets(session)) == 1
    assert comentarios(session, ticket.id) == ["No funciona todavía."]


@pytest.mark.parametrize("modo", MODOS)
def test_reply_to_the_assignment_notice_is_a_comment(modo, entorno, factory, session, gente):
    graph = FakeGraph([], enviados=[crear_enviado()], copiar_a_enviados=True, perder_cabeceras=True)
    revisar(modo, factory, graph, entorno)
    [ticket] = tickets(session)
    conversacion_aviso = registro(session, "<app-1@data.cr>").conversation_id

    agregar(graph, dict(crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas", msg_id="<re3@data.cr>",
                                     asunto="RE: Aviso", cuerpo="La reviso hoy, no funciona el tóner."),
                        conversationId=conversacion_aviso))
    for _ in range(2):
        revisar(modo, factory, graph, entorno)

    assert len(tickets(session)) == 1
    assert comentarios(session, ticket.id) == ["La reviso hoy, no funciona el tóner."]


# --- Una conversación ya procesada nunca crea un ticket nuevo ----------------


def test_same_conversation_never_creates_a_second_ticket(session, gente):
    primero = cs.correo_desde_graph(pedido_de_ana())
    assert cs.procesar_correo(session, primero, CONFIG)[0] == "ticket"

    # Otro correo de Juan (que no participa) en la misma conversación.
    segundo = cs.correo_desde_graph(dict(crear_correo(remitente="juan@data.cr", nombre="Juan Solís",
                                                      msg_id="<otro@data.cr>",
                                                      asunto="[Ticket #99] No funciona el monitor",
                                                      cuerpo="Tampoco funciona el monitor."),
                                         conversationId="conv-pedido"))
    # Juan está en el hilo: comenta. Lo importante: no hay ticket nuevo.
    assert cs.procesar_correo(session, segundo, CONFIG)[0] in ("comentario", "ignorado")
    assert len(tickets(session)) == 1


def test_conversation_of_a_deleted_ticket_does_not_create_a_new_one(session, gente):
    """Lo que pasó en producción: se borraron los tickets repetidos y sus
    registros quedaron sin ticket. Un correo más de esa conversación no
    vuelve a crear uno."""
    assert cs.procesar_correo(session, cs.correo_desde_graph(pedido_de_ana()), CONFIG)[0] == "ticket"
    for ticket in tickets(session):
        session.delete(ticket)
    session.commit()

    otra_vez = cs.correo_desde_graph(pedido_de_ana(msg_id="<otra-vez@data.cr>",
                                                   asunto="La impresora sigue sin funcionar"))
    assert cs.procesar_correo(session, otra_vez, CONFIG) == ("ignorado", None)
    assert tickets(session) == []


def test_sent_mail_in_a_known_conversation_does_not_create_a_ticket(session, gente):
    assert cs.procesar_correo(session, cs.correo_desde_graph(pedido_de_ana()), CONFIG)[0] == "ticket"
    for ticket in tickets(session):
        session.delete(ticket)
    session.commit()
    enviado = cs.correo_desde_graph(crear_enviado(asunto="Ticket: La impresora", conversacion="conv-pedido"))
    assert cs.procesar_enviado(session, enviado, CONFIG) == ("ignorado", None)
    assert tickets(session) == []


# --- Lo que envía la dueña: solo con «Ticket:» --------------------------------


@pytest.mark.parametrize("asunto,crea", [
    ("Ticket: La impresora no imprime", True),
    ("La impresora no imprime, no funciona", False),
    ("Urgente: no funciona la red", False),
])
def test_sent_mail_creates_a_ticket_only_with_the_prefix(session, gente, asunto, crea):
    resultado, _ = cs.procesar_enviado(session, cs.correo_desde_graph(crear_enviado(asunto=asunto)), CONFIG)
    assert resultado == ("ticket" if crea else "otro")
    assert len(tickets(session)) == (1 if crea else 0)


def test_incoming_mail_still_uses_the_auto_filter(session, gente):
    pide = cs.correo_desde_graph(pedido_de_ana(asunto="No funciona la impresora"))
    assert cs.procesar_correo(session, pide, CONFIG)[0] == "ticket"


# --- Freno de seguridad -------------------------------------------------------


@pytest.mark.parametrize("modo", MODOS)
def test_brake_creates_at_most_five_tickets_per_cycle(modo, entorno, factory, session, gente, caplog):
    pedidos = [pedido_de_ana(msg_id=f"<p{i}@data.cr>", conversacion=f"conv-{i}",
                             asunto=f"No funciona la impresora {i}") for i in range(7)]
    graph = FakeGraph(pedidos)

    with caplog.at_level(logging.ERROR, logger="backend.services.correo_service"):
        revisar(modo, factory, graph, entorno)
    assert len(tickets(session)) == cs.MAX_TICKETS_POR_CICLO == 5
    assert "ALERTA: freno de seguridad" in caplog.text
    assert "2 correo(s) que crearían más quedan para la próxima revisión" in caplog.text
    # Los dos que faltan siguen sin leer y sin registrar.
    assert len(graph.no_leidos()) == 2
    assert registro(session, "<p6@data.cr>") is None

    caplog.clear()
    revisar(modo, factory, graph, entorno)  # la próxima revisión los crea
    assert len(tickets(session)) == 7
    assert "ALERTA" not in caplog.text


def test_brake_counts_sent_and_inbox_together(entorno, factory, session, gente, caplog):
    enviados = [crear_enviado(asunto=f"Ticket: Pedido {i}") for i in range(4)]
    pedidos = [pedido_de_ana(msg_id=f"<q{i}@data.cr>", conversacion=f"conv-q{i}",
                             asunto=f"No funciona el equipo {i}") for i in range(3)]
    graph = FakeGraph(pedidos, enviados=enviados)
    with caplog.at_level(logging.ERROR, logger="backend.services.correo_service"):
        revisar("cron", factory, graph, entorno)
    assert len(tickets(session)) == 5
    assert "ALERTA: freno de seguridad" in caplog.text
