"""Avisos por correo de los cambios de estado (``AVISAR_ESTADOS``) y de las
asignaciones (``AVISAR_ASIGNADO``) hechos desde la app. Graph simulado
(``FakeGraph``), sin correo real.

* Estado: al solicitante y al asignado, menos a quien lo cambió; con el
  motivo en el mismo correo (sin un aviso aparte de comentario); a Cerrado,
  avisa que ya no admite cambios y una respuesta no es comentario.
* Asignación: «Se le asignó» al nuevo asignado y «fue asignado a» al
  solicitante; quitar la asignación o dejar el mismo asignado no avisa.
* Sin duplicados, nada si el único involucrado es quien hizo el cambio, y el
  cambio se guarda aunque falle el envío.
* Como los demás avisos: registrados como ``aviso_app`` antes de enviarse;
  su copia en Enviados se ignora y una respuesta vuelve como comentario."""

import pytest
from sqlalchemy import select

from backend.models import Comment, History, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs
from backend.tests.test_asistente import login_as
from backend.tests.test_correo import FakeGraph, crear_correo, factory  # noqa: F401
from backend.tests.test_correo_ciclo import CONFIG
from backend.tests.test_correo_enviados import crear_enviado
from backend.tests.test_correo_reglas import APP_URL, MODOS, YO, entorno, revisar  # noqa: F401


@pytest.fixture
def avisos(entorno):  # noqa: F811
    entorno.setenv("AVISAR_ESTADOS", "true")
    entorno.setenv("AVISAR_ASIGNADO", "true")
    entorno.setenv("AVISAR_COMENTARIOS", "true")
    return entorno


@pytest.fixture
def graph(avisos):
    falso = FakeGraph([], copiar_a_enviados=True)
    avisos.setattr(cs, "crear_cliente", lambda config, fabrica: falso.cliente)
    return falso


@pytest.fixture
def gente(client, session):
    """Yo (Administradora, con sesión), Ana (solicitante), Pedro y Juan (técnicos)."""
    headers = login_as(client, session, "Administrador", YO, "Kristin Castro")
    personas = {
        "ana": User(name="Ana Pérez", email="ana@data.cr", role="Solicitante"),
        "pedro": User(name="Pedro Rojas", email="pedro@data.cr", role="Técnico"),
        "juan": User(name="Juan Solís", email="juan@data.cr", role="Técnico"),
    }
    session.add_all(personas.values())
    session.commit()
    personas["yo"] = session.scalar(select(User).where(User.email == YO))
    personas["headers"] = headers
    return personas


def nuevo_ticket(session, creador, asignado=None, estado="Nuevo"):
    ticket = Ticket(title="La impresora no imprime", description="x", category="Hardware",
                    priority="Alta", state=estado, created_by_id=creador.id,
                    assigned_to_id=asignado.id if asignado else None)
    session.add(ticket)
    session.commit()
    return ticket


def estado(client, headers, ticket, nuevo, motivo=None):
    cuerpo = {"state": nuevo} | ({"motivo": motivo} if motivo else {})
    return client.patch(f"/api/tickets/{ticket.id}/state", json=cuerpo, headers=headers)


def asignar(client, headers, ticket, usuario):
    return client.patch(f"/api/tickets/{ticket.id}/assign",
                        json={"assigned_to_id": usuario.id if usuario else None}, headers=headers)


def enviados(graph):
    """(destinatario, asunto, texto) de cada correo nuevo, por destinatario."""
    return sorted((c["message"]["toRecipients"][0]["emailAddress"]["address"], c["message"]["subject"],
                   c["message"]["body"]["content"]) for c in graph.correos_nuevos)


def para(graph):
    return [p for p, _, _ in enviados(graph)]


# --- A. Cambio de estado -------------------------------------------------------------------


