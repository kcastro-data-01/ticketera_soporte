"""Reglas del correo, de punta a punta y en los dos modos: «cron» (Vercel,
``revisar_una_vez`` por cada POST /api/cron/correo) y «hilo» (Docker, una
vuelta de ``_bucle``). Graph simulado (``FakeGraph``), sin correo real.

* Remitente de la empresa sin cuenta → aviso para entrar primero, sin
  usuario ni ticket y sin repetir el aviso.
* Con cuenta → ticket asignado al dueño del buzón y confirmación.
* Lo que envía el dueño usa el mismo filtro; «Ticket:» siempre crea.
* Comentan por correo los que están en el hilo (Para o CC) y tienen cuenta.
* Un comentario hecho en la app avisa por correo a los demás; uno que llega
  por correo, no."""

import pytest
from sqlalchemy import func, select

from backend.models import Comment, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs
from backend.tests.test_asistente import login_as
from backend.tests.test_correo import FakeGraph, crear_correo, factory  # noqa: F401
from backend.tests.test_correo_enviados import crear_enviado

YO = "kcastro@data.cr"
APP_URL = "https://tickets-americandata.vercel.app"
MODOS = ["cron", "hilo"]


@pytest.fixture
def entorno(monkeypatch):
    """Variables como en Vercel / Docker (sin el modo, que pone cada prueba)."""
    valores = {"CORREO_ACTIVO": "1", "CORREO_USUARIO": YO, "APP_URL": APP_URL,
               "DOMINIO_EMPRESA": "data.cr", "CORREO_FILTRO": "auto", "AVISAR_ASIGNADO": "true",
               "AVISAR_COMENTARIOS": "true"}
    for nombre, valor in valores.items():
        monkeypatch.setenv(nombre, valor)
    return monkeypatch


def revisar(modo, factory, graph, monkeypatch):  # noqa: F811
    """Una revisión del buzón como la hace cada modo."""
    monkeypatch.setenv("CORREO_MODO", modo)
    if modo == "cron":
        return cs.revisar_una_vez(factory, crear=lambda config, fabrica: graph.cliente)
    config = cs.config_desde_entorno()
    assert config.modo == "hilo"
    vueltas = []

    def una_vuelta(segundos):
        vueltas.append(segundos)
        cs._detener.set()
        return True

    monkeypatch.setattr(cs._detener, "wait", una_vuelta)
    cs._detener.clear()
    cs._bucle(factory, config, graph.cliente)
    cs._detener.clear()
    assert vueltas == [config.intervalo]


def agregar(graph, mensaje):
    """Un correo nuevo que llega a la bandeja entre una revisión y otra."""
    graph.mensajes[mensaje["id"]] = dict(mensaje, isRead=False, carpeta="inbox")


@pytest.fixture
def gente(session):
    """La dueña del buzón, una solicitante, un técnico y alguien más con cuenta."""
    personas = {
        "yo": User(name="Kristin Castro", email=YO, role="Administrador"),
        "ana": User(name="Ana Pérez", email="ana@data.cr", role="Solicitante"),
        "pedro": User(name="Pedro Rojas", email="pedro@data.cr", role="Técnico"),
        "juan": User(name="Juan Solís", email="juan@data.cr", role="Técnico"),
    }
    session.add_all(personas.values())
    session.commit()
    return personas


def usuario(session, correo):
    return session.scalar(select(User).where(func.lower(User.email) == correo))


# --- Correos que llegan -------------------------------------------------------------


