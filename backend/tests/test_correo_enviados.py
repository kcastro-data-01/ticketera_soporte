"""Tickets desde los correos que envía el dueño del buzón (Elementos enviados)
y la regla «quien escribe = solicitante, quien recibe = asignado».

Caso principal: kcastro@data.cr le escribe a pedro@data.cr → ticket asignado
a Pedro (se crea su usuario) → Pedro entra con Microsoft por primera vez y ve
el ticket en su lista. Graph y Microsoft simulados."""

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import func, select

from backend.models import Comment, History, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs
from backend.tests.test_correo import CONFIG, CONFIG_FILTRO, FakeGraph, crear_correo, factory, usuario  # noqa: F401
from backend.tests.test_login_microsoft import entrar, id_token, tenant_simulado  # noqa: F401

_ids = count(1)
YO = "kcastro@data.cr"


def crear_enviado(para=(("Pedro@Data.cr", "Pedro Rojas"),), asunto="Ticket: La impresora no imprime",
                  cuerpo="Pedro, la impresora del segundo piso no imprime desde ayer.",
                  msg_id=None, fecha=None, en_respuesta_a=None, cabeceras=None, propiedades=None,
                  conversacion=None) -> dict:
    """Mensaje con la forma de /me/mailFolders/sentitems/messages. Como en el
    buzón real, In-Reply-To llega solo como propiedad extendida (los enviados
    no traen esas cabeceras en ``internetMessageHeaders``)."""
    fecha = fecha or datetime.now(timezone.utc) + timedelta(minutes=1)
    extendidas = [{"id": k, "value": v} for k, v in (propiedades or {}).items()]
    if en_respuesta_a:
        extendidas.append({"id": cs.PROPIEDAD_IN_REPLY_TO, "value": en_respuesta_a})
    return {
        "id": f"ENV{next(_ids)}",
        "internetMessageId": msg_id or f"<enviado{next(_ids)}@data.cr>",
        "conversationId": conversacion or f"conv-enviado-{next(_ids)}",
        "subject": asunto,
        "from": {"emailAddress": {"name": "Kristin Castro", "address": YO}},
        "toRecipients": [{"emailAddress": {"address": c, "name": n}} for c, n in para],
        "body": {"contentType": "text", "content": cuerpo},
        "sentDateTime": fecha.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "internetMessageHeaders": [{"name": k, "value": v} for k, v in (cabeceras or {}).items()],
        "singleValueExtendedProperties": extendidas,
    }


@pytest.fixture
def yo(session):
    """La dueña del buzón (Administradora)."""
    user = User(name="Kristin Castro", email=YO, role="Administrador", is_active=True)
    session.add(user)
    session.commit()
    return user


def enviar(session, mensaje, config=CONFIG):
    return cs.procesar_enviado(session, cs.correo_desde_graph(mensaje), config)


def pedro(session):
    return session.scalar(select(User).where(func.lower(User.email) == "pedro@data.cr"))


# --- Ticket desde un correo enviado ---------------------------------------------


def test_sent_mail_creates_a_ticket_assigned_to_the_recipient(session, yo):
    resultado, aviso = enviar(session, crear_enviado())
    assert (resultado, aviso) == ("ticket", None)  # sin AVISAR_ASIGNADO no se avisa
    ticket = session.scalars(select(Ticket)).one()
    p = pedro(session)
    assert (p.name, p.email, p.role, p.password_hash) == ("Pedro Rojas", "pedro@data.cr", "Solicitante", None)
    assert ticket.created_by_id == yo.id
    assert ticket.assigned_to_id == p.id
    assert ticket.title == "La impresora no imprime"
    assert "Enviado por correo de kcastro@data.cr a pedro@data.cr" in ticket.description
    creado = session.scalars(select(History).where(History.ticket_id == ticket.id)).one()
    assert (creado.action, creado.field, creado.author) == ("created", "correo", "Kristin Castro")
    assert creado.new_value == "Ticket creado desde correo enviado por Kristin Castro a Pedro Rojas"