def test_estado_avisa_al_solicitante_y_al_asignado(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200

    assert para(graph) == ["ana@data.cr", "pedro@data.cr"]  # no a quien lo cambió
    for destinatario, asunto, texto in enviados(graph):
        nombre = "Ana Pérez" if destinatario == "ana@data.cr" else "Pedro Rojas"
        assert asunto == f"[Ticket #{ticket.id}] El ticket #{ticket.id} pasó a «En proceso»"
        assert texto.startswith(f"Hola {nombre},\n\nKristin Castro cambió el estado del ticket #{ticket.id}.")
        assert "Título: La impresora no imprime\nEstado: Nuevo → En proceso" in texto
        assert f"Puede verlo aquí: {APP_URL}/detalle.html?id={ticket.id}" in texto
        assert f"debe mantener «[Ticket #{ticket.id}]»" in texto
        assert "Motivo:" not in texto and "quedó cerrado" not in texto
        assert texto.endswith("Mesa de ayuda")
    # Registrados como aviso_app (con el ticket) antes de enviarse.
    registros = session.scalars(select(ProcessedEmail).where(ProcessedEmail.result == "aviso_app")).all()
    assert [(r.message_id, r.ticket_id) for r in registros] == [
        ("<app-1@data.cr>", ticket.id), ("<app-2@data.cr>", ticket.id)]


def test_estado_con_motivo_un_solo_correo_con_el_motivo(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="En proceso")
    resp = estado(client, gente["headers"], ticket, "Resuelto", motivo="Se cambió el tóner.")
    assert resp.status_code == 200

    assert para(graph) == ["ana@data.cr", "pedro@data.cr"]  # uno por persona, no dos
    for _, asunto, texto in enviados(graph):
        assert "pasó a «Resuelto»" in asunto
        assert "Estado: En proceso → Resuelto\n\nMotivo: Se cambió el tóner." in texto
    assert all("Nuevo comentario" not in asunto for _, asunto, _ in enviados(graph))
    assert session.scalars(select(Comment.content)).all() == ["Se cambió el tóner."]


def test_estado_a_cerrado_dice_que_no_admite_cambios(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="Resuelto")
    assert estado(client, gente["headers"], ticket, "Cerrado", motivo="Confirmado por Ana.").status_code == 200

    for _, asunto, texto in enviados(graph):
        assert asunto == f"[Ticket #{ticket.id}] El ticket #{ticket.id} pasó a «Cerrado»"
        assert "Motivo: Confirmado por Ana.\n\nEste ticket quedó cerrado y ya no admite cambios." in texto
        assert "su respuesta se agrega como comentario" not in texto  # no lo sería


def test_estado_lo_cambia_el_asignado_solo_avisa_al_solicitante(client, session, graph, gente):
    pedro = login_as(client, session, "Técnico", "pedro2@data.cr", "Pedro Dos")
    ticket = nuevo_ticket(session, gente["ana"], session.scalar(select(User).where(User.email == "pedro2@data.cr")))
    assert estado(client, pedro, ticket, "En proceso").status_code == 200
    [(destinatario, _, texto)] = enviados(graph)
    assert destinatario == "ana@data.cr" and "Pedro Dos cambió el estado" in texto


def test_estado_solicitante_y_asignado_la_misma_persona_un_solo_correo(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["pedro"], gente["pedro"])
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200
    assert para(graph) == ["pedro@data.cr"]


def test_estado_si_el_unico_involucrado_es_quien_cambia_no_se_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["yo"], gente["yo"])
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200
    ticket_sin_asignar = nuevo_ticket(session, gente["yo"])
    assert estado(client, gente["headers"], ticket_sin_asignar, "En proceso").status_code == 200
    assert graph.correos_nuevos == []


def test_estado_sin_asignado_avisa_solo_al_solicitante(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"])
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200
    assert para(graph) == ["ana@data.cr"]


def test_estado_no_avisa_a_usuarios_desactivados(client, session, graph, gente):
    gente["pedro"].is_active = False
    session.commit()
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200
    assert para(graph) == ["ana@data.cr"]


def test_estado_sin_avisar_estados_no_envia(client, session, graph, gente, avisos):
    avisos.setenv("AVISAR_ESTADOS", "false")
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert estado(client, gente["headers"], ticket, "En proceso", motivo="Reviso hoy.").status_code == 200
    assert graph.correos_nuevos == []


def test_estado_rechazado_no_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="En proceso")
    assert estado(client, gente["headers"], ticket, "Nuevo").status_code == 409
    cerrado = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="Cerrado")
    assert estado(client, gente["headers"], cerrado, "En proceso").status_code == 409
    assert graph.correos_nuevos == []


def test_estado_se_guarda_aunque_falle_el_envio(client, session, graph, gente, avisos, caplog):
    avisos.setattr(cs.logger, "propagate", True)

    def falla(*_args, **_kwargs):
        raise cs.ErrorGraph("POST /me/messages → 500: caído")

    graph.cliente.enviar = falla
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    with caplog.at_level("ERROR", logger=cs.logger.name):
        assert estado(client, gente["headers"], ticket, "En proceso", motivo="Voy.").status_code == 200
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "En proceso"
    assert session.scalars(select(Comment.content)).all() == ["Voy."]
    assert f"No se pudo avisar por correo el cambio de estado del ticket #{ticket.id}" in caplog.text