@pytest.mark.parametrize("modo", MODOS)
def test_company_sender_without_account_gets_the_notice_once(modo, entorno, factory, session, gente):
    mensaje = crear_correo(remitente="Luis@Data.cr", nombre="Luis Mora", msg_id="<luis1@data.cr>")
    graph = FakeGraph([mensaje])
    revisar(modo, factory, graph, entorno)

    [(respondido, enviado)] = graph.respuestas
    assert respondido == mensaje["id"]  # en el mismo hilo
    assert enviado["message"]["subject"] == cs.ASUNTO_SIN_CUENTA
    assert (f"Para crear tickets por correo, primero ingrese a la ticketera con su cuenta de "
            f"Microsoft de la empresa: {APP_URL}. Después vuelva a enviar su solicitud."
            ) in enviado["message"]["body"]["content"]
    assert enviado["message"]["internetMessageHeaders"] == [
        {"name": "X-Auto-Response-Suppress", "value": "All"}, {"name": "X-Ticketera", "value": "1"}]
    assert usuario(session, "luis@data.cr") is None
    assert session.scalars(select(Ticket)).all() == []

    # Otra revisión, y el mismo correo de nuevo en la bandeja (no se pudo
    # mover): sin segundo aviso.
    revisar(modo, factory, graph, entorno)
    agregar(graph, dict(mensaje, id="AAMk-otra-vez"))
    revisar(modo, factory, graph, entorno)
    assert len(graph.respuestas) == 1
    assert session.scalars(select(ProcessedEmail).where(
        ProcessedEmail.message_id == "<luis1@data.cr>")).one().result == "sin_cuenta"


@pytest.mark.parametrize("modo", MODOS)
def test_automatic_and_app_mail_never_get_the_notice(modo, entorno, factory, session, gente):
    graph = FakeGraph([
        crear_correo(remitente="luis@data.cr", msg_id="<auto@x>", cabeceras={"Auto-Submitted": "auto-replied"}),
        crear_correo(remitente="noreply@data.cr", msg_id="<noreply@x>"),
        crear_correo(remitente="luis@data.cr", msg_id="<re-aviso@x>", asunto=f"RE: {cs.ASUNTO_SIN_CUENTA}",
                     cuerpo="No me funciona la impresora"),
        crear_correo(remitente="luis@otro.com", msg_id="<externo@x>"),
    ])
    revisar(modo, factory, graph, entorno)
    assert graph.respuestas == []
    assert session.scalars(select(Ticket)).all() == []


@pytest.mark.parametrize("modo", MODOS)
def test_registered_sender_gets_ticket_and_confirmation(modo, entorno, factory, session, gente):
    graph = FakeGraph([crear_correo(remitente="ana@data.cr", asunto="No me funciona la impresora")])
    revisar(modo, factory, graph, entorno)

    ticket = session.scalars(select(Ticket)).one()
    assert (ticket.created_by_id, ticket.assigned_to_id) == (gente["ana"].id, gente["yo"].id)
    [(_, enviado)] = graph.respuestas
    assert enviado["message"]["subject"] == f"Ticket #{ticket.id} creado: {ticket.title}"
    assert f"{APP_URL}/detalle.html?id={ticket.id}" in enviado["message"]["body"]["content"]
    assert graph.no_leidos() == []


# --- Correos que envío --------------------------------------------------------------


@pytest.mark.parametrize("modo", MODOS)
def test_sent_help_request_without_prefix_creates_assigned_ticket_and_notice(modo, entorno, factory, session,
                                                                            gente):
    enviado = crear_enviado(para=(("nueva@data.cr", "Nueva Persona"),), asunto="No me funciona la impresora",
                            cuerpo="¿La podés revisar?")
    graph = FakeGraph([], enviados=[enviado])
    revisar(modo, factory, graph, entorno)

    ticket = session.scalars(select(Ticket)).one()
    nueva = usuario(session, "nueva@data.cr")
    assert nueva is not None and nueva.name == "Nueva Persona"  # para que lo vea al entrar
    assert (ticket.title, ticket.created_by_id, ticket.assigned_to_id) == (
        "No me funciona la impresora", gente["yo"].id, nueva.id)
    [aviso] = graph.correos_nuevos
    mensaje = aviso["message"]
    assert mensaje["toRecipients"] == [{"emailAddress": {"address": "nueva@data.cr"}}]
    assert mensaje["subject"].startswith(f"[Ticket #{ticket.id}] Se le asignó el ticket #{ticket.id}")
    assert f"{APP_URL}/detalle.html?id={ticket.id}" in mensaje["body"]["content"]
    assert {"name": "X-Ticketera", "value": "1"} in mensaje["internetMessageHeaders"]