def test_existing_recipient_is_reused_whatever_the_case(session, yo):
    existente = User(name="Pedro R.", email="pedro@data.cr", role="Técnico")
    session.add(existente)
    session.commit()
    enviar(session, crear_enviado(para=(("PEDRO@DATA.CR", "Otro Nombre"),)))
    assert session.scalar(select(func.count(User.id))) == 2
    assert session.scalars(select(Ticket)).one().assigned_to_id == existente.id
    assert existente.name == "Pedro R."


def test_first_company_recipient_in_to_is_the_assignee_and_cc_does_not_count(session, yo):
    mensaje = crear_enviado(para=(("cliente@gmail.com", "Cliente"), ("ana@data.cr", "Ana Mora"),
                                  ("luis@data.cr", "Luis Solís")))
    mensaje["ccRecipients"] = [{"emailAddress": {"address": "jefe@data.cr", "name": "Jefe"}}]
    enviar(session, mensaje)
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.assignee.email == "ana@data.cr"
    assert session.scalar(select(User).where(User.email == "jefe@data.cr")) is None


def test_only_cc_to_the_company_is_ignored(session, yo):
    mensaje = crear_enviado(para=(("cliente@gmail.com", "Cliente"),))
    mensaje["ccRecipients"] = [{"emailAddress": {"address": "ana@data.cr", "name": "Ana"}}]
    assert enviar(session, mensaje) == ("ignorado", None)
    assert session.scalars(select(Ticket)).all() == []


@pytest.mark.parametrize("para", [
    (("cliente@gmail.com", "Cliente"),),
    ((YO, "Kristin"),),
    (),
])
def test_mail_only_to_outsiders_or_to_myself_is_ignored(session, yo, para):
    assert enviar(session, crear_enviado(para=para)) == ("ignorado", None)
    assert session.scalars(select(Ticket)).all() == []


@pytest.mark.parametrize("mensaje", [
    crear_enviado(asunto="Ticket #4 creado: La impresora no imprime"),
    crear_enviado(asunto="Comentario agregado al ticket #4"),
    crear_enviado(asunto="No pudimos crear tu ticket"),
    crear_enviado(cabeceras={"X-Ticketera": "1"}),
    crear_enviado(propiedades={cs.PROPIEDAD_X_TICKETERA: "1"}),
])
def test_mails_sent_by_the_app_are_ignored(session, yo, mensaje):
    assert enviar(session, mensaje)[0] == "ignorado"
    assert session.scalars(select(Ticket)).all() == []


def test_same_message_id_never_creates_two_tickets(session, yo):
    mensaje = crear_enviado(msg_id="<unico@data.cr>")
    assert enviar(session, mensaje)[0] == "ticket"
    assert enviar(session, mensaje)[0] == "repetido"
    assert len(session.scalars(select(Ticket)).all()) == 1


def test_sent_mail_without_ticket_prefix_never_creates_even_if_it_asks_for_help(session, yo):
    """Lo que envío solo crea un ticket con «Ticket:» al inicio del asunto
    (lo que llega sigue con el filtro auto)."""
    pide_ayuda = crear_enviado(asunto="No me funciona la impresora", cuerpo="Pedro, ¿la podés revisar?")
    assert enviar(session, pide_ayuda, CONFIG_FILTRO) == ("otro", None)
    assert session.scalars(select(Ticket)).all() == []


def test_sent_mail_that_does_not_ask_for_help_creates_nothing(session, yo):
    gracias = crear_enviado(asunto="Gracias por el informe", cuerpo="Pedro, lo reviso mañana.")
    assert enviar(session, gracias, CONFIG_FILTRO) == ("otro", None)
    # Queda anotado: no se vuelve a revisar.
    assert enviar(session, gracias, CONFIG_FILTRO) == ("repetido", None)
    assert session.scalars(select(Ticket)).all() == []
    assert pedro(session) is None, "tampoco se crea el usuario del destinatario"


def test_sent_mail_with_filter_todos_still_needs_the_prefix(session, yo):
    gracias = crear_enviado(asunto="Gracias por el informe", cuerpo="Pedro, lo reviso mañana.")
    assert enviar(session, gracias, CONFIG)[0] == "otro"
    assert session.scalars(select(Ticket)).all() == []


