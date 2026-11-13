"""Pantalla «Departamentos» (solo Administrador): GET
/api/departamentos/resumen con los números por departamento y estado, los
Técnicos activos y el departamento con más abiertos; 403 para Técnico y
Solicitante; el permiso «Ver departamentos» en la ayuda y en el chat."""

from pathlib import Path

import pytest
from sqlalchemy import select

from backend.constants import IT_AREAS
from backend.migrate_add_it_areas import fix_it_areas
from backend.models import ItArea, Ticket, User
from backend.services.asistente_service import PERMISOS_POR_ROL, REGLA_AREAS, TABLA_PERMISOS
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401

SOP, RED, CIB, PROG = IT_AREAS
URL = "/api/departamentos/resumen"


@pytest.fixture
def areas(engine, session):
    fix_it_areas(engine)
    return {a.name: a for a in session.scalars(select(ItArea)).all()}


def ticket(session, estado, area=None):
    session.add(Ticket(title="Ticket de prueba", description="Para contar", category="Red",
                       priority="Media", state=estado, area_id=area.id if area else None))
    session.commit()


def tecnico(session, nombre, area, activo=True, rol="Técnico"):
    session.add(User(name=nombre, email=f"{nombre.split()[0].lower()}@data.cr", role=rol,
                     area_id=area.id if area else None, is_active=activo))
    session.commit()


def test_admin_gets_the_numbers_per_department(auth_client, session, areas):
    for estado in ("Nuevo", "Nuevo", "En proceso", "Resuelto", "Cerrado"):
        ticket(session, estado, areas[SOP])
    for estado in ("Nuevo", "En proceso", "En proceso"):
        ticket(session, estado, areas[RED])
    ticket(session, "Cerrado", areas[PROG])
    ticket(session, "Nuevo")  # Sin departamento
    tecnico(session, "Luis Solís", areas[SOP])
    tecnico(session, "Ana Mora", areas[SOP])
    tecnico(session, "Inés Inactiva", areas[SOP], activo=False)  # inactiva: no cuenta
    tecnico(session, "Jefa IT", areas[SOP], rol="Administrador")  # no es Técnico
    tecnico(session, "Pedro Rojas", areas[RED])

    resp = auth_client.get(URL)
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["total_abiertos"] == 3 + 3 + 0 + 0 + 1
    assert datos["mas_abiertos"] == {"area_id": areas[SOP].id, "nombre": SOP, "abiertos": 3}, \
        "empate 3 a 3: gana el primero (Soporte IT)"
    filas = {f["nombre"]: f for f in datos["departamentos"]}
    assert [f["nombre"] for f in datos["departamentos"]] == [*IT_AREAS, "Sin departamento"]
    assert filas[SOP]["total"] == 5 and filas[SOP]["abiertos"] == 3
    assert filas[SOP]["por_estado"] == {"Nuevo": 2, "En proceso": 1, "Resuelto": 1, "Cerrado": 1}
    assert [t["name"] for t in filas[SOP]["tecnicos"]] == ["Ana Mora", "Luis Solís"]
    assert filas[RED]["por_estado"] == {"Nuevo": 1, "En proceso": 2, "Resuelto": 0, "Cerrado": 0}
    assert [t["name"] for t in filas[RED]["tecnicos"]] == ["Pedro Rojas"]
    assert (filas[CIB]["total"], filas[CIB]["abiertos"], filas[CIB]["tecnicos"]) == (0, 0, [])
    assert (filas[PROG]["total"], filas[PROG]["abiertos"]) == (1, 0)
    sin = filas["Sin departamento"]
    assert (sin["area_id"], sin["total"], sin["abiertos"], sin["tecnicos"]) == (None, 1, 1, [])


def test_without_open_tickets_there_is_no_department_with_more(auth_client, areas, session):
    ticket(session, "Cerrado", areas[SOP])
    datos = auth_client.get(URL).json()
    assert (datos["total_abiertos"], datos["mas_abiertos"]) == (0, None)


@pytest.mark.parametrize("rol", ["Técnico", "Solicitante"])
def test_technician_and_requester_get_403(client, session, areas, rol):
    headers = login_as(client, session, rol, "persona@data.cr", "Persona")
    assert client.get(URL, headers=headers).status_code == 403


def test_without_session_401(client):
    assert client.get(URL).status_code == 401