@pytest.mark.parametrize("modo", MODOS)
def test_sent_thank_you_creates_nothing(modo, entorno, factory, session, gente):
    graph = FakeGraph([], enviados=[crear_enviado(asunto="Gracias por el informe", cuerpo="Saludos.")])
    revisar(modo, factory, graph, entorno)
    assert session.scalars(select(Ticket)).all() == []
    assert graph.correos_nuevos == []


@pytest.mark.parametrize("modo", MODOS)
def test_sent_ticket_prefix_always_creates_without_the_prefix(modo, entorno, factory, session, gente):
    graph = FakeGraph([], enviados=[crear_enviado(asunto="Ticket: algo", cuerpo="Cuando pueda.")])
    revisar(modo, factory, graph, entorno)
    assert session.scalars(select(Ticket)).one().title == "algo"


@pytest.mark.parametrize("modo", MODOS)
def test_assignee_reply_to_the_assignment_notice_is_a_comment(modo, entorno, factory, session, gente):
    graph = FakeGraph([], enviados=[crear_enviado(asunto="Ticket: Cambiar el tóner", cuerpo="Cuando pueda.")])
    revisar(modo, factory, graph, entorno)
    asunto = graph.correos_nuevos[0]["message"]["subject"]

    agregar(graph, crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas", asunto=f"RE: {asunto}",
                                cuerpo="Listo, ya lo cambié.", msg_id="<pedro-listo@data.cr>"))
    revisar(modo, factory, graph, entorno)
    assert [c.content for c in session.scalars(select(Comment))] == ["Listo, ya lo cambié."]
    assert len(session.scalars(select(Ticket)).all()) == 1


# --- Comentarios por correo ---------------------------------------------------------


def ticket_de_ana(modo, entorno, factory, graph):  # noqa: F811
    """Ana escribe al buzón con Juan en copia → ticket de Ana asignado a mí."""
    original = crear_correo(remitente="ana@data.cr", asunto="No me funciona la impresora",
                            msg_id="<ana-original@data.cr>")
    original["ccRecipients"] = [{"emailAddress": {"address": "juan@data.cr", "name": "Juan Solís"}}]
    agregar(graph, original)
    revisar(modo, factory, graph, entorno)


@pytest.mark.parametrize("modo", MODOS)
def test_reply_in_thread_from_someone_in_cc_with_account_is_a_comment(modo, entorno, factory, session, gente):
    graph = FakeGraph([])
    ticket_de_ana(modo, entorno, factory, graph)
    ticket = session.scalars(select(Ticket)).one()

    agregar(graph, crear_correo(remitente="juan@data.cr", nombre="Juan Solís", asunto="RE: No me funciona la impresora",
                                cuerpo="Yo también lo vi esta mañana.", msg_id="<juan1@data.cr>",
                                cabeceras={"In-Reply-To": "<ana-original@data.cr>"}))
    revisar(modo, factory, graph, entorno)

    [comentario] = session.scalars(select(Comment)).all()
    assert (comentario.ticket_id, comentario.author, comentario.content) == (
        ticket.id, "Juan Solís", "Yo también lo vi esta mañana.")
    assert len(session.scalars(select(Ticket)).all()) == 1
    # Un comentario que llega por correo no manda el aviso de comentarios.
    assert graph.correos_nuevos == []


def test_cc_parsed_from_graph():
    mensaje = crear_correo()
    mensaje["ccRecipients"] = [{"emailAddress": {"address": "Juan@Data.cr", "name": "Juan"}}]
    assert cs.correo_desde_graph(mensaje).cc == [("juan@data.cr", "Juan")]
    assert "ccRecipients" in cs._SELECT_MENSAJE


