"""Un Solicitante (u otro rol) con tickets ASIGNADOS a él, por ejemplo los
que le llegan desde un correo: los ve en su lista y en el detalle, los
comenta y les cambia el estado; no los edita, reasigna ni borra. Los tickets
ajenos siguen ocultos (404)."""

import pytest
from sqlalchemy import select

from backend.models import Ticket, User
from backend.services import asistente_service, ticket_service
from backend.tests.test_asistente import login_as


@pytest.fixture
def escenario(client, session):
    """Pedro (Solicitante) con un ticket asignado, uno propio y uno ajeno."""
    cabeceras = login_as(client, session, "Solicitante", "pedro@data.cr", "Pedro Rojas")
    pedro = session.scalar(select(User).where(User.email == "pedro@data.cr"))
    kristin = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador")
    session.add(kristin)
    session.commit()

    def nuevo(titulo, creador, asignado=None):
        ticket = Ticket(title=titulo, description="Descripción del caso", category="Hardware",
                        priority="Media", created_by_id=creador.id,
                        assigned_to_id=asignado.id if asignado else None)
        session.add(ticket)
        session.commit()
        return ticket

    asignado = nuevo("Impresora del segundo piso", kristin, asignado=pedro)
    propio = nuevo("Mi monitor parpadea", pedro)
    ajeno = nuevo("Servidor caído", kristin, asignado=kristin)
    return cabeceras, pedro, asignado, propio, ajeno


def test_list_and_detail_include_assigned_and_own_but_not_others(client, escenario):
    cabeceras, _, asignado, propio, ajeno = escenario
    ids = {t["id"] for t in client.get("/api/tickets", headers=cabeceras).json()}
    assert ids == {asignado.id, propio.id}
    assert client.get(f"/api/tickets/{asignado.id}", headers=cabeceras).status_code == 200
    assert client.get(f"/api/tickets/{asignado.id}/history", headers=cabeceras).status_code == 200
    assert client.get(f"/api/tickets/{ajeno.id}", headers=cabeceras).status_code == 404
    mios = client.get("/api/tickets?mios=true", headers=cabeceras).json()
    assert [t["id"] for t in mios] == [asignado.id]


def test_comment_on_assigned_ticket(client, escenario):
    cabeceras, _, asignado, _, ajeno = escenario
    resp = client.post(f"/api/tickets/{asignado.id}/comments", json={"content": "Ya la revisé."},
                       headers=cabeceras)
    assert resp.status_code == 201, resp.text
    assert client.post(f"/api/tickets/{ajeno.id}/comments", json={"content": "Hola"},
                       headers=cabeceras).status_code == 404


def test_assignee_changes_state_only_of_assigned_tickets(client, escenario):
    cabeceras, _, asignado, propio, ajeno = escenario
    resp = client.patch(f"/api/tickets/{asignado.id}/state", json={"state": "En proceso"}, headers=cabeceras)
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "En proceso"
    # El flujo sigue siendo el mismo: no puede saltar estados.
    assert client.patch(f"/api/tickets/{asignado.id}/state", json={"state": "Cerrado"},
                        headers=cabeceras).status_code == 409
    # El suyo que no tiene asignado: no; el ajeno: no existe para él.
    assert client.patch(f"/api/tickets/{propio.id}/state", json={"state": "En proceso"},
                        headers=cabeceras).status_code == 403
    assert client.patch(f"/api/tickets/{ajeno.id}/state", json={"state": "En proceso"},
                        headers=cabeceras).status_code == 404


def test_assignee_cannot_edit_reassign_or_delete(client, escenario):
    cabeceras, pedro, asignado, _, _ = escenario
    assert client.patch(f"/api/tickets/{asignado.id}", json={"title": "Otro título"},
                        headers=cabeceras).status_code == 403
    assert client.patch(f"/api/tickets/{asignado.id}/assign", json={"assigned_to_id": None},
                        headers=cabeceras).status_code == 403
    assert client.delete(f"/api/tickets/{asignado.id}", headers=cabeceras).status_code == 403
    assert client.get("/api/history", headers=cabeceras).status_code == 403
    assert client.get("/api/metricas", headers=cabeceras).status_code == 403


def test_assignee_with_another_role_changes_state_of_any_ticket(client, session):
    """El permiso del rol no cambia: el Técnico cambia el estado de cualquiera."""
    cabeceras = login_as(client, session, "Técnico", "tec@data.cr", "Técnico Uno")
    ticket = Ticket(title="Proyector", description="No enciende", category="Hardware", priority="Baja")
    session.add(ticket)
    session.commit()
    assert client.patch(f"/api/tickets/{ticket.id}/state", json={"state": "En proceso"},
                        headers=cabeceras).status_code == 200


def test_dashboard_counts_include_assigned_tickets(client, escenario):
    cabeceras, _, _, _, _ = escenario
    resumen = client.get("/api/tickets/summary", headers=cabeceras).json()
    assert resumen["total"] == 2
    assert resumen["mios_abiertos"] == 1


def test_chat_sees_assigned_tickets(client, session, escenario):
    cabeceras, pedro, asignado, _, ajeno = escenario
    base = asistente_service._base_visible(pedro)
    visibles = {t.id for t in session.scalars(base)}
    assert visibles == {asignado.id, escenario[3].id}
    datos = client.post("/api/asistente", headers=cabeceras, json={
        "messages": [{"role": "user", "content": f"explicame el ticket #{asignado.id}"}]}).json()
    assert "Impresora del segundo piso" in datos["respuesta"]
    datos = client.post("/api/asistente", headers=cabeceras, json={
        "messages": [{"role": "user", "content": f"explicame el ticket #{ajeno.id}"}]}).json()
    assert "Servidor caído" not in datos["respuesta"]


def test_visibility_rules(escenario):
    _, pedro, asignado, propio, ajeno = escenario
    assert ticket_service.can_view_ticket(asignado, pedro)
    assert ticket_service.can_view_ticket(propio, pedro)
    assert not ticket_service.can_view_ticket(ajeno, pedro)
    assert ticket_service.can_change_state(asignado, pedro)
    assert not ticket_service.can_change_state(propio, pedro)