@pytest.mark.parametrize("asunto", ["Ticket: Cambiar el tóner", "TICKET: Cambiar el tóner",
                                    "  ticket:Cambiar el tóner"])
def test_ticket_prefix_creates_and_is_removed_from_the_title(session, yo, asunto):
    assert enviar(session, crear_enviado(asunto=asunto, cuerpo="Cuando pueda."), CONFIG_FILTRO)[0] == "ticket"
    assert session.scalars(select(Ticket)).one().title == "Cambiar el tóner"


def test_ticket_prefix_must_be_at_the_start(session, yo):
    for asunto in ("RE: Ticket: Cambiar el tóner", "Sobre el Ticket: tóner", "Ticket #5 tóner"):
        correo = crear_enviado(asunto=asunto, cuerpo="Cuando pueda.")
        assert enviar(session, correo, CONFIG_FILTRO)[0] in ("otro", "ignorado")
    assert session.scalars(select(Ticket)).all() == []


def test_inactive_recipient_is_ignored(session, yo):
    session.add(User(name="Pedro", email="pedro@data.cr", role="Técnico", is_active=False))
    session.commit()
    assert enviar(session, crear_enviado())[0] == "ignorado"


def test_avisar_asignado_prepares_the_mail_when_enabled(session, yo):
    config = cs.ConfigCorreo(usuario=YO, app_url="http://ticketera.data.cr", filtro="todos",
                             dominio_empresa="data.cr", avisar_asignado=True)
    resultado, aviso = enviar(session, crear_enviado(), config)
    ticket = session.scalars(select(Ticket)).one()
    assert resultado == "ticket"
    assert aviso.para == "pedro@data.cr"
    assert aviso.asunto == f"[Ticket #{ticket.id}] Se le asignó el ticket #{ticket.id}: {ticket.title}"
    assert f"Se le asignó el ticket #{ticket.id}" in aviso.texto
    assert f"http://ticketera.data.cr/detalle.html?id={ticket.id}" in aviso.texto


def test_avisar_asignado_comes_from_the_environment():
    base = {"CORREO_ACTIVO": "1", "CORREO_USUARIO": YO}
    assert cs.config_desde_entorno(base).avisar_asignado is False
    assert cs.config_desde_entorno({**base, "AVISAR_ASIGNADO": "false"}).avisar_asignado is False
    assert cs.config_desde_entorno({**base, "AVISAR_ASIGNADO": "true"}).avisar_asignado is True


# --- Hilos: respuestas como comentarios --------------------------------------------


def test_reply_chain_is_one_ticket_with_comments(session, yo):
    """Yo le escribo a Pedro → Pedro me responde (bandeja) → yo le respondo
    (enviados): un solo ticket con dos comentarios."""
    original = crear_enviado(msg_id="<original@data.cr>")
    assert enviar(session, original)[0] == "ticket"
    ticket = session.scalars(select(Ticket)).one()

    respuesta_pedro = crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas",
                                   asunto="RE: La impresora no imprime", cuerpo="Ya la revisé, era el cable.",
                                   msg_id="<pedro1@data.cr>",
                                   cabeceras={"In-Reply-To": "<original@data.cr>",
                                              "References": "<original@data.cr>"})
    resultado, respuesta = cs.procesar_correo(session, cs.correo_desde_graph(respuesta_pedro), CONFIG_FILTRO)
    assert resultado == "comentario"

    mi_respuesta = crear_enviado(asunto="RE: La impresora no imprime", cuerpo="Gracias, Pedro.",
                                 msg_id="<yo2@data.cr>", en_respuesta_a="<pedro1@data.cr>")
    assert enviar(session, mi_respuesta, CONFIG_FILTRO) == ("comentario", None)

    assert len(session.scalars(select(Ticket)).all()) == 1
    comentarios = session.scalars(select(Comment).where(Comment.ticket_id == ticket.id)).all()
    assert [(c.author, c.content) for c in comentarios] == [
        ("Pedro Rojas", "Ya la revisé, era el cable."), ("Kristin Castro", "Gracias, Pedro.")]