# --- B. Asignación -------------------------------------------------------------------------


def test_reasignar_avisa_al_nuevo_asignado_y_al_solicitante(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 200

    [(a_ana, asunto_ana, texto_ana), (a_juan, asunto_juan, texto_juan)] = enviados(graph)
    assert (a_ana, a_juan) == ("ana@data.cr", "juan@data.cr")  # Pedro (el anterior), no
    assert asunto_juan == f"[Ticket #{ticket.id}] Se le asignó el ticket #{ticket.id}"
    assert texto_juan.startswith(f"Hola Juan Solís,\n\nKristin Castro le asignó el ticket #{ticket.id}.")
    assert "Título: La impresora no imprime\nPrioridad: Alta" in texto_juan
    assert f"Puede verlo aquí: {APP_URL}/detalle.html?id={ticket.id}" in texto_juan
    assert asunto_ana == f"[Ticket #{ticket.id}] El ticket #{ticket.id} fue asignado a Juan Solís"
    assert texto_ana.startswith(
        f"Hola Ana Pérez,\n\nKristin Castro asignó su ticket #{ticket.id} a Juan Solís.")
    assert "Prioridad: Alta" in texto_ana and f"{APP_URL}/detalle.html?id={ticket.id}" in texto_ana
    registros = session.scalars(select(ProcessedEmail.ticket_id).where(ProcessedEmail.result == "aviso_app"))
    assert registros.all() == [ticket.id, ticket.id]


def test_asignar_un_ticket_sin_asignar(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"])
    assert asignar(client, gente["headers"], ticket, gente["pedro"]).status_code == 200
    assert para(graph) == ["ana@data.cr", "pedro@data.cr"]


def test_quitar_la_asignacion_no_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, None).status_code == 200
    assert graph.correos_nuevos == []


def test_asignar_al_mismo_no_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["pedro"]).status_code == 200
    assert graph.correos_nuevos == []


def test_asignar_al_propio_solicitante_un_solo_correo(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["pedro"]).status_code == 200
    [(destinatario, asunto, _)] = enviados(graph)
    assert destinatario == "pedro@data.cr" and "Se le asignó" in asunto


def test_asignarse_a_si_mismo_solo_avisa_al_solicitante(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"])
    assert asignar(client, gente["headers"], ticket, gente["yo"]).status_code == 200
    [(destinatario, asunto, _)] = enviados(graph)
    assert (destinatario, asunto) == ("ana@data.cr",
                                      f"[Ticket #{ticket.id}] El ticket #{ticket.id} fue asignado a Kristin Castro")


def test_asignar_si_el_unico_involucrado_es_quien_asigna_no_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["yo"])
    assert asignar(client, gente["headers"], ticket, gente["yo"]).status_code == 200
    assert graph.correos_nuevos == []


def test_asignar_un_cerrado_no_envia(client, session, graph, gente):
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="Cerrado")
    assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 409
    assert graph.correos_nuevos == []


def test_asignar_sin_avisar_asignado_no_envia(client, session, graph, gente, avisos):
    avisos.setenv("AVISAR_ASIGNADO", "false")
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 200
    assert graph.correos_nuevos == []


def test_asignacion_se_guarda_aunque_falle_el_envio(client, session, graph, gente, avisos, caplog):
    avisos.setattr(cs.logger, "propagate", True)

    def falla(*_args, **_kwargs):
        raise cs.ErrorGraph("POST /me/messages → 500: caído")

    graph.cliente.enviar = falla
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    with caplog.at_level("ERROR", logger=cs.logger.name):
        assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 200
    session.expire_all()
    assert session.get(Ticket, ticket.id).assigned_to_id == gente["juan"].id
    assert session.scalar(select(History.new_value).where(History.action == "assigned")) == "Juan Solís"
    assert f"No se pudo avisar por correo la asignación del ticket #{ticket.id}" in caplog.text


# --- C. Ciclos: Enviados y respuestas ------------------------------------------------------