@pytest.mark.parametrize("modo", MODOS)
def test_reply_in_thread_without_account_is_ignored_and_logged(modo, entorno, factory, session, gente, caplog):
    entorno.setattr(cs.logger, "propagate", True)
    caplog.set_level("INFO", logger=cs.logger.name)
    graph = FakeGraph([])
    ticket_de_ana(modo, entorno, factory, graph)

    agregar(graph, crear_correo(remitente="luis@data.cr", asunto="RE: No me funciona la impresora",
                                cuerpo="Aquí tampoco funciona.", msg_id="<luis-hilo@data.cr>",
                                cabeceras={"In-Reply-To": "<ana-original@data.cr>"}))
    revisar(modo, factory, graph, entorno)

    assert session.scalars(select(Comment)).all() == []
    assert usuario(session, "luis@data.cr") is None
    assert len(graph.respuestas) == 1  # solo la confirmación a Ana: a Luis, nada
    assert "Comentario ignorado: luis@data.cr no tiene cuenta en la ticketera" in caplog.text


def test_ticket_number_alone_does_not_let_others_comment(session, gente):
    config = cs.ConfigCorreo(usuario=YO, app_url=APP_URL, dominio_empresa="data.cr")
    cs.procesar_correo(session, cs.correo_desde_graph(
        crear_correo(remitente="ana@data.cr", asunto="No me funciona la impresora")), config)
    ticket = session.scalars(select(Ticket)).one()
    ajeno = crear_correo(remitente="juan@data.cr", asunto=f"[Ticket #{ticket.id}] una nota",
                         cuerpo="Cuando pueda.", msg_id="<juan-numero@data.cr>")
    assert cs.procesar_correo(session, cs.correo_desde_graph(ajeno), config)[0] == "ignorado"
    assert session.scalars(select(Comment)).all() == []


def test_owner_can_comment_in_a_thread_where_it_does_not_participate(session, gente):
    """La dueña del buzón responde en el hilo de un ticket entre Ana y Pedro."""
    config = cs.ConfigCorreo(usuario=YO, app_url=APP_URL, dominio_empresa="data.cr")
    ticket = Ticket(title="Ajeno", description="x", category="Red", priority="Baja",
                    created_by_id=gente["ana"].id, assigned_to_id=gente["pedro"].id)
    session.add(ticket)
    session.commit()
    session.add(ProcessedEmail(message_id="<hilo-ajeno@data.cr>", result="ticket", ticket_id=ticket.id))
    session.commit()
    mia = crear_enviado(asunto="RE: Ajeno", cuerpo="Lo reviso yo.", en_respuesta_a="<hilo-ajeno@data.cr>")
    assert cs.procesar_enviado(session, cs.correo_desde_graph(mia), config) == ("comentario", None)


@pytest.mark.parametrize("modo", MODOS)
def test_app_notice_to_my_own_mailbox_stays_in_the_inbox(modo, entorno, factory, session, gente):
    propio = crear_correo(remitente=YO, asunto="[Ticket #1] Nuevo comentario en el ticket #1",
                          cabeceras={"X-Ticketera": "1"}, msg_id="<propio@data.cr>")
    graph = FakeGraph([propio])
    revisar(modo, factory, graph, entorno)
    assert [m["id"] for m in graph.no_leidos()] == [propio["id"]]  # sin leer, en la bandeja
    assert session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<propio@data.cr>")) is None


# --- Comentarios desde la app --------------------------------------------------------


def preparar(client, session):
    yo = login_as(client, session, "Administrador", YO, "Kristin Castro")
    ana = User(name="Ana Pérez", email="ana@data.cr", role="Solicitante")
    pedro = User(name="Pedro Rojas", email="pedro@data.cr", role="Técnico")
    session.add_all([ana, pedro])
    session.commit()
    ticket = Ticket(title="La impresora no imprime", description="x", category="Hardware", priority="Media",
                    created_by_id=ana.id, assigned_to_id=pedro.id)
    session.add(ticket)
    session.commit()
    return yo, ticket


def comentar(client, headers, ticket, texto="Ya pedí el repuesto."):
    return client.post(f"/api/tickets/{ticket.id}/comments", json={"content": texto}, headers=headers)


def graph_falso(entorno):
    graph = FakeGraph([])
    entorno.setattr(cs, "crear_cliente", lambda config, fabrica: graph.cliente)
    return graph


