"""GET /api/metricas: conteos, filtro de fechas (días de Costa Rica), tiempo
promedio de resolución, correo frente a web y permisos."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.models import History, ProcessedEmail, Ticket, User
from backend.services import metricas_service
from backend.tests.test_asistente import login_as

CR = timezone(timedelta(hours=-6))


def cr(dia: str, hora: str = "10:00") -> datetime:
    """Instante en hora de Costa Rica, guardado en UTC como hace la app."""
    local = datetime.fromisoformat(f"{dia}T{hora}").replace(tzinfo=CR)
    return local.astimezone(timezone.utc)


def persona(session, nombre, rol, correo, activo=True):
    user = User(name=nombre, email=correo, role=rol, password_hash="x", is_active=activo)
    session.add(user)
    session.commit()
    return user


def ticket(session, creado, estado="Nuevo", categoria="Hardware", asignado=None, resuelto=None):
    t = Ticket(title=f"T {creado:%d %H:%M}", description="d", category=categoria, priority="Media",
               state=estado, created_at=creado, assigned_to_id=asignado.id if asignado else None)
    session.add(t)
    session.commit()
    if resuelto is not None:
        session.add(History(ticket_id=t.id, action="Cambio de estado", field="state",
                            old_value="En proceso", new_value="Resuelto", created_at=resuelto))
        session.commit()
    return t


@pytest.fixture
def admin(client, session):
    return login_as(client, session, "Administrador", "admin@x.local", "Laura Méndez")


def metricas(client, headers, **params):
    resp = client.get("/api/metricas", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_counts_cards_states_categories_and_people(client, session, admin):
    carlos = persona(session, "Carlos Solís", "Técnico", "carlos@x.local")
    sup = persona(session, "Marta Rojas", "Técnico", "marta@x.local")
    ticket(session, cr("2026-10-02"), "Nuevo", "Hardware", carlos)
    ticket(session, cr("2026-10-03"), "En proceso", "Red", carlos)
    ticket(session, cr("2026-10-04"), "En proceso", "Software", sup)
    ticket(session, cr("2026-10-05"), "Nuevo", "Red")  # sin asignar
    ticket(session, cr("2026-10-01", "08:00"), "Resuelto", "Accesos", carlos,
           resuelto=cr("2026-10-01", "18:00"))  # 10 h
    ticket(session, cr("2026-10-02", "08:00"), "Cerrado", "Hardware", sup,
           resuelto=cr("2026-10-03", "14:00"))  # 30 h

    m = metricas(client, admin, desde="2026-10-01", hasta="2026-10-10")
    assert m["desde"] == "2026-10-01" and m["hasta"] == "2026-10-10"
    assert m["tarjetas"] == {
        "abiertos": 4, "en_proceso": 2, "resueltos_periodo": 2, "tiempo_promedio_horas": 20.0,
        "creados_periodo": 6, "por_correo": 0, "por_web": 6,
    }
    assert m["por_estado"] == [{"nombre": "Nuevo", "total": 2}, {"nombre": "En proceso", "total": 2},
                               {"nombre": "Resuelto", "total": 1}, {"nombre": "Cerrado", "total": 1}]
    categorias = {c["nombre"]: c["total"] for c in m["por_categoria"]}
    assert categorias == {"Hardware": 2, "Software": 1, "Red": 2, "Accesos": 1}
    assert m["por_persona"] == [
        {"id": carlos.id, "nombre": "Carlos Solís", "rol": "Técnico", "activo": True, "abiertos": 2, "resueltos": 1},
        {"id": sup.id, "nombre": "Marta Rojas", "rol": "Técnico", "activo": True, "abiertos": 1, "resueltos": 1},
    ]
    assert m["sin_asignar_abiertos"] == 1


def test_date_filter_includes_both_ends_and_uses_costa_rica_days(client, session, admin):
    ticket(session, cr("2026-09-30", "23:59"))                 # antes del rango
    ticket(session, cr("2026-10-01", "00:00"))                 # primer instante
    ticket(session, cr("2026-10-03", "23:30"))                 # en UTC ya es el 4
    ticket(session, cr("2026-10-05", "23:59"))                 # último día
    ticket(session, cr("2026-10-06", "00:00"))                 # después del rango

    m = metricas(client, admin, desde="2026-10-01", hasta="2026-10-05")
    assert m["tarjetas"]["creados_periodo"] == 3
    assert m["por_dia"] == [
        {"fecha": "2026-10-01", "total": 1}, {"fecha": "2026-10-02", "total": 0},
        {"fecha": "2026-10-03", "total": 1}, {"fecha": "2026-10-04", "total": 0},
        {"fecha": "2026-10-05", "total": 1},
    ]
    # La cola de hoy no depende del rango: los 5 siguen abiertos.
    assert m["tarjetas"]["abiertos"] == 5


def test_average_resolution_only_counts_tickets_resolved_in_the_range(client, session, admin):
    ticket(session, cr("2026-10-01", "08:00"), "Resuelto", resuelto=cr("2026-10-01", "12:00"))  # 4 h
    ticket(session, cr("2026-09-01"), "Resuelto", resuelto=cr("2026-09-02"))  # fuera del rango
    m = metricas(client, admin, desde="2026-10-01", hasta="2026-10-31")
    assert m["tarjetas"]["resueltos_periodo"] == 1
    assert m["tarjetas"]["tiempo_promedio_horas"] == 4.0

    vacio = metricas(client, admin, desde="2026-11-01", hasta="2026-11-30")
    assert vacio["tarjetas"]["resueltos_periodo"] == 0
    assert vacio["tarjetas"]["tiempo_promedio_horas"] is None


def test_first_resolution_is_used(client, session, admin):
    t = ticket(session, cr("2026-10-01", "08:00"), "Cerrado", resuelto=cr("2026-10-01", "10:00"))
    session.add(History(ticket_id=t.id, action="Cambio de estado", field="state", old_value="Resuelto",
                        new_value="Cerrado", created_at=cr("2026-10-02")))
    session.commit()
    m = metricas(client, admin, desde="2026-10-01", hasta="2026-10-31")
    assert m["tarjetas"]["resueltos_periodo"] == 1
    assert m["tarjetas"]["tiempo_promedio_horas"] == 2.0


def test_email_versus_web(client, session, admin):
    por_correo = ticket(session, cr("2026-10-02"))
    ticket(session, cr("2026-10-03"))
    viejo = ticket(session, cr("2026-08-01"))
    session.add_all([
        ProcessedEmail(message_id="<a@x>", sender="a@x", result="ticket", ticket_id=por_correo.id),
        ProcessedEmail(message_id="<b@x>", sender="b@x", result="comentario", ticket_id=por_correo.id),
        ProcessedEmail(message_id="<c@x>", sender="c@x", result="ticket", ticket_id=viejo.id),
    ])
    session.commit()
    m = metricas(client, admin, desde="2026-10-01", hasta="2026-10-31")
    assert (m["tarjetas"]["creados_periodo"], m["tarjetas"]["por_correo"], m["tarjetas"]["por_web"]) == (2, 1, 1)


def test_default_range_is_the_last_30_days(client, session, admin, monkeypatch):
    monkeypatch.setattr(metricas_service, "hoy", lambda: date(2026, 10, 19))
    ticket(session, cr("2026-09-20"))   # primer día del rango
    ticket(session, cr("2026-09-19"))   # día 31: afuera
    m = metricas(client, admin)
    assert (m["desde"], m["hasta"]) == ("2026-09-20", "2026-10-19")
    assert len(m["por_dia"]) == 30
    assert m["tarjetas"]["creados_periodo"] == 1


@pytest.mark.parametrize("params,mensaje", [
    ({"desde": "2026-10-10", "hasta": "2026-10-01"}, "posterior"),
    ({"desde": "2025-01-01", "hasta": "2026-10-01"}, "366"),
])
def test_invalid_ranges(client, session, admin, params, mensaje):
    resp = client.get("/api/metricas", params=params, headers=admin)
    assert resp.status_code == 422
    assert mensaje in resp.json()["detail"]


def test_bad_date_format_is_422(client, session, admin):
    assert client.get("/api/metricas", params={"desde": "ayer"}, headers=admin).status_code == 422


@pytest.mark.parametrize("rol,codigo", [
    ("Administrador", 200), ("Técnico", 403), ("Solicitante", 403),
])
def test_permissions(client, session, rol, codigo):
    headers = login_as(client, session, rol, "p@x.local", "Persona")
    assert client.get("/api/metricas", headers=headers).status_code == codigo


def test_requires_login(client):
    assert client.get("/api/metricas").status_code == 401