def test_conversation_id_finds_the_thread_without_reply_headers(session, yo):
    """Si la respuesta no trae In-Reply-To/References, el hilo se encuentra
    por el conversationId: la respuesta de Pedro (bandeja) y la mía
    (enviados) son comentarios del mismo ticket."""
    original = crear_enviado(msg_id="<conv-original@data.cr>", conversacion="AAQk-hilo-1")
    assert enviar(session, original)[0] == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    guardado = session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<conv-original@data.cr>"))
    assert guardado.conversation_id == "AAQk-hilo-1"

    de_pedro = crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas", asunto="Sobre la impresora",
                            cuerpo="Ya cambié el cable.", msg_id="<conv-pedro@data.cr>")
    de_pedro["conversationId"] = "AAQk-hilo-1"
    assert cs.procesar_correo(session, cs.correo_desde_graph(de_pedro), CONFIG_FILTRO)[0] == "comentario"

    mia = crear_enviado(asunto="RE: La impresora no imprime", cuerpo="Gracias.", conversacion="AAQk-hilo-1")
    assert enviar(session, mia, CONFIG_FILTRO) == ("comentario", None)

    assert len(session.scalars(select(Ticket)).all()) == 1
    assert [c.content for c in session.scalars(select(Comment).where(Comment.ticket_id == ticket.id))] == [
        "Ya cambié el cable.", "Gracias."]


def test_app_confirmation_in_the_same_conversation_is_not_a_comment(session, yo):
    enviar(session, crear_enviado(conversacion="AAQk-hilo-2"))
    ticket = session.scalars(select(Ticket)).one()
    confirmacion = crear_enviado(asunto=f"Ticket #{ticket.id} creado: {ticket.title}", conversacion="AAQk-hilo-2",
                                 cabeceras={"X-Ticketera": "1"})
    vieja = crear_enviado(asunto=f"Ticket #{ticket.id} creado: {ticket.title}", conversacion="AAQk-hilo-2")
    assert enviar(session, confirmacion)[0] == "ignorado"
    assert enviar(session, vieja)[0] == "ignorado", "las anteriores a X-Ticketera, por el asunto"
    assert session.scalars(select(Comment)).all() == []


def test_reply_with_ticket_number_in_subject_is_a_comment(session, yo):
    enviar(session, crear_enviado())
    ticket = session.scalars(select(Ticket)).one()
    seguimiento = crear_enviado(asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                                cuerpo="Pedro, ¿pudiste revisarla?")
    assert enviar(session, seguimiento)[0] == "comentario"
    assert len(session.scalars(select(Ticket)).all()) == 1


# --- Correos que llegan: asignados al dueño del buzón -------------------------------


def test_incoming_mail_is_assigned_to_the_mailbox_owner(session, yo, usuario):  # noqa: F811
    resultado, _ = cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    assert resultado == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.assigned_to_id == yo.id
    creado = session.scalars(select(History).where(History.ticket_id == ticket.id)).one()
    assert creado.new_value == "Ticket creado desde correo enviado por Ana Pérez a Kristin Castro"


def test_incoming_mail_is_not_round_robin_even_with_technicians(session, yo, usuario):  # noqa: F811
    session.add(User(name="Técnico Uno", email="t1@data.cr", role="Técnico"))
    session.commit()
    cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    assert session.scalars(select(Ticket)).one().assigned_to_id == yo.id


def test_incoming_subject_ticket_prefix_always_creates_and_is_removed(session, yo, usuario):  # noqa: F811
    correo = crear_correo(asunto="ticket: Revisar el proyector", cuerpo="Cuando pueda.")
    assert cs.procesar_correo(session, cs.correo_desde_graph(correo), CONFIG_FILTRO)[0] == "ticket"
    assert session.scalars(select(Ticket)).one().title == "Revisar el proyector"


# --- revisar_buzon con Elementos enviados -------------------------------------------


