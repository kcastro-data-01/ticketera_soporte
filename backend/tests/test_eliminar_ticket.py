"""Eliminar tickets: solo el Administrador, con comentarios e historial."""

import logging

import pytest
from sqlalchemy import func, select

from backend.models import Comment, History, ProcessedEmail, Ticket
from backend.services import ticket_service
from backend.tests.test_access_control import headers, login_role


def crear_ticket(auth_client) -> int:
    resp = auth_client.post("/api/tickets", json={
        "title": "Impresora no imprime", "description": "Marca error 49.",
        "category": "Hardware", "priority": "Alta",
    })
    assert resp.status_code == 201
    ticket_id = resp.json()["id"]
    assert auth_client.post(f"/api/tickets/{ticket_id}/comments",
                            json={"content": "Ya cambié el tóner"}).status_code == 201
    return ticket_id


def contar(session, modelo, ticket_id):
    return session.scalar(select(func.count()).select_from(modelo).where(modelo.ticket_id == ticket_id))


def test_admin_deletes_ticket_with_comments_and_history(auth_client, session):
    ticket_id = crear_ticket(auth_client)
    otro_id = crear_ticket(auth_client)
    assert contar(session, Comment, ticket_id) == 1
    assert contar(session, History, ticket_id) >= 2

    resp = auth_client.delete(f"/api/tickets/{ticket_id}")
    assert resp.status_code == 204
    assert resp.content == b""

    session.expire_all()
    assert auth_client.get(f"/api/tickets/{ticket_id}").status_code == 404
    assert contar(session, Comment, ticket_id) == 0
    assert contar(session, History, ticket_id) == 0
    # Los demás tickets no se tocan.
    assert auth_client.get(f"/api/tickets/{otro_id}").status_code == 200
    assert contar(session, Comment, otro_id) == 1


def test_deleting_keeps_processed_email_record_without_ticket(auth_client, session):
    ticket_id = crear_ticket(auth_client)
    session.add(ProcessedEmail(message_id="<m1@data.cr>", sender="ana@data.cr",
                               result="ticket", ticket_id=ticket_id))
    session.commit()

    assert auth_client.delete(f"/api/tickets/{ticket_id}").status_code == 204
    session.expire_all()
    registro = session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<m1@data.cr>"))
    assert registro is not None  # ese correo nunca vuelve a crear un ticket
    assert registro.ticket_id is None


@pytest.mark.parametrize("rol,correo", [
    ("Supervisor", "sup@test.local"),
    ("Técnico", "tec@test.local"),
    ("Solicitante", "soli@test.local"),
])
def test_other_roles_get_403(client, auth_client, session, rol, correo):
    ticket_id = crear_ticket(auth_client)
    token = login_role(client, session, rol, correo)
    resp = client.delete(f"/api/tickets/{ticket_id}", headers=headers(token))
    assert resp.status_code == 403
    assert auth_client.get(f"/api/tickets/{ticket_id}").status_code == 200


def test_missing_ticket_returns_404(auth_client):
    resp = auth_client.delete("/api/tickets/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Ticket 9999 no encontrado"


def test_delete_requires_login(client, auth_client):
    ticket_id = crear_ticket(auth_client)
    assert client.delete(f"/api/tickets/{ticket_id}").status_code == 401


def test_deletion_is_logged_with_who_and_when(auth_client, caplog, monkeypatch):
    ticket_id = crear_ticket(auth_client)
    monkeypatch.setattr(ticket_service.logger, "propagate", True)
    with caplog.at_level(logging.INFO, logger=ticket_service.logger.name):
        assert auth_client.delete(f"/api/tickets/{ticket_id}").status_code == 204
    assert (f"Test Admin (testadmin@test.com, id 1) eliminó el ticket #{ticket_id} "
            "«Impresora no imprime» el ") in caplog.text
    assert "UTC" in caplog.text


def test_failed_delete_rolls_back_everything(auth_client, session, monkeypatch):
    ticket_id = crear_ticket(auth_client)
    user = session.get(ticket_service.User, 1)
    original_commit = session.commit

    def falla():
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(session, "commit", falla)
    with pytest.raises(RuntimeError):
        ticket_service.delete_ticket(session, ticket_id, user)
    monkeypatch.setattr(session, "commit", original_commit)
    session.expire_all()
    assert session.get(Ticket, ticket_id) is not None
    assert contar(session, Comment, ticket_id) == 1
