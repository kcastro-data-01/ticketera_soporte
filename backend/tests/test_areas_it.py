"""Áreas de IT fijas (Soporte IT, Redes e Infraestructura, Ciberseguridad,
Programación): nadie las crea, renombra, desactiva ni borra (405), la
migración deja exactamente esas, un ticket sin área la toma de la categoría,
reparto al técnico del área con menos tickets abiertos, «IT solo recibe»
(nunca se asigna a un Solicitante), cambio de área (Administrador y Técnico)
y filtros en la lista y en las métricas."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text

from backend.auth import hash_password
from backend.constants import CATEGORY_IT_AREA, IT_AREAS
from backend.database import init_db
from backend.migrate_add_it_areas import fix_it_areas, migrate_it_areas
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


# Nombres cortos de las 4 áreas fijas en las pruebas.
SOP, RED, CIB, PROG = IT_AREAS


@pytest.fixture
def areas(engine, session):
    """Las 4 áreas fijas, como las deja la migración."""
    fix_it_areas(engine)
    return {a.name: a for a in session.scalars(select(ItArea)).all()}


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


def _vieja(tmp_path):
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
    return engine


def _areas_de(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT name FROM it_areas ORDER BY id")).scalars().all()


def test_migration_on_a_base_without_areas_creates_exactly_the_four(tmp_path):
    """Como en Neon: todavía no hay áreas. Lo de antes queda «Sin área»."""
    engine = _vieja(tmp_path)
    init_db(engine)
    assert _areas_de(engine) == list(IT_AREAS)
    assert _areas_de(engine)[0] == "Soporte IT", "en Neon se crea directo así"
    assert "Soporte" not in _areas_de(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT area_id FROM users")).scalars().all() == [None, None]
        # El ticket viejo asignado a un Solicitante queda como estaba, «Sin área».
        assert conn.execute(text("SELECT assigned_to_id, area_id FROM tickets")).one() == (2, None)
    init_db(engine)  # idempotente
    assert _areas_de(engine) == list(IT_AREAS)
    engine.dispose()


def test_migration_turns_the_old_areas_into_the_fixed_ones(tmp_path, caplog):
    """Una base vieja: «Soporte técnico» → «Soporte IT», «Redes» e
    «Infraestructura» → «Redes e Infraestructura», «Ciberseguridad» igual y
    cualquier otra («Samuel Mendez», las de prueba) se borra: sus tickets y
    técnicos quedan «Sin área»."""
    engine = create_engine(f"sqlite:///{tmp_path / 'local.db'}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM it_areas"))
        viejas = ["Soporte técnico", "Redes", "Infraestructura", "Ciberseguridad", "Samuel Mendez",
                  "Mesa de prueba", "Programacion"]
        for n, nombre in enumerate(viejas, start=1):
            conn.execute(text("INSERT INTO it_areas (id, name, is_active, created_at) "
                              "VALUES (:i, :n, :a, CURRENT_TIMESTAMP)"),
                         {"i": n, "n": nombre, "a": nombre != "Mesa de prueba"})
        # Un técnico y un ticket en cada área vieja.
        for n in range(1, 8):
            conn.execute(text("INSERT INTO users (id, name, email, role, is_active, area_id) "
                              "VALUES (:i, :n, :e, 'Técnico', 1, :a)"),
                         {"i": n, "n": f"T{n}", "e": f"t{n}@data.cr", "a": n})
            conn.execute(text("INSERT INTO tickets (id, title, description, category, priority, state, "
                              "area_id, created_at, updated_at) VALUES (:i, 'Ticket viejo', 'D', 'Red', "
                              "'Media', 'Nuevo', :a, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"i": n, "a": n})
    with caplog.at_level("WARNING"):
        init_db(engine)
    assert sorted(_areas_de(engine)) == sorted(IT_AREAS)
    with engine.connect() as conn:
        nombre_de = dict(conn.execute(text("SELECT id, name FROM it_areas")).all())
        areas_tickets = [nombre_de.get(a) for a in conn.execute(
            text("SELECT area_id FROM tickets ORDER BY id")).scalars().all()]
        areas_usuarios = [nombre_de.get(a) for a in conn.execute(
            text("SELECT area_id FROM users ORDER BY id")).scalars().all()]
    # «Programacion» (sin tilde) es Programación: no se pierde su ticket.
    esperado = [SOP, RED, RED, CIB, None, None, PROG]
    assert areas_tickets == esperado
    assert areas_usuarios == esperado
    assert "«Samuel Mendez»" in caplog.text and "«Soporte técnico» pasa a «Soporte IT»" in caplog.text
    caplog.clear()
    init_db(engine)
    assert "Departamentos (áreas de IT)" not in caplog.text, "ya al día: no hace nada"
    engine.dispose()


def test_migration_renames_soporte_to_soporte_it(tmp_path, caplog):
    """La base local de hoy: «Soporte» pasa a «Soporte IT» con el mismo id, así
    sus tickets y técnicos no se mueven; los demás quedan como estaban."""
    engine = create_engine(f"sqlite:///{tmp_path / 'local.db'}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM it_areas"))
        for n, nombre in enumerate(["Soporte", "Redes e Infraestructura", "Ciberseguridad", "Programación"],
                                   start=1):
            conn.execute(text("INSERT INTO it_areas (id, name, is_active, created_at) "
                              "VALUES (:i, :n, 1, CURRENT_TIMESTAMP)"), {"i": n, "n": nombre})
        conn.execute(text("INSERT INTO users (id, name, email, role, is_active, area_id) "
                          "VALUES (1, 'Ana', 'ana@data.cr', 'Técnico', 1, 1)"))
        conn.execute(text("INSERT INTO tickets (id, title, description, category, priority, state, "
                          "area_id, created_at, updated_at) VALUES (1, 'Ticket viejo', 'D', 'Hardware', "
                          "'Media', 'Nuevo', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    with caplog.at_level("WARNING"):
        init_db(engine)
    assert "«Soporte» pasa a «Soporte IT»" in caplog.text
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, name FROM it_areas ORDER BY id")).all() == [
            (1, "Soporte IT"), (2, "Redes e Infraestructura"), (3, "Ciberseguridad"), (4, "Programación")]
        assert conn.execute(text("SELECT area_id FROM users")).scalar_one() == 1
        assert conn.execute(text("SELECT area_id FROM tickets")).scalar_one() == 1
    caplog.clear()
    init_db(engine)
    assert "Departamentos (áreas de IT)" not in caplog.text, "ya al día: no hace nada"
    engine.dispose()


# --- Las áreas son fijas: nadie las cambia (405) -------------------------------


def test_everyone_lists_the_four_fixed_areas_in_order(client, session, areas):
    tecnico(session, "Pedro", areas[RED])
    tecnico(session, "Luis", areas[RED], activo=False)
    for rol in ("Administrador", "Técnico", "Solicitante"):
        _, h = headers_de(client, session, rol, f"{rol[:3].lower()}@data.cr", rol)
        lista = client.get("/api/areas", headers=h).json()
        assert [a["name"] for a in lista] == list(IT_AREAS), rol
    assert {a["name"]: a["tecnicos"] for a in lista}[RED] == 1
    uno = client.get(f"/api/areas/{areas[CIB].id}", headers=h)
    assert (uno.status_code, uno.json()["name"]) == (200, CIB)


@pytest.mark.parametrize("rol", ["Administrador", "Técnico", "Solicitante"])
def test_no_role_can_create_rename_deactivate_or_delete_areas(client, session, areas, rol):
    _, h = headers_de(client, session, rol, "quien@data.cr", "Quien")
    area = areas[SOP]
    for metodo, url, cuerpo in [
        ("POST", "/api/areas", {"name": "Nueva"}),
        ("PUT", "/api/areas", {"name": "Nueva"}),
        ("PATCH", "/api/areas", {"name": "Nueva"}),
        ("DELETE", "/api/areas", None),
        ("POST", f"/api/areas/{area.id}", {"name": "Otra"}),
        ("PUT", f"/api/areas/{area.id}", {"name": "Otra"}),
        ("PATCH", f"/api/areas/{area.id}", {"name": "Otra"}),
        ("PATCH", f"/api/areas/{area.id}", {"is_active": False}),
        ("DELETE", f"/api/areas/{area.id}", None),
    ]:
        resp = client.request(metodo, url, json=cuerpo, headers=h)
        assert resp.status_code == 405, f"{rol} {metodo} {url}: {resp.status_code}"
    session.expire_all()
    assert [a["name"] for a in client.get("/api/areas", headers=h).json()] == list(IT_AREAS)
    assert session.get(ItArea, area.id).is_active is True


def test_the_areas_page_and_menu_link_are_gone():
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    assert not (frontend / "areas.html").exists()
    for pagina in frontend.glob("*.html"):
        assert "areas.html" not in pagina.read_text(encoding="utf-8"), pagina.name


# --- Crear ticket: área obligatoria y reparto ----------------------------------


@pytest.mark.parametrize("categoria,area", sorted(CATEGORY_IT_AREA.items()))
def test_a_ticket_without_area_takes_it_from_its_category(auth_client, areas, categoria, area):
    data = auth_client.post("/api/tickets", json=TICKET | {"category": categoria}).json()
    assert data["area_name"] == area


def test_programming_is_only_chosen_by_hand():
    assert PROG not in CATEGORY_IT_AREA.values()
    assert set(CATEGORY_IT_AREA.values()) == {SOP, RED, CIB}


def test_unknown_area_is_rejected(auth_client, areas):
    assert auth_client.post("/api/tickets", json=TICKET | {"area_id": 999}).status_code == 422


def test_ticket_goes_to_the_area_technician_with_fewest_open_tickets(auth_client, session, areas):
    redes = areas[RED]
    pedro = tecnico(session, "Pedro", redes)
    luis = tecnico(session, "Luis", redes)
    tecnico(session, "Otro", areas[PROG])  # de otra área: no cuenta
    ticket_abierto(session, pedro)
    # Los cerrados y resueltos no cuentan: Luis tiene 2 pero ninguno abierto.
    ticket_abierto(session, luis, "Cerrado")
    ticket_abierto(session, luis, "Resuelto")
    resp = auth_client.post("/api/tickets", json=TICKET | {"area_id": redes.id})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert (data["assigned_to_id"], data["area_id"], data["area_name"]) == (luis.id, redes.id, RED)


def test_area_without_technicians_goes_to_any_technician_with_fewest(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    ana = tecnico(session, "Ana")  # sin área
    ticket_abierto(session, pedro)
    data = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas[PROG].id}).json()
    # El área es la que se eligió, aunque lo atienda alguien de otra.
    assert (data["assigned_to_id"], data["area_name"]) == (ana.id, PROG)


def test_without_technicians_the_ticket_stays_unassigned(auth_client, areas):
    data = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas[RED].id}).json()
    assert (data["assigned_to_id"], data["area_name"]) == (None, RED)


def test_requester_creates_a_ticket_with_area(client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    _, h = headers_de(client, session, "Solicitante", "sofia@data.cr", "Sofía")
    data = client.post("/api/tickets", json=TICKET | {"area_id": areas[RED].id}, headers=h).json()
    assert (data["assigned_to_id"], data["area_name"]) == (pedro.id, RED)


# --- IT solo recibe -------------------------------------------------------------


def test_a_ticket_can_not_be_assigned_to_a_requester(auth_client, session, areas):
    sofia = User(name="Sofía", email="sofia@data.cr", role="Solicitante")
    session.add(sofia)
    session.commit()
    ticket = auth_client.post("/api/tickets", json=TICKET | {"area_id": areas[RED].id}).json()
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


def test_inbox_ticket_goes_to_the_owner_with_the_area_of_its_category(session, areas):
    """Correo al buzón general: asignado al dueño (como antes) y el área sale
    de la categoría, aunque la dueña tenga otra área."""
    duena = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador",
                 area_id=areas[PROG].id)
    session.add_all([duena, User(name="Ana Pérez", email="ana@data.cr", role="Solicitante")])
    session.commit()
    resultado, _ = cs.procesar_correo(session, cs.correo_desde_graph(crear_correo()), CONFIG)
    assert resultado == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.assigned_to_id == duena.id
    assert ticket.area.name == CATEGORY_IT_AREA[ticket.category]


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
        ticket_service.create_ticket(session, TicketCreate(**TICKET), None, asignado=sofia)


# --- Cambiar el área ------------------------------------------------------------


def test_technician_moves_the_ticket_to_another_area_and_it_is_in_the_history(client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    _, h = headers_de(client, session, "Técnico", "luis@data.cr", "Luis", areas[PROG])
    ticket = ticket_abierto(session, pedro, area=areas[RED])
    resp = client.patch(f"/api/tickets/{ticket.id}/area",
                        json={"area_id": areas[PROG].id}, headers=h)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["area_name"], resp.json()["assigned_to_id"]) == (PROG, pedro.id)
    entrada = session.scalars(select(History).where(History.action == "area_changed")).one()
    assert (entrada.field, entrada.old_value, entrada.new_value, entrada.author) == (
        "area", RED, PROG, "Luis")
    historial = client.get(f"/api/tickets/{ticket.id}/history", headers=h).json()
    assert historial[-1]["action"] == "area_changed"


def test_changing_the_area_with_reassign_goes_to_the_new_area_technician(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    marta = tecnico(session, "Marta", areas[PROG])
    ticket = ticket_abierto(session, pedro, area=areas[RED])
    resp = auth_client.patch(f"/api/tickets/{ticket.id}/area",
                             json={"area_id": areas[PROG].id, "reasignar": True})
    assert resp.json()["assigned_to_id"] == marta.id
    acciones = session.scalars(select(History.action).where(History.ticket_id == ticket.id)
                               .order_by(History.id)).all()
    assert acciones == ["area_changed", "assigned"]


def test_sin_area_ticket_gets_an_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    ticket = ticket_abierto(session, pedro)
    auth_client.patch(f"/api/tickets/{ticket.id}/area", json={"area_id": areas[RED].id})
    entrada = session.scalars(select(History).where(History.action == "area_changed")).one()
    assert (entrada.old_value, entrada.new_value) == (None, RED)


def test_area_change_rules(client, auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    ticket = ticket_abierto(session, pedro, area=areas[RED])
    _, sol = headers_de(client, session, "Solicitante", "sofia@data.cr", "Sofía")
    url = f"/api/tickets/{ticket.id}/area"
    assert client.patch(url, json={"area_id": areas[PROG].id}, headers=sol).status_code == 403
    assert auth_client.patch(url, json={"area_id": 999}).status_code == 404
    ticket.state = "Cerrado"
    session.commit()
    assert auth_client.patch(url, json={"area_id": areas[SOP].id}).status_code == 409


# --- Usuarios -------------------------------------------------------------------


def test_admin_assigns_an_area_to_a_technician_and_to_themself(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"area_id": areas[RED].id})
    assert (resp.json()["area_id"], resp.json()["area_name"]) == (areas[RED].id, RED)
    yo = auth_client.get("/api/auth/me").json()
    assert auth_client.patch(f"/api/users/{yo['id']}", json={"area_id": areas[SOP].id}
                             ).json()["area_name"] == SOP
    # null quita el área.
    assert auth_client.patch(f"/api/users/{pedro.id}", json={"area_id": None}).json()["area_id"] is None


def test_a_requester_has_no_area(auth_client, session, areas):
    resp = auth_client.post("/api/users", json={"name": "Sofía", "email": "sofia@data.cr",
                                                 "role": "Solicitante", "area_id": areas[RED].id})
    assert resp.status_code == 422
    creado = auth_client.post("/api/users", json={"name": "Pedro", "email": "pedro@data.cr",
                                                   "role": "Técnico", "area_id": areas[RED].id})
    assert creado.json()["area_name"] == RED


def test_demoting_to_requester_clears_the_area_and_needs_no_open_tickets(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    abierto = ticket_abierto(session, pedro)
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"role": "Solicitante"})
    assert resp.status_code == 409
    assert "1 ticket abierto" in resp.json()["detail"]
    abierto.state = "Cerrado"
    session.commit()
    resp = auth_client.patch(f"/api/users/{pedro.id}", json={"role": "Solicitante"})
    assert resp.status_code == 200
    assert (resp.json()["role"], resp.json()["area_id"]) == ("Solicitante", None)


# --- Filtros ---------------------------------------------------------------------


def test_list_filters_by_area_and_sin_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    en_redes = ticket_abierto(session, pedro, area=areas[RED])
    sin = ticket_abierto(session, pedro)
    assert [t["id"] for t in auth_client.get(f"/api/tickets?area={areas[RED].id}").json()] == [en_redes.id]
    assert [t["id"] for t in auth_client.get("/api/tickets?sin_area=true").json()] == [sin.id]
    assert auth_client.get(f"/api/tickets?area={areas[RED].id}&sin_area=true").status_code == 422


def test_metrics_filter_by_area(auth_client, session, areas):
    pedro = tecnico(session, "Pedro")
    ticket_abierto(session, pedro, area=areas[RED])
    ticket_abierto(session, pedro, area=areas[RED])
    ticket_abierto(session, pedro)
    todas = auth_client.get("/api/metricas").json()
    redes = auth_client.get(f"/api/metricas?area={areas[RED].id}").json()
    sin = auth_client.get("/api/metricas?sin_area=true").json()
    assert (todas["tarjetas"]["abiertos"], redes["tarjetas"]["abiertos"], sin["tarjetas"]["abiertos"]) == (3, 2, 1)
    assert redes["por_persona"][0]["abiertos"] == 2
    assert auth_client.get(f"/api/metricas?area={areas[RED].id}&sin_area=1").status_code == 422


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
    "¿quién puede cambiar el departamento de un ticket?",
    "que departamentos hay?",
    "¿quién puede cambiar el área de un ticket?",
    "que areas hay?",
])
def test_chat_answers_the_area_rule_without_ai(client, session, ia, pregunta):
    h = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    respuesta = _respuesta(ask(client, h, pregunta), "directa")
    assert respuesta == REGLA_AREAS
    assert ia.interpretaciones == [] and ia.calls == []


def test_chat_rules_and_permissions_talk_about_areas():
    assert "el departamento (obligatorio)" in REGLA_REPARTO
    assert "Técnico activo de ese departamento con menos tickets abiertos" in REGLA_REPARTO
    assert REGLA_AREAS in REGLAS_PARA_IA
    assert "cambiar el departamento de un ticket" in PERMISOS_POR_ROL["Técnico"].split("No puede")[0]
    for rol in PERMISOS_POR_ROL:
        assert "administrar las áreas" not in PERMISOS_POR_ROL[rol], rol
    for area in IT_AREAS:
        assert area in REGLA_AREAS
    assert "Hardware y Software → Soporte IT" in REGLA_AREAS
    assert "cambiar el departamento de un ticket" in PERMISOS_POR_ROL["Solicitante"].split("No puede")[1]
    assert "No puede" not in PERMISOS_POR_ROL["Administrador"]


def test_people_see_departamento_not_area():
    """En la app se dice «Departamento» (en el código y la base, «área»)."""
    import re

    from backend.constants import NO_AREA_LABEL
    from backend.services import asistente_service as asis

    assert NO_AREA_LABEL == "Sin departamento"
    textos = [asis.GUIA_APP, asis.REGLAS_PARA_IA, *asis.PERMISOS_POR_ROL.values(),
              *asis.DESCRIPCION_ROL.values()]
    for texto in textos:
        limpio = texto.replace("área de TI", "")
        assert not re.search(r"\b[Áá]reas?\b", limpio), limpio[:120]
    assert ("Cambiar departamento", "cambiar el departamento de un ticket",
            ("Mientras está en Nuevo", "Mientras está en Nuevo", "No")) in asis.TABLA_PERMISOS


def test_api_messages_say_departamento(auth_client, session, areas):
    assert auth_client.post("/api/tickets", json=TICKET | {"area_id": 999}).json()["detail"] == (
        "Departamento 999 no encontrado")
    filtro = auth_client.get(f"/api/tickets?area={areas[RED].id}&sin_area=true").json()["detail"]
    assert filtro == "Elija un departamento o «Sin departamento», no los dos."
    resp = auth_client.post("/api/users", json={"name": "Sofía", "email": "sofia@data.cr",
                                                 "role": "Solicitante", "area_id": areas[RED].id})
    assert resp.json()["detail"] == "El Solicitante no tiene departamento: solo Técnicos y Administradores."


def test_help_and_chat_say_the_same():
    """La ayuda y el chat dicen lo mismo: la tabla de permisos es la misma (otra
    prueba la compara), los 4 departamentos con lo que atiende cada uno, IT
    solo recibe, la nota de los tickets de antes y la lista sin páginas."""
    from pathlib import Path

    from backend.constants import IT_AREA_SCOPE
    from backend.services import asistente_service as asis

    ayuda = (Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html").read_text(encoding="utf-8")
    for area, atiende in IT_AREA_SCOPE.items():
        assert f"<strong>{area}</strong>: {atiende}." in ayuda, area
        assert f"{area} ({atiende})" in asis.REGLA_AREAS, area
    assert asis.NOTA_ASIGNADOS_DE_ANTES in ayuda
    assert asis.NOTA_ASIGNADOS_DE_ANTES in asis.REGLAS_PARA_IA
    assert "IT solo recibe" in ayuda and "IT solo recibe" in asis.REGLA_SOLICITANTE
    assert "sin páginas" in ayuda and "sin páginas" in asis.GUIA_APP
    assert "tarjetas de resumen" not in asis.GUIA_APP
    assert "asignados a él" not in ayuda
    for _, _, valores in asis.TABLA_PERMISOS:
        assert "asignados" not in valores[2]


# --- El departamento solo se cambia en Nuevo -------------------------------------

SOLO_NUEVO = "El departamento solo se puede cambiar mientras el ticket está en Nuevo"


def test_in_nuevo_the_department_can_be_changed(auth_client, session, areas):
    pedro = tecnico(session, "Pedro", areas[RED])
    ticket = ticket_abierto(session, pedro, area=areas[RED])
    resp = auth_client.patch(f"/api/tickets/{ticket.id}/area", json={"area_id": areas[SOP].id})
    assert (resp.status_code, resp.json()["area_name"]) == (200, SOP)


@pytest.mark.parametrize("estado", ["En proceso", "Resuelto", "Cerrado"])
@pytest.mark.parametrize("rol", ["Administrador", "Técnico"])
def test_outside_nuevo_changing_the_department_is_409_for_everyone(client, session, areas, estado, rol):
    pedro = tecnico(session, "Pedro", areas[RED])
    ticket = ticket_abierto(session, pedro, estado=estado, area=areas[RED])
    _, h = headers_de(client, session, rol, "quien@data.cr", "Quien")
    resp = client.patch(f"/api/tickets/{ticket.id}/area",
                        json={"area_id": areas[SOP].id, "reasignar": True}, headers=h)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == SOLO_NUEVO
    session.expire_all()
    guardado = session.get(Ticket, ticket.id)
    assert (guardado.area_id, guardado.assigned_to_id) == (areas[RED].id, pedro.id), "no cambia nada"
    assert session.scalars(select(History).where(History.action == "area_changed")).all() == []


def test_the_help_and_the_chat_say_it_only_changes_in_nuevo():
    from pathlib import Path

    from backend.services import asistente_service as asis

    ayuda = (Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html").read_text(encoding="utf-8")
    assert "solo mientras el ticket está en Nuevo" in ayuda
    assert "En los demás estados esa sección no aparece; el departamento se ve en «Detalles»." in ayuda
    assert "Departamento actual" not in ayuda
    assert "solo mientras el ticket está en Nuevo" in asis.REGLA_AREAS
    assert "cambiar el departamento de un ticket (mientras está en Nuevo)" in asis.PERMISOS_POR_ROL["Técnico"]
    guia = " ".join(asis.GUIA_APP.split())
    assert "el departamento se ve en «Detalles»" in guia
    assert "en los demás estados esa sección no aparece" in guia
    assert "a la derecha, el departamento" not in guia


def test_the_support_department_is_called_soporte_it_everywhere():
    """El departamento fijo es «Soporte IT» en la ayuda, el chat, «Nuevo
    ticket», «Usuarios», el README y docs/api.md (el menú «Soporte» y el buzón
    de soporte no son el departamento)."""
    import re
    from pathlib import Path

    from backend.constants import CATEGORY_IT_AREA, IT_AREA_SCOPE, IT_AREA_SUPPORT
    from backend.services import asistente_service as asis

    assert IT_AREA_SUPPORT == "Soporte IT" and IT_AREAS[0] == "Soporte IT"
    assert CATEGORY_IT_AREA["Hardware"] == CATEGORY_IT_AREA["Software"] == "Soporte IT"
    assert "Soporte IT" in IT_AREA_SCOPE
    raiz = Path(__file__).resolve().parents[2]
    textos = {nombre: (raiz / nombre).read_text(encoding="utf-8") for nombre in (
        "frontend/ayuda.html", "frontend/crear.html", "frontend/usuarios.html", "README.md", "docs/api.md")}
    textos["chat"] = asis.GUIA_APP + asis.REGLA_AREAS + asis.REGLAS_PARA_IA
    viejo = re.compile(r"→ Soporte(?! IT)|Soporte \(|<strong>Soporte</strong>|fijos: Soporte,|"
                       r"Soporte → |\| Soporte \|")
    for nombre, texto in textos.items():
        assert not viejo.search(texto), nombre
    for nombre in ("frontend/ayuda.html", "frontend/crear.html", "chat"):
        assert "Soporte IT" in textos[nombre], nombre