def test_revisar_buzon_processes_sent_items_without_touching_them(factory, session, yo):
    viejo = crear_enviado(msg_id="<viejo@data.cr>", fecha=datetime.now(timezone.utc) - timedelta(days=3))
    nuevo = crear_enviado(msg_id="<nuevo@data.cr>")
    graph = FakeGraph([], enviados=[viejo, nuevo])

    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {"enviado_ticket": 1}
    # Solo el enviado después de activar la función; el viejo no se procesa.
    assert session.scalars(select(Ticket)).one().title == "La impresora no imprime"
    assert session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<viejo@data.cr>")) is None
    # No se movió, ni se marcó, ni se respondió nada.
    assert not any(metodo in ("PATCH", "POST") for metodo, _ in graph.llamadas)
    assert all(m["carpeta"] == "sentitems" for m in graph.mensajes.values())

    # La segunda revisión no repite nada y la fecha de inicio se guardó una sola vez.
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"enviado_repetido": 1}
    marcas = session.scalars(select(ProcessedEmail).where(
        ProcessedEmail.message_id == cs.MARCA_INICIO_ENVIADOS)).all()
    assert len(marcas) == 1


def test_revisar_buzon_sends_the_notice_only_with_avisar_asignado(factory, session, yo):
    config = cs.ConfigCorreo(usuario=YO, app_url="http://ticketera.data.cr", filtro="todos",
                             dominio_empresa="data.cr", avisar_asignado=True)
    graph = FakeGraph([], enviados=[crear_enviado()])
    cs.revisar_buzon(factory, config, graph.cliente)
    [correo] = graph.correos_nuevos
    assert correo["message"]["toRecipients"] == [{"emailAddress": {"address": "pedro@data.cr"}}]
    assert {"name": "X-Ticketera", "value": "1"} in correo["message"]["internetMessageHeaders"]

    sin_aviso = FakeGraph([], enviados=[crear_enviado()])
    cs.revisar_buzon(factory, CONFIG, sin_aviso.cliente)
    assert sin_aviso.correos_nuevos == []


# --- De punta a punta: correo enviado → Pedro entra con Microsoft → lo ve ----------


def test_end_to_end_sent_mail_then_microsoft_login_shows_the_ticket(client, session, factory, yo,
                                                                    tenant_simulado):  # noqa: F811
    graph = FakeGraph([], enviados=[crear_enviado()])
    cs.revisar_buzon(factory, CONFIG, graph.cliente)
    session.expire_all()
    ticket = session.scalars(select(Ticket)).one()
    creado = pedro(session)
    assert ticket.assigned_to_id == creado.id

    # Pedro entra por primera vez con Microsoft (correo con otras mayúsculas).
    resp = entrar(client, id_token(name="Pedro Rojas Mora", email="PEDRO@data.cr",
                                   preferred_username="pedro@data.cr"))
    assert resp.status_code == 200, resp.text
    cabeceras = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    yo_pedro = client.get("/api/auth/me", headers=cabeceras).json()
    assert yo_pedro["id"] == creado.id  # el mismo usuario, no uno nuevo
    assert session.scalar(select(func.count(User.id)).where(func.lower(User.email) == "pedro@data.cr")) == 1

    lista = client.get("/api/tickets", headers=cabeceras)
    assert [t["id"] for t in lista.json()] == [ticket.id]
    assert client.get(f"/api/tickets/{ticket.id}", headers=cabeceras).status_code == 200
    session.expire_all()
    assert session.get(Ticket, ticket.id).assigned_to_id == creado.id  # sus tickets no cambian


def test_reply_in_the_same_check_finds_the_thread(factory, session, yo):
    """Enviado y respuesta de Pedro en la misma revisión: primero se procesan
    los enviados, así la respuesta va como comentario y no crea otro ticket."""
    original = crear_enviado(msg_id="<rapido@data.cr>")
    respuesta = crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas",
                             asunto="RE: La impresora no imprime", cuerpo="La impresora sigue sin imprimir.",
                             msg_id="<pedro-rapido@data.cr>", cabeceras={"In-Reply-To": "<rapido@data.cr>"})
    graph = FakeGraph([respuesta], enviados=[original])
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {"enviado_ticket": 1, "comentario": 1}
    assert len(session.scalars(select(Ticket)).all()) == 1
