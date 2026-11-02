"""Reglas de integridad de los tickets.

1. Editar (título, descripción, categoría, prioridad): quien lo creó, solo
   mientras está «Nuevo»; el Administrador, en cualquier estado salvo
   «Cerrado»; nadie más (403 con el motivo). Cada cambio queda en el historial.
2. Un ticket Cerrado es de solo lectura para todos, también para el
   Administrador: no se edita, no se reasigna, no se comenta, no se elimina y
   no cambia de estado (409 «El ticket #N está Cerrado y no admite cambios.»).
   Una respuesta por correo a un ticket Cerrado no se agrega como comentario:
   se responde una sola vez que envíe un correo nuevo y queda en el log.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from backend.models import Comment, History, ProcessedEmail, Ticket, User
from backend.services import asistente_service as asis
from backend.services import correo_service as cs
from backend.services import ticket_service
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401
from backend.tests.test_correo import CONFIG, FakeGraph, crear_correo, procesar

AYUDA = Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html"
CERRADO = "El ticket #{id} está Cerrado y no admite cambios."


def entrar(client, session, rol, email):
    headers = login_as(client, session, rol, email, f"Persona {rol}")
    usuario = session.scalars(select(User).where(User.email == email)).one()
    return headers, usuario


@pytest.fixture
def personas(client, session):
    """Un Administrador, un Técnico y una Solicitante (cada uno con su token)."""
    return {
        "admin": entrar(client, session, "Administrador", "admin@data.cr"),
        "tecnico": entrar(client, session, "Técnico", "tecnico@data.cr"),
        "solicitante": entrar(client, session, "Solicitante", "sol@data.cr"),
    }


def nuevo_ticket(session, creador: User, estado="Nuevo", asignado: User | None = None) -> Ticket:
    ticket = Ticket(title="Impresora sin conexión", description="La impresora del piso 2 no responde.",
                    category="Hardware", priority="Media", state=estado, created_by_id=creador.id,
                    assigned_to_id=asignado.id if asignado else None)
    session.add(ticket)
    session.commit()
    return ticket


def editar(client, headers, ticket_id, **datos):
    return client.patch(f"/api/tickets/{ticket_id}", headers=headers,
                        json=datos or {"title": "Impresora del piso 2 sin conexión"})


# --- 1. Quién edita -------------------------------------------------------------


def test_creator_edits_while_new_and_it_is_in_history(client, session, personas):
    headers, sol = personas["solicitante"]
    ticket = nuevo_ticket(session, sol)

    resp = editar(client, headers, ticket.id, title="Impresora del piso 2 sin conexión", priority="Alta")

    assert resp.status_code == 200, resp.text
    assert resp.json()["priority"] == "Alta"
    cambios = session.scalars(select(History).where(
        History.ticket_id == ticket.id, History.action == "updated")).all()
    assert {(h.field, h.old_value, h.new_value, h.author_id) for h in cambios} == {
        ("title", "Impresora sin conexión", "Impresora del piso 2 sin conexión", sol.id),
        ("priority", "Media", "Alta", sol.id),
    }
    assert all(h.created_at is not None for h in cambios)


def test_technician_creator_also_edits_while_new(client, session, personas):
    headers, tecnico = personas["tecnico"]
    ticket = nuevo_ticket(session, tecnico)
    assert editar(client, headers, ticket.id).status_code == 200


@pytest.mark.parametrize("estado", ["En proceso", "Resuelto"])
def test_creator_cannot_edit_after_new(client, session, personas, estado):
    headers, sol = personas["solicitante"]
    ticket = nuevo_ticket(session, sol, estado=estado)

    resp = editar(client, headers, ticket.id)

    assert resp.status_code == 403
    assert resp.json()["detail"] == (
        f"Solo puede editar el ticket mientras está «Nuevo»; ahora está «{estado}». "
        "Pídale el cambio a un Administrador.")
    assert session.get(Ticket, ticket.id).title == "Impresora sin conexión"


@pytest.mark.parametrize("estado", ["Nuevo", "En proceso", "Resuelto"])
def test_admin_edits_in_any_state_but_closed(client, session, personas, estado):
    headers, _ = personas["admin"]
    _, sol = personas["solicitante"]
    ticket = nuevo_ticket(session, sol, estado=estado)

    resp = editar(client, headers, ticket.id)

    assert resp.status_code == 200, resp.text
    assert session.scalars(select(History).where(
        History.ticket_id == ticket.id, History.field == "title")).one().author == "Persona Administrador"


def test_technician_who_did_not_create_it_cannot_edit(client, session, personas):
    headers, tecnico = personas["tecnico"]
    _, sol = personas["solicitante"]
    # Aunque lo tenga asignado y esté «Nuevo».
    ticket = nuevo_ticket(session, sol, asignado=tecnico)

    resp = editar(client, headers, ticket.id)

    assert resp.status_code == 403
    assert resp.json()["detail"] == (
        "Solo quien creó el ticket (mientras está «Nuevo») o un Administrador pueden editarlo.")


def test_requester_who_did_not_create_it_cannot_edit(client, session, personas):
    headers, sol = personas["solicitante"]
    _, tecnico = personas["tecnico"]
    # Lo tiene asignado (lo ve), pero no lo creó.
    ticket = nuevo_ticket(session, tecnico, asignado=sol)
    assert editar(client, headers, ticket.id).status_code == 403
    # Uno ajeno que no ve: no existe para ella.
    ajeno = nuevo_ticket(session, tecnico)
    assert editar(client, headers, ajeno.id).status_code == 404


# --- 2. Cerrado: solo lectura para todos ----------------------------------------


def _accion_en_cerrado(client, headers, ticket_id, accion, otro_id):
    if accion == "editar":
        return editar(client, headers, ticket_id)
    if accion == "asignar":
        return client.patch(f"/api/tickets/{ticket_id}/assign", headers=headers,
                            json={"assigned_to_id": otro_id})
    if accion == "comentar":
        return client.post(f"/api/tickets/{ticket_id}/comments", headers=headers,
                           json={"content": "¿Alguna novedad?"})
    if accion == "eliminar":
        return client.delete(f"/api/tickets/{ticket_id}", headers=headers)
    if accion == "estado":
        return client.patch(f"/api/tickets/{ticket_id}/state", headers=headers,
                            json={"state": "En proceso", "motivo": "Volvió a fallar"})
    raise AssertionError(accion)


@pytest.mark.parametrize("accion", ["editar", "asignar", "comentar", "eliminar", "estado"])
def test_closed_ticket_rejects_everything_even_for_the_admin(client, session, personas, accion):
    headers, admin = personas["admin"]
    _, tecnico = personas["tecnico"]
    ticket = nuevo_ticket(session, admin, estado="Cerrado")
    historial_antes = len(session.scalars(select(History).where(History.ticket_id == ticket.id)).all())

    resp = _accion_en_cerrado(client, headers, ticket.id, accion, tecnico.id)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == CERRADO.format(id=ticket.id)
    session.expire_all()
    guardado = session.get(Ticket, ticket.id)
    assert guardado is not None and guardado.state == "Cerrado"
    assert guardado.title == "Impresora sin conexión" and guardado.assigned_to_id is None
    assert session.scalars(select(Comment)).all() == []
    assert len(session.scalars(select(History).where(History.ticket_id == ticket.id)).all()) == historial_antes


@pytest.mark.parametrize("accion", ["editar", "comentar", "estado"])
def test_closed_ticket_rejects_its_creator_and_assignee(client, session, personas, accion):
    headers_sol, sol = personas["solicitante"]
    headers_tec, tecnico = personas["tecnico"]
    ticket = nuevo_ticket(session, sol, estado="Cerrado", asignado=tecnico)
    for headers in (headers_sol, headers_tec):
        resp = _accion_en_cerrado(client, headers, ticket.id, accion, tecnico.id)
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == CERRADO.format(id=ticket.id)


def test_closing_is_the_last_change(client, session, personas):
    headers, admin = personas["admin"]
    ticket = nuevo_ticket(session, admin)
    assert client.patch(f"/api/tickets/{ticket.id}/state", headers=headers,
                        json={"state": "Cerrado"}).status_code == 200
    assert editar(client, headers, ticket.id).status_code == 409


def test_services_also_refuse_closed_tickets(session, personas):
    """El chat y el correo usan los mismos servicios: tampoco pasan."""
    _, admin = personas["admin"]
    ticket = nuevo_ticket(session, admin, estado="Cerrado")
    for llamada in (
        lambda: ticket_service.assign_ticket(session, ticket.id, admin.id, admin),
        lambda: ticket_service.delete_ticket(session, ticket.id, admin),
    ):
        with pytest.raises(ticket_service.TicketClosedError):
            llamada()


# --- Correo: respuesta a un ticket Cerrado --------------------------------------


@pytest.fixture
def ana(session):
    user = User(name="Ana Pérez", email="ana@data.cr", role="Solicitante", password_hash="x", is_active=True)
    session.add(user)
    session.commit()
    return user


def test_mail_reply_to_closed_ticket_gets_a_notice_and_no_comment(session, ana, caplog, monkeypatch):
    monkeypatch.setattr(cs.logger, "propagate", True)
    caplog.set_level("INFO", logger=cs.logger.name)
    ticket = nuevo_ticket(session, ana, estado="Cerrado")
    mensaje = crear_correo(asunto=f"RE: Ticket #{ticket.id} creado: Impresora", cuerpo="Sigue sin imprimir.",
                           msg_id="<cerrado1@data.cr>")

    resultado, respuesta = procesar(session, mensaje)

    assert resultado == "cerrado"
    assert session.scalars(select(Comment)).all() == []
    assert respuesta.para == "ana@data.cr"
    assert respuesta.asunto == f"Ticket #{ticket.id} cerrado"
    assert (f"El ticket #{ticket.id} está cerrado. Si el problema continúa, envíe un nuevo correo "
            "para crear otro ticket.") in respuesta.texto
    registro = session.scalars(select(ProcessedEmail)).one()
    assert (registro.result, registro.ticket_id) == ("cerrado", ticket.id)
    assert f"el ticket #{ticket.id} está Cerrado" in caplog.text

    # Una sola vez: el mismo correo no se responde de nuevo.
    assert procesar(session, mensaje) == ("repetido", None)


def test_closed_notice_is_recognized_as_an_app_mail(session, ana):
    """Si alguien responde al aviso «Ticket #N cerrado», no se procesa otra vez
    (ni comentario ni ticket nuevo): es un aviso de la app."""
    ticket = nuevo_ticket(session, ana, estado="Cerrado")
    resultado, _ = procesar(session, crear_correo(asunto=f"RE: Ticket #{ticket.id} cerrado",
                                                   cuerpo="Ok, gracias.", msg_id="<cerrado2@data.cr>"))
    assert resultado == "ignorado"
    assert len(session.scalars(select(Ticket)).all()) == 1
    assert session.scalars(select(Comment)).all() == []


def test_mailbox_review_sends_the_closed_notice_in_the_thread(engine, session, ana):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    ticket = nuevo_ticket(session, ana, estado="Cerrado")
    mensaje = crear_correo(asunto=f"RE: Ticket #{ticket.id} creado: Impresora", cuerpo="Sigue igual.",
                           msg_id="<cerrado3@data.cr>")
    graph = FakeGraph([mensaje])

    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"cerrado": 1}

    [(respondido, enviado)] = graph.respuestas
    assert respondido == mensaje["id"]
    assert enviado["message"]["subject"] == f"Ticket #{ticket.id} cerrado"
    assert session.scalars(select(Comment)).all() == []


# --- Ayuda y chat -------------------------------------------------------------


def test_help_page_explains_the_rules():
    html = AYUDA.read_text(encoding="utf-8")
    assert ("<tr><td>Editar ticket</td><td>Todos, salvo los Cerrados</td>"
            "<td>Los que creó, mientras están en Nuevo</td><td>Los que creó, mientras están en Nuevo</td></tr>") in html
    assert "Un ticket Cerrado es de solo lectura para todos, también para el Administrador" in html
    assert "El ticket #N está cerrado. Si el problema continúa, envíe un nuevo correo" in html


def test_role_texts_include_the_edit_rule():
    assert "editar tickets (todos, salvo los Cerrados)" in asis.PERMISOS_POR_ROL["Administrador"]
    for rol in ("Técnico", "Solicitante"):
        assert "editar tickets (los que creó, mientras están en Nuevo)" in asis.PERMISOS_POR_ROL[rol]
    assert asis.NOTA_CERRADO in asis.REGLAS_PARA_IA


@pytest.mark.parametrize("pregunta,regla", [
    ("¿quién puede editar un ticket?", "REGLA_QUIEN_EDITA"),
    ("¿se puede comentar un ticket cerrado?", "REGLA_CERRADO"),
    ("¿se puede editar un ticket cerrado?", "REGLA_CERRADO"),
])
def test_chat_answers_the_rules_without_ai(client, session, ia, pregunta, regla):
    headers = login_as(client, session, "Técnico", "tec2@data.cr", "Tec Dos")
    respuesta = _respuesta(ask(client, headers, pregunta), "directa")
    assert respuesta == getattr(asis, regla)
    assert ia.calls == []


def test_chat_says_a_closed_ticket_is_not_deleted(client, session, ia):
    headers = login_as(client, session, "Administrador", "adm3@data.cr", "Adm Tres")
    respuesta = _respuesta(ask(client, headers, "¿se puede eliminar un ticket cerrado?"), "directa")
    assert "Un ticket Cerrado no se elimina." in respuesta


def test_chat_edit_guide_depends_on_the_role(client, session, ia):
    sol = login_as(client, session, "Solicitante", "sol2@data.cr", "Sol Dos")
    admin = login_as(client, session, "Administrador", "adm2@data.cr", "Adm Dos")
    assert _respuesta(ask(client, sol, "¿cómo edito un ticket?"), "directa") == asis.GUIA_EDITAR_CREADOR
    assert "salvo los Cerrados" in _respuesta(ask(client, admin, "¿cómo edito un ticket?"), "directa")