def test_the_permission_is_in_the_help_and_in_the_chat():
    assert ("Ver departamentos", "ver la pantalla «Departamentos»", ("Sí", "No", "No")) in TABLA_PERMISOS
    for rol in ("Técnico", "Solicitante"):
        assert "ver la pantalla «Departamentos»" in PERMISOS_POR_ROL[rol].split("No puede")[1], rol
    assert "ver la pantalla «Departamentos»" in PERMISOS_POR_ROL["Administrador"]
    assert "Solo el Administrador ve la pantalla «Departamentos»" in REGLA_AREAS
    ayuda = (Path(__file__).resolve().parents[2] / "frontend" / "ayuda.html").read_text(encoding="utf-8")
    assert "<tr><td>Ver departamentos</td><td>Sí</td><td>No</td><td>No</td></tr>" in ayuda


def test_chat_says_only_the_admin_sees_it(client, session, ia):
    headers = login_as(client, session, "Técnico", "tec@data.cr", "José Solano")
    respuesta = _respuesta(ask(client, headers, "¿quién puede ver los departamentos?"), "directa")
    assert "Solo el Administrador ve la pantalla «Departamentos»" in respuesta
    assert ia.calls == []


def test_detail_brings_scope_technicians_and_open_tickets(auth_client, session, areas):
    """Lo que pinta el detalle: qué atiende, cada Técnico con sus abiertos y
    resueltos de este mes, y los abiertos por prioridad y antigüedad (10 como
    máximo)."""
    from datetime import datetime, timedelta, timezone

    from backend.models import History

    tecnico(session, "Ana Mora", areas[SOP])
    tecnico(session, "Luis Solís", areas[SOP])
    ana, luis = (session.scalar(select(User).where(User.name == n)) for n in ("Ana Mora", "Luis Solís"))
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)

    def nuevo(prioridad, estado="Nuevo", horas=0, quien=None, area=areas[SOP], titulo="Ticket abierto"):
        t = Ticket(title=titulo, description="Para el detalle", category="Hardware", priority=prioridad,
                   state=estado, area_id=area.id, assigned_to_id=quien.id if quien else None,
                   created_at=ahora - timedelta(hours=horas))
        session.add(t)
        session.commit()
        return t

    media_vieja = nuevo("Media", horas=50, quien=ana, titulo="Media vieja")
    critica = nuevo("Crítica", "En proceso", horas=1, quien=luis, titulo="Crítica nueva")
    media_nueva = nuevo("Media", horas=2, titulo="Media nueva")
    baja = nuevo("Baja", horas=99, quien=ana, titulo="Baja vieja")
    nuevo("Alta", area=areas[RED])  # de otro departamento: no cuenta para Ana
    resuelto = nuevo("Alta", "Resuelto", quien=ana)
    session.add(History(ticket_id=resuelto.id, action="updated", field="state",
                        old_value="En proceso", new_value="Resuelto", created_at=ahora))
    viejo = nuevo("Alta", "Cerrado", quien=luis)
    session.add(History(ticket_id=viejo.id, action="updated", field="state",
                        old_value="En proceso", new_value="Resuelto",
                        created_at=ahora - timedelta(days=40)))  # otro mes: no cuenta
    session.commit()

    filas = {f["nombre"]: f for f in auth_client.get(URL).json()["departamentos"]}
    datos = auth_client.get(URL).json()
    # Resumen de todos: abiertos sin asignar (Media nueva + el Alta de Redes)
    # y resueltos este mes (el del otro mes no cuenta).
    assert (datos["total_abiertos"], datos["sin_asignar"], datos["resueltos_mes"]) == (5, 2, 1)
    soporte = filas[SOP]
    assert soporte["atiende"] == "computadoras, impresoras, programas"
    assert filas["Sin departamento"]["atiende"]
    assert [(t["name"], t["abiertos"], t["resueltos_mes"]) for t in soporte["tecnicos"]] == [
        ("Ana Mora", 2, 1), ("Luis Solís", 1, 0)]
    assert [t["id"] for t in soporte["tickets_abiertos"]] == [critica.id, media_vieja.id, media_nueva.id, baja.id]
    primero = soporte["tickets_abiertos"][0]
    assert (primero["title"], primero["state"], primero["priority"], primero["assigned_to_name"]) == (
        "Crítica nueva", "En proceso", "Crítica", "Luis Solís")
    assert soporte["tickets_abiertos"][2]["assigned_to_name"] is None

    for _ in range(9):
        nuevo("Baja")
    soporte = {f["nombre"]: f for f in auth_client.get(URL).json()["departamentos"]}[SOP]
    assert soporte["abiertos"] == 13 and len(soporte["tickets_abiertos"]) == 10