@pytest.mark.parametrize("asunto,cuerpo", [
    ("[Ticket #1] El ticket #1 pasó a «En proceso»", "Hola Ana"),
    ("[Ticket #1] El ticket #1 pasó a «Cerrado»", "Hola Ana"),
    ("[Ticket #1] Se le asignó el ticket #1", "Hola Juan"),
    ("[Ticket #1] El ticket #1 fue asignado a Juan Solís", "Hola Ana"),
    # Asunto cambiado: las frases fijas lo delatan.
    ("Aviso", "Hola Ana,\n\nKristin Castro cambió el estado del ticket #1.\n\nTítulo: Impresora"),
    ("Aviso", "Hola Juan,\n\nKristin Castro le asignó el ticket #1.\n\nTítulo: Impresora"),
    ("Aviso", "Hola Ana,\n\nKristin Castro asignó su ticket #1 a Juan Solís."),
])
def test_copia_del_aviso_en_enviados_se_ignora_sin_registro(session, asunto, cuerpo):
    session.add(User(name="Juan Solís", email="juan@data.cr", role="Técnico"))
    session.commit()
    copia = cs.correo_desde_graph(crear_enviado(para=(("juan@data.cr", "Juan Solís"),), asunto=asunto,
                                                cuerpo=cuerpo, msg_id="<otro-id@data.cr>"))
    assert cs.procesar_enviado(session, copia, CONFIG) == ("ignorado", None)
    assert session.scalars(select(Ticket)).all() == []


@pytest.mark.parametrize("modo", MODOS)
def test_avisos_en_enviados_nunca_crean_tickets(modo, client, session, graph, gente, factory, avisos):  # noqa: F811
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 200
    assert estado(client, gente["headers"], ticket, "En proceso", motivo="Reviso hoy.").status_code == 200
    assert len(graph.correos_nuevos) == 4
    for _ in range(2):
        revisar(modo, factory, graph, avisos)
    session.expire_all()
    assert [t.id for t in session.scalars(select(Ticket))] == [ticket.id]
    assert session.scalars(select(Comment.content)).all() == ["Reviso hoy."]
    assert len(graph.correos_nuevos) == 4  # ningún aviso nuevo por las copias


def responder(graph, aviso_numero, remitente, nombre, cuerpo, msg_id):
    """Respuesta en el hilo del aviso ``<app-N@data.cr>``."""
    original = graph.correos_nuevos[aviso_numero - 1]["message"]
    respuesta = dict(crear_correo(remitente=remitente, nombre=nombre, asunto=f"RE: {original['subject']}",
                                  cuerpo=cuerpo, msg_id=msg_id,
                                  cabeceras={"In-Reply-To": f"<app-{aviso_numero}@data.cr>"}),
                     conversationId=f"conv-app-{aviso_numero}")
    graph.mensajes[respuesta["id"]] = dict(respuesta, isRead=False, carpeta="inbox")


@pytest.mark.parametrize("modo", MODOS)
def test_responder_a_los_avisos_es_un_comentario(modo, client, session, graph, gente, factory, avisos):  # noqa: F811
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"])
    assert asignar(client, gente["headers"], ticket, gente["juan"]).status_code == 200  # app-1 Juan, app-2 Ana
    assert estado(client, gente["headers"], ticket, "En proceso").status_code == 200  # app-3 Ana, app-4 Juan
    assert para(graph) == ["ana@data.cr", "ana@data.cr", "juan@data.cr", "juan@data.cr"]
    responder(graph, 1, "juan@data.cr", "Juan Solís", "Lo veo mañana.", "<r1@data.cr>")
    responder(graph, 3, "ana@data.cr", "Ana Pérez", "Gracias.", "<r2@data.cr>")
    revisar(modo, factory, graph, avisos)
    session.expire_all()
    assert sorted(session.scalars(select(Comment.content).where(Comment.ticket_id == ticket.id))) == [
        "Gracias.", "Lo veo mañana."]
    assert [t.id for t in session.scalars(select(Ticket))] == [ticket.id]


@pytest.mark.parametrize("modo", MODOS)
def test_responder_al_aviso_de_cerrado_no_es_comentario(modo, client, session, graph, gente, factory, avisos):  # noqa: F811
    ticket = nuevo_ticket(session, gente["ana"], gente["pedro"], estado="Resuelto")
    assert estado(client, gente["headers"], ticket, "Cerrado").status_code == 200
    a_ana = next(i + 1 for i, c in enumerate(graph.correos_nuevos)
                 if c["message"]["toRecipients"][0]["emailAddress"]["address"] == "ana@data.cr")
    responder(graph, a_ana, "ana@data.cr", "Ana Pérez", "Sigue fallando.", "<r-cerrado@data.cr>")
    revisar(modo, factory, graph, avisos)
    session.expire_all()
    assert session.scalars(select(Comment)).all() == []
    registro = session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<r-cerrado@data.cr>"))
    assert (registro.result, registro.ticket_id) == ("cerrado", ticket.id)
    [(_, respuesta)] = graph.respuestas
    assert respuesta["message"]["subject"] == f"Ticket #{ticket.id} cerrado"