@pytest.mark.parametrize("modo", MODOS)
def test_app_comment_notifies_requester_and_assignee(modo, client, session, entorno):
    entorno.setenv("CORREO_MODO", modo)
    graph = graph_falso(entorno)
    headers, ticket = preparar(client, session)

    resp = comentar(client, headers, ticket)
    assert resp.status_code == 201, resp.text

    para = [c["message"]["toRecipients"][0]["emailAddress"]["address"] for c in graph.correos_nuevos]
    assert sorted(para) == ["ana@data.cr", "pedro@data.cr"]  # no a quien comentó
    for correo in graph.correos_nuevos:
        mensaje = correo["message"]
        assert mensaje["subject"] == f"[Ticket #{ticket.id}] Nuevo comentario en el ticket #{ticket.id}"
        texto = mensaje["body"]["content"]
        assert "Kristin Castro agregó un comentario" in texto and "Ya pedí el repuesto." in texto
        assert f"{APP_URL}/detalle.html?id={ticket.id}" in texto
        assert {"name": "X-Auto-Response-Suppress", "value": "All"} in mensaje["internetMessageHeaders"]
        assert {"name": "X-Ticketera", "value": "1"} in mensaje["internetMessageHeaders"]


def test_app_comment_by_the_requester_only_notifies_the_assignee(client, session, entorno):
    graph = graph_falso(entorno)
    _, ticket = preparar(client, session)
    ana = login_as(client, session, "Solicitante", "ana2@data.cr", "Ana Dos")
    ticket.created_by_id = usuario(session, "ana2@data.cr").id
    session.commit()

    assert comentar(client, ana, ticket).status_code == 201
    para = [c["message"]["toRecipients"][0]["emailAddress"]["address"] for c in graph.correos_nuevos]
    assert para == ["pedro@data.cr"]


def test_app_comment_without_avisar_comentarios_sends_nothing(client, session, entorno):
    entorno.setenv("AVISAR_COMENTARIOS", "false")
    graph = graph_falso(entorno)
    headers, ticket = preparar(client, session)
    assert comentar(client, headers, ticket).status_code == 201
    assert graph.correos_nuevos == []


def test_app_comment_is_saved_even_if_the_mail_fails(client, session, entorno, caplog):
    entorno.setattr(cs.logger, "propagate", True)
    graph = graph_falso(entorno)

    def falla(respuesta):
        raise cs.ErrorGraph("POST /me/sendMail → 500: caído")

    graph.cliente.enviar = falla
    headers, ticket = preparar(client, session)
    with caplog.at_level("ERROR", logger=cs.logger.name):
        resp = comentar(client, headers, ticket)
    assert resp.status_code == 201
    assert [c.content for c in session.scalars(select(Comment))] == ["Ya pedí el repuesto."]
    assert f"No se pudo avisar por correo el comentario del ticket #{ticket.id}" in caplog.text


@pytest.mark.parametrize("modo", MODOS)
def test_mail_comment_does_not_send_the_comment_notice(modo, entorno, factory, session, gente):
    graph = FakeGraph([])
    entorno.setattr(cs, "crear_cliente", lambda config, fabrica: graph.cliente)
    ticket_de_ana(modo, entorno, factory, graph)
    agregar(graph, crear_correo(remitente="ana@data.cr", asunto="RE: No me funciona la impresora",
                                cuerpo="Sigue igual.", msg_id="<ana2@data.cr>",
                                cabeceras={"In-Reply-To": "<ana-original@data.cr>"}))
    revisar(modo, factory, graph, entorno)
    assert [c.content for c in session.scalars(select(Comment))] == ["Sigue igual."]
    assert graph.correos_nuevos == []


def test_avisar_comentarios_default_depends_on_vercel():
    base = {"CORREO_ACTIVO": "1", "CORREO_USUARIO": YO}
    assert cs.config_desde_entorno(base).avisar_comentarios is False
    assert cs.config_desde_entorno({**base, "VERCEL": "1"}).avisar_comentarios is True
    assert cs.config_desde_entorno({**base, "VERCEL": "1", "AVISAR_COMENTARIOS": "false"}
                                   ).avisar_comentarios is False
    assert cs.config_desde_entorno({**base, "AVISAR_COMENTARIOS": "true"}).avisar_comentarios is True
