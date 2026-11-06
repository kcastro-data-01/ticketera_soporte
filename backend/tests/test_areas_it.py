"""Áreas de IT: tabla administrada por el Administrador, área obligatoria al
crear un ticket en la app, reparto al técnico del área con menos tickets
abiertos, «IT solo recibe» (nunca se asigna a un Solicitante), cambio de
área (Administrador y Técnico), filtros en la lista y en las métricas, y la
migración automática de una base de antes de las áreas."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text

from backend.auth import hash_password
from backend.constants import EXAMPLE_IT_AREAS
from backend.database import init_db
from backend.migrate_add_it_areas import migrate_it_areas
from backend.models import History, ItArea, Ticket, User
from backend.services import correo_service as cs
from backend.services import ticket_service
from backend.tests.test_correo import CONFIG, crear_correo

TICKET = {"title": "No funciona la VPN", "description": "No conecta desde la casa.",
          "category": "Red", "priority": "Media"}


def headers_de(client, session, role, email, name, area=None):
    user = User(name=name, email=email, role=role, password_hash=hash_password("clave12345"),
                area_id=area.id if area is not None else None)
    session.add(user)
    session.commit()
    token = client.post("/api/auth/login", json={"email": email, "password": "clave12345"}).json()
    return user, {"Authorization": f"Bearer {token['access_token']}"}


@pytest.fixture
def areas(session):
    filas = {n: ItArea(name=n) for n in ("Soporte técnico", "Redes", "Infraestructura")}
    session.add_all(filas.values())
    session.commit()
    return filas


def tecnico(session, nombre, area=None, activo=True):
    user = User(name=nombre, email=f"{nombre.lower()}@data.cr", role="Técnico",
                area_id=area.id if area is not None else None, is_active=activo)
    session.add(user)
    session.commit()
    return user


def ticket_abierto(session, asignado, estado="Nuevo", area=None):
    t = Ticket(title="Ticket de carga", description="Para contar", category="Red", priority="Baja",
               state=estado, assigned_to_id=asignado.id, area_id=area.id if area else None)
    session.add(t)
    session.commit()
    return t


# --- Migración ------------------------------------------------------------------


def test_migration_adds_areas_to_an_old_database_and_keeps_everything_sin_area(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120), "
                          "email VARCHAR(255), role VARCHAR(30), is_active BOOLEAN, password_hash VARCHAR(255))"))
        conn.execute(text("CREATE TABLE tickets (id INTEGER PRIMARY KEY, title VARCHAR(200), "
                          "description TEXT, category VARCHAR(30), priority VARCHAR(20), state VARCHAR(20), "
                          "assigned_to_id INTEGER, created_by_id INTEGER, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'Pedro', 'pedro@data.cr', 'Técnico', 1, NULL), "
                          "(2, 'Sofía', 'sofia@data.cr', 'Solicitante', 1, NULL)"))
        ahora = datetime.now(timezone.utc)
        conn.execute(text("INSERT INTO tickets VALUES (1, 'Viejo', 'Desc', 'Red', 'Media', 'Nuevo', 2, 1, "
                          ":a, :a)"), {"a": ahora})
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM it_areas ORDER BY id")).scalars().all() == list(EXAMPLE_IT_AREAS)
        assert conn.execute(text("SELECT area_id FROM users")).scalars().all() == [None, None]
        # El ticket viejo asignado a un Solicitante queda como estaba, «Sin área».
        assert conn.execute(text("SELECT assigned_to_id, area_id FROM tickets")).one() == (2, None)
    engine.dispose()


def test_example_areas_are_loaded_only_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nueva.db'}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE it_areas SET name = 'Mesa de ayuda' WHERE name = 'Soporte técnico'"))
        conn.execute(text("DELETE FROM it_areas WHERE name = 'Redes'"))
    init_db(engine)
    migrate_it_areas(engine)
    with engine.connect() as conn:
        nombres = conn.execute(text("SELECT name FROM it_areas ORDER BY id")).scalars().all()
    assert nombres == ["Mesa de ayuda", "Infraestructura", "Ciberseguridad"]
    engine.dispose()


# --- Administración de áreas ----------------------------------------------------


def test_admin_creates_renames_deactivates_and_reactivates(auth_client):
    creada = auth_client.post("/api/areas", json={"name": "  Mesa   de ayuda "})
    assert creada.status_code == 201, creada.text
    area = creada.json()
    assert (area["name"], area["is_active"], area["tecnicos"]) == ("Mesa de ayuda", True, 0)

    assert auth_client.post("/api/areas", json={"name": "MESA DE AYUDA"}).status_code == 409
    assert auth_client.post("/api/areas", json={"name": "x"}).status_code == 422

    renombrada = auth_client.patch(f"/api/areas/{area['id']}", json={"name": "Soporte en sitio"})
    assert renombrada.json()["name"] == "Soporte en sitio"
    assert auth_client.patch(f"/api/areas/{area['id']}", json={"is_active": False}).json()["is_active"] is False
    assert auth_client.get("/api/areas").json() == []
    todas = auth_client.get("/api/areas?todas=1").json()
    assert [(a["name"], a["is_active"]) for a in todas] == [("Soporte en sitio", False)]
    assert auth_client.patch(f"/api/areas/{area['id']}", json={"is_active": True}).json()["is_active"] is True
    assert auth_client.patch("/api/areas/999", json={"is_active": True}).status_code == 404


def test_area_listing_counts_active_technicians(auth_client, session, areas):
    tecnico(session, "Pedro", areas["Redes"])
    tecnico(session, "Luis", areas["Redes"], activo=False)
    lista = {a["name"]: a["tecnicos"] for a in auth_client.get("/api/areas").json()}
    assert lista == {"Infraestructura": 0, "Redes": 1, "Soporte técnico": 0}


@pytest.mark.parametrize("rol", ["Técnico", "Solicitante"])
def test_only_admin_manages_areas_but_everyone_lists_active_ones(client, session, areas, rol):
    _, h = headers_de(client, session, rol, "otro@data.cr", "Otro")
    assert client.post("/api/areas", json={"name": "Nueva"}, headers=h).status_code == 403
    assert client.patch(f"/api/areas/{areas['Redes'].id}", json={"is_active": False},
                        headers=h).status_code == 403
    assert client.get("/api/areas?todas=1", headers=h).status_code == 403
    assert len(client.get("/api/areas", headers=h).json()) == 3


# --- Crear ticket: área obligatoria y reparto ----------------------------------


def test_area_is_required_when_there_are_active_areas(auth_client, areas):
    resp = auth_client.post("/api/tickets", json=TICKET)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Elija el área de IT del ticket."


def test_inactive_or_unknown_area_is_rejected(auth_client, session, areas):
    areas["Redes"].is_active = False
    session.commit()
    assert auth_client.post("/api/tickets", json=TICKET | {"area_id": areas["Redes"].id}).status_code == 422
    assert auth_client.post("/api/tickets", json=TICKET | {"area_id": 999}).status_code == 422


def test_ticket_goes_to_the_area_technician_with_fewest_open_tickets(auth_client, session, areas):
    redes = areas["Redes"]
    pedro = tecnico(session, "Pedro", redes)
    luis = tecnico(session, "Luis", redes)
    tecnico(session, "Otro", areas["Infraestructura"])  # de otra área: no cuenta
    ticket_abierto(session, pedro)
    # Los cerrados y resueltos no cuentan: Luis tiene 2 pero ninguno abierto.
    ticket_abierto(session, luis, "Cerrado")
    ticket_abierto(session, luis, "Resuelto")
    resp = auth_client.post("/api/tickets", json=TICKET | {"area_id": redes.id})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert (data["assigned_to_id"], data["area_id"], data["area_name"]) == (luis.id, redes.id, "Redes")


def test_area_without_technicians_goes_to_any_technician_with_fewest(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    ana = tecnico(session, "Ana")  # sin área
    ticket_abierto(session, pedro)
    data = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas["Infraestructura"].id}).json()
    # El área es la que se eligió, aunque lo atienda alguien de otra.
    assert (data["assigned_to_id"], data["area_name"]) == (ana.id, "Infraestructura")


def test_without_technicians_the_ticket_stays_unassigned(auth_client, areas):
    data = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas["Redes"].id}).json()
    assert (data["assigned_to_id"], data["area_name"]) == (None, "Redes")


def test_requester_creates_a_ticket_with_area(client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    _, h = headers_de(client, session, "Solicitante", "sofia@data.cr", "Sofía")
    data = client.post("/api/tickets", json=TICKET | {"area_id": areas["Redes"].id}, headers=h).json()
    assert (data["assigned_to_id"], data["area_name"]) == (pedro.id, "Redes")


# --- IT solo recibe -------------------------------------------------------------


def test_a_ticket_can_not_be_assigned_to_a_requester(auth_client, session, areas):
    sofia = User(name="Sofía", email="sofia@data.cr", role="Solicitante")
    session.add(sofia)
    session.commit()
    ticket = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas["Redes"].id}).json()
    resp = auth_client.patch(f"/api/tickets/{ticket['id']}/assign", json={"assigned_to_id": sofia.id})
    assert resp.status_code == 422
    assert "Solicitante" in resp.json()["detail"]


def test_old_ticket_assigned_to_a_requester_can_be_reassigned(auth_client, session):
    sofia = User(name="Sofía", email="sofia@data.cr", role="Solicitante")
    session.add(sofia)
    session.commit()
    viejo = ticket_abierto(session, sofia)
    pedro = tecnico(session, "Pedro")
    resp = auth_client.patch(f"/api/tickets/{viejo.id}/assign", json={"assigned_to_id": pedro.id})
    assert resp.status_code == 200
    assert resp.json()["assigned_to_id"] == pedro.id


def test_inbox_ticket_takes_the_area_of_the_mailbox_owner(session, areas):
    duena = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador",
                 area_id=areas["Soporte técnico"].id)
    ana = User(name="Ana Pérez", email="ana@data.cr", role="Solicitante")
    session.add_all([duena, ana])
    session.commit()
    resultado, _ = cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    assert resultado == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    assert (ticket.assigned_to_id, ticket.area_id) == (duena.id, areas["Soporte técnico"].id)


def test_inbox_ticket_is_sin_area_when_the_owner_has_no_area(session):
    duena = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador")
    session.add_all([duena, User(name="Ana Pérez", email="ana@data.cr", role="Solicitante")])
    session.commit()
    cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    ticket = session.scalars(select(Ticket)).one()
    assert (ticket.assigned_to_id, ticket.area_id) == (duena.id, None)


def test_inbox_owner_who_is_a_requester_never_gets_the_ticket(session, caplog):
    session.add_all([User(name="Buzón", email="kcastro@data.cr", role="Solicitante"),
                     User(name="Ana Pérez", email="ana@data.cr", role="Solicitante")])
    session.commit()
    pedro = tecnico(session, "Pedro")
    with caplog.at_level("WARNING"):
        cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    assert session.scalars(select(Ticket)).one().assigned_to_id == pedro.id
    assert "no de IT" in caplog.text


def test_create_ticket_rejects_a_requester_as_assignee(session):
    sofia = User(name="Sofía", email="sofia@data.cr", role="Solicitante")
    session.add(sofia)
    session.commit()
    from backend.schemas import TicketCreate

    with pytest.raises(ticket_service.AssigneeNotITError):
        ticket_service.create_ticket(session, TicketCreate(**TICKET), None, asignado=sofia,
                                     requiere_area=False)


# --- Cambiar el área ------------------------------------------------------------


def test_technician_moves_the_ticket_to_another_area_and_it_is_in_the_history(client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    _, h = headers_de(client, session, "Técnico", "luis@data.cr", "Luis", areas["Infraestructura"])
    ticket = ticket_abierto(session, pedro, area=areas["Redes"])
    resp = client.patch(f"/api/tickets/{ticket.id}/area",
                        json={"area_id": areas["Infraestructura"].id}, headers=h)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["area_name"], resp.json()["assigned_to_id"]) == ("Infraestructura", pedro.id)
    entrada = session.scalars(select(History).where(History.action == "area_changed")).one()
    assert (entrada.field, entrada.old_value, entrada.new_value, entrada.author) == (
        "area", "Redes", "Infraestructura", "Luis")
    historial = client.get(f"/api/tickets/{ticket.id}/history", headers=h).json()
    assert historial[-1]["action"] == "area_changed"


def test_changing_the_area_with_reassign_goes_to_the_new_area_technician(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    marta = tecnico(session, "Marta", areas["Infraestructura"])
    ticket = ticket_abierto(session, pedro, area=areas["Redes"])
    resp = auth_client.patch(f"/api/tickets/{ticket.id}/area",
                             json={"area_id": areas["Infraestructura"].id, "reasignar": True})
    assert resp.json()["assigned_to_id"] == marta.id
    acciones = session.scalars(select(History.action).where(History.ticket_id == ticket.id)
                               .order_by(History.id)).all()
    assert acciones == ["area_changed", "assigned"]


def test_sin_area_ticket_gets_an_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    ticket = ticket_abierto(session, pedro)
    auth_client.patch(f"/api/tickets/{ticket.id}/area", json={"area_id": areas["Redes"].id})
    entrada = session.scalars(select(History).where(History.action == "area_changed")).one()
    assert (entrada.old_value, entrada.new_value) == (None, "Redes")


def test_area_change_rules(client, auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    ticket = ticket_abierto(session, pedro, area=areas["Redes"])
    _, sol = headers_de(client, session, "Solicitante", "sofia@data.cr", "Sofía")
    url = f"/api/tickets/{ticket.id}/area"
    assert client.patch(url, json={"area_id": areas["Infraestructura"].id}, headers=sol).status_code == 403
    areas["Infraestructura"].is_active = False
    session.commit()
    assert auth_client.patch(url, json={"area_id": areas["Infraestructura"].id}).status_code == 422
    assert auth_client.patch(url, json={"area_id": 999}).status_code == 404
    ticket.state = "Cerrado"
    session.commit()
    assert auth_client.patch(url, json={"area_id": areas["Soporte técnico"].id}).status_code == 409


# --- Usuarios -------------------------------------------------------------------


def test_admin_assigns_an_area_to_a_technician_and_to_themself(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"area_id": areas["Redes"].id})
    assert (resp.json()["area_id"], resp.json()["area_name"]) == (areas["Redes"].id, "Redes")
    yo = auth_client.get("/api/auth/me").json()
    assert auth_client.patch(f"/api/users/{yo['id']}", json={"area_id": areas["Soporte técnico"].id}
                             ).json()["area_name"] == "Soporte técnico"
    # null quita el área.
    assert auth_client.patch(f"/api/users/{pedro.id}", json={"area_id": None}).json()["area_id"] is None


def test_a_requester_has_no_area(auth_client, session, areas):
    resp = auth_client.post("/api/users", json={"name": "Sofía", "email": "sofia@data.cr",
                                                 "role": "Solicitante", "area_id": areas["Redes"].id})
    assert resp.status_code == 422
    creado = auth_client.post("/api/users", json={"name": "Pedro", "email": "pedro@data.cr",
                                                   "role": "Técnico", "area_id": areas["Redes"].id})
    assert creado.json()["area_name"] == "Redes"


def test_demoting_to_requester_clears_the_area_and_needs_no_open_tickets(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    abierto = ticket_abierto(session, pedro)
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"role": "Solicitante"})
    assert resp.status_code == 409
    assert "1 ticket abierto" in resp.json()["detail"]
    abierto.state = "Cerrado"
    session.commit()
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"role": "Solicitante"})
    assert resp.status_code == 200
    assert (resp.json()["role"], resp.json()["area_id"]) == ("Solicitante", None)


def test_a_technician_keeps_an_area_that_was_deactivated(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas["Redes"])
    areas["Redes"].is_active = False
    session.commit()
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"name": "Pedro R.", "area_id": areas["Redes"].id})
    assert resp.status_code == 200
    assert resp.json()["area_name"] == "Redes"
    otro = tecnico(session, "Luis")
    assert auth_client.patch(f"/api/users/{otro.id}", json={"area_id": areas["Redes"].id}).status_code == 422


# --- Filtros ---------------------------------------------------------------------


def test_list_filters_by_area_and_sin_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    en_redes = ticket_abierto(session, pedro, area=areas["Redes"])
    sin = ticket_abierto(session, pedro)
    assert [t["id"] for t in auth_client.get(f"/api/tickets?area={areas['Redes'].id}").json()] == [en_redes.id]
    assert [t["id"] for t in auth_client.get("/api/tickets?sin_area=true").json()] == [sin.id]
    assert auth_client.get(f"/api/tickets?area={areas['Redes'].id}&sin_area=true").status_code == 422


def test_metrics_filter_by_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    ticket_abierto(session, pedro, area=areas["Redes"])
    ticket_abierto(session, pedro, area=areas["Redes"])
    ticket_abierto(session, pedro)
    todas = auth_client.get("/api/metricas").json()
    redes = auth_client.get(f"/api/metricas?area={areas['Redes'].id}").json()
    sin = auth_client.get("/api/metricas?sin_area=true").json()
    assert (todas["tarjetas"]["abiertos"], redes["tarjetas"]["abiertos"], sin["tarjetas"]["abiertos"]) == (3, 2, 1)
    assert redes["por_persona"][0]["abiertos"] == 2
    assert auth_client.get(f"/api/metricas?area={areas['Redes'].id}&sin_area=1").status_code == 422


# --- Chat: reglas y permisos -----------------------------------------------------

from backend.services.asistente_service import (  # noqa: E402
    PERMISOS_POR_ROL,
    REGLA_AREAS,
    REGLA_REPARTO,
    REGLAS_PARA_IA,
)
from backend.tests.test_asistente import ask, login_as  # noqa: E402
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: E402,F401


@pytest.mark.parametrize("pregunta", [
    "¿quién puede cambiar el área de un ticket?",
    "que areas hay y quien las puede administrar?",
])
def test_chat_answers_the_area_rule_without_ai(client, session, ia, pregunta):
    h = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    respuesta = _respuesta(ask(client, h, pregunta), "directa")
    assert respuesta == REGLA_AREAS
    assert ia.interpretaciones == [] and ia.calls == []


def test_chat_rules_and_permissions_talk_about_areas():
    assert "área de IT elegida" in REGLA_REPARTO or "área de IT (obligatoria)" in REGLA_REPARTO
    assert "Técnico activo de esa área con menos tickets abiertos" in REGLA_REPARTO
    assert REGLA_AREAS in REGLAS_PARA_IA
    assert "cambiar el área de IT de un ticket" in PERMISOS_POR_ROL["Técnico"].split("No puede")[0]
    assert "administrar las áreas de IT" in PERMISOS_POR_ROL["Técnico"].split("No puede")[1]
    assert "cambiar el área de IT de un ticket" in PERMISOS_POR_ROL["Solicitante"].split("No puede")[1]
    assert "No puede" not in PERMISOS_POR_ROL["Administrador"]
