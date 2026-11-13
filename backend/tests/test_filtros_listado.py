"""Filtros «Asignado a» y «Desde / Hasta» de GET /api/tickets.

* ``assigned_to`` / ``sin_asignar``: por persona asignada o sin asignar.
* ``fecha_campo`` + ``desde`` / ``hasta``: la creación o la primera vez que
  el ticket pasó a En proceso, Resuelto o Cerrado (del historial), en días
  de Costa Rica (UTC−6) con los dos extremos incluidos.
* Validación (422): ``desde`` posterior a ``hasta``, usuario inexistente,
  ``assigned_to`` junto con ``sin_asignar``.
* Se combinan con los demás filtros y respetan lo que ve cada rol.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.models import History, Ticket, User
from backend.tests.test_asistente import ask, login_as
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: F401

RAIZ = Path(__file__).resolve().parents[2]


def utc(*partes) -> datetime:
    return datetime(*partes, tzinfo=timezone.utc)


@pytest.fixture
def equipo(client, session):
    """Administrador, Técnico (Luis), Solicitante (Sara) y sus tokens."""
    gente = {}
    for clave, rol, email, nombre in (
        ("admin", "Administrador", "admin@data.cr", "Ana Admin"),
        ("luis", "Técnico", "luis@data.cr", "Luis Mora"),
        ("sara", "Solicitante", "sara@data.cr", "Sara Solano"),
    ):
        headers = login_as(client, session, rol, email, nombre)
        gente[clave] = (headers, session.scalars(select(User).where(User.email == email)).one())
    return gente


def ticket(session, titulo, *, creado, asignado=None, creador=None, categoria="Red",
           prioridad="Media", estado="Nuevo", pasos=()):
    """Ticket con su fecha de creación y sus pasos de estado ``(estado, cuándo)``."""
    t = Ticket(title=titulo, description=f"Descripción de {titulo}", category=categoria,
               priority=prioridad, state=estado, created_at=creado, updated_at=creado,
               assigned_to_id=asignado.id if asignado else None,
               created_by_id=creador.id if creador else None)
    session.add(t)
    session.commit()
    anterior = "Nuevo"
    for nuevo, cuando in pasos:
        session.add(History(ticket_id=t.id, action="Cambio de estado", field="state",
                            old_value=anterior, new_value=nuevo, created_at=cuando))
        anterior = nuevo
    session.commit()
    return t


def ids(resp):
    assert resp.status_code == 200, resp.text
    return sorted(t["id"] for t in resp.json())


def listar(client, headers, **params):
    return client.get("/api/tickets", headers=headers, params=params)


# --- «Asignado a» ---------------------------------------------------------------


def test_assigned_to_and_unassigned(client, session, equipo):
    headers, admin = equipo["admin"]
    _, luis = equipo["luis"]
    de_luis = ticket(session, "VPN caída", creado=utc(2026, 10, 1, 15), asignado=luis)
    de_ana = ticket(session, "Impresora", creado=utc(2026, 10, 1, 15), asignado=admin)
    suelto = ticket(session, "Monitor roto", creado=utc(2026, 10, 1, 15))

    assert ids(listar(client, headers, assigned_to=luis.id)) == [de_luis.id]
    assert ids(listar(client, headers, sin_asignar="true")) == [suelto.id]
    assert ids(listar(client, headers)) == sorted([de_luis.id, de_ana.id, suelto.id])
    resp = listar(client, headers, assigned_to=luis.id)
    assert resp.headers["X-Total-Count"] == "1"


def test_technician_can_use_the_assignee_filter(client, session, equipo):
    headers, luis = equipo["luis"]
    _, admin = equipo["admin"]
    ticket(session, "VPN caída", creado=utc(2026, 10, 1, 15), asignado=luis)
    de_ana = ticket(session, "Impresora", creado=utc(2026, 10, 1, 15), asignado=admin)
    assert ids(listar(client, headers, assigned_to=admin.id)) == [de_ana.id]


def test_unknown_user_is_422(client, session, equipo):
    headers, _ = equipo["admin"]
    resp = listar(client, headers, assigned_to=999)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Usuario 999 no encontrado"


def test_user_and_unassigned_together_is_422(client, session, equipo):
    headers, _ = equipo["admin"]
    _, luis = equipo["luis"]
    resp = listar(client, headers, assigned_to=luis.id, sin_asignar="true")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Elija un usuario o «Sin asignar», no los dos."


def test_requester_still_sees_only_their_tickets(client, session, equipo):
    """El Solicitante no tiene el filtro en pantalla; si manda el parámetro,
    igual solo le llegan los tickets que ve."""
    headers, sara = equipo["sara"]
    _, luis = equipo["luis"]
    suyo = ticket(session, "Mi VPN", creado=utc(2026, 10, 1, 15), asignado=luis, creador=sara)
    ticket(session, "VPN ajena", creado=utc(2026, 10, 1, 15), asignado=luis)
    ticket(session, "Sin dueño", creado=utc(2026, 10, 1, 15))

    assert ids(listar(client, headers, assigned_to=luis.id)) == [suyo.id]
    assert ids(listar(client, headers, sin_asignar="true")) == []


# --- Fechas ----------------------------------------------------------------------


@pytest.fixture
def octubre(session, equipo):
    """Tickets alrededor de los bordes de octubre en hora de Costa Rica (UTC−6)."""
    _, luis = equipo["luis"]
    return {
        # 30 de septiembre 23:30 en Costa Rica (1 de octubre 05:30 UTC).
        "sep30": ticket(session, "Teclado", creado=utc(2026, 10, 1, 5, 30)),
        # 1 de octubre 00:00 en Costa Rica exacto.
        "oct1": ticket(session, "Mouse", creado=utc(2026, 10, 1, 6, 0)),
        # 31 de octubre 23:59 en Costa Rica (1 de noviembre 05:59 UTC).
        "oct31": ticket(session, "Pantalla", creado=utc(2026, 11, 1, 5, 59)),
        # 1 de noviembre 00:00 en Costa Rica.
        "nov1": ticket(session, "Cable", creado=utc(2026, 11, 1, 6, 0), asignado=luis),
    }


def test_created_between_includes_both_ends_in_costa_rica_time(client, equipo, octubre):
    headers, _ = equipo["admin"]
    resp = listar(client, headers, desde="2026-10-01", hasta="2026-10-31")
    assert ids(resp) == sorted([octubre["oct1"].id, octubre["oct31"].id])


def test_only_from_or_only_until(client, equipo, octubre):
    headers, _ = equipo["admin"]
    assert ids(listar(client, headers, desde="2026-11-01")) == [octubre["nov1"].id]
    assert ids(listar(client, headers, hasta="2026-09-30")) == [octubre["sep30"].id]


def test_same_day_from_and_until(client, equipo, octubre):
    headers, _ = equipo["admin"]
    assert ids(listar(client, headers, desde="2026-10-31", hasta="2026-10-31")) == [octubre["oct31"].id]


def test_from_after_until_is_422(client, equipo):
    headers, _ = equipo["admin"]
    resp = listar(client, headers, desde="2026-10-31", hasta="2026-10-01")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "La fecha «Desde» no puede ser posterior a «Hasta»."


@pytest.mark.parametrize("params", [
    {"desde": "31/10/2026"}, {"hasta": "ayer"}, {"fecha_campo": "modificacion", "desde": "2026-10-01"},
])
def test_invalid_dates_or_field_are_422(client, equipo, params):
    headers, _ = equipo["admin"]
    assert listar(client, headers, **params).status_code == 422


@pytest.fixture
def con_pasos(session):
    """Un ticket que pasó a En proceso en septiembre y a Resuelto dos veces
    (primero el 31 de octubre a las 23:00 de Costa Rica, después en noviembre)
    y otro que nunca pasó por En proceso (Nuevo → Cerrado)."""
    reabierto = ticket(session, "VPN intermitente", creado=utc(2026, 9, 20, 15), estado="Cerrado", pasos=[
        ("En proceso", utc(2026, 9, 25, 15)),
        ("Resuelto", utc(2026, 11, 1, 5)),        # 31/10 23:00 en Costa Rica
        ("En proceso", utc(2026, 11, 3, 15)),
        ("Resuelto", utc(2026, 11, 5, 15)),
        ("Cerrado", utc(2026, 11, 6, 15)),
    ])
    directo = ticket(session, "No se hará", creado=utc(2026, 10, 10, 15), estado="Cerrado", pasos=[
        ("Cerrado", utc(2026, 10, 12, 15)),
    ])
    return reabierto, directo


def test_state_date_uses_the_first_time_it_reached_that_state(client, equipo, con_pasos):
    headers, _ = equipo["admin"]
    reabierto, directo = con_pasos
    octubre = {"desde": "2026-10-01", "hasta": "2026-10-31"}

    assert ids(listar(client, headers, fecha_campo="resuelto", **octubre)) == [reabierto.id]
    # La segunda vez que pasó a Resuelto (noviembre) no cuenta.
    assert ids(listar(client, headers, fecha_campo="resuelto", desde="2026-11-02")) == []
    # Pasó a En proceso por primera vez en septiembre, aunque volvió en noviembre.
    assert ids(listar(client, headers, fecha_campo="en_proceso", desde="2026-11-01")) == []
    assert ids(listar(client, headers, fecha_campo="en_proceso", hasta="2026-09-30")) == [reabierto.id]
    assert ids(listar(client, headers, fecha_campo="cerrado", **octubre)) == [directo.id]
    # Creado: ninguno de los dos se creó en noviembre.
    assert ids(listar(client, headers, desde="2026-11-01")) == []


def test_ticket_that_never_reached_the_state_does_not_match(client, equipo, con_pasos):
    headers, _ = equipo["admin"]
    _, directo = con_pasos
    resultado = ids(listar(client, headers, fecha_campo="en_proceso", desde="2026-01-01"))
    assert directo.id not in resultado


def test_without_days_the_date_field_does_not_filter(client, equipo, con_pasos):
    headers, _ = equipo["admin"]
    assert len(ids(listar(client, headers, fecha_campo="en_proceso"))) == 2


# --- Combinados -------------------------------------------------------------------


def test_new_filters_combine_with_the_existing_ones(client, session, equipo):
    headers, admin = equipo["admin"]
    _, luis = equipo["luis"]
    buscado = ticket(session, "VPN caída en piso 2", creado=utc(2026, 10, 5, 15), asignado=luis,
                     categoria="Red", prioridad="Alta", estado="Resuelto",
                     pasos=[("Resuelto", utc(2026, 10, 7, 15))])
    # Cada uno falla en un solo criterio.
    ticket(session, "VPN caída otra vez", creado=utc(2026, 10, 5, 15), asignado=admin,
           categoria="Red", prioridad="Alta", estado="Resuelto", pasos=[("Resuelto", utc(2026, 10, 7, 15))])
    ticket(session, "VPN caída de nuevo", creado=utc(2026, 10, 5, 15), asignado=luis,
           categoria="Red", prioridad="Baja", estado="Resuelto", pasos=[("Resuelto", utc(2026, 10, 7, 15))])
    ticket(session, "VPN caída en noviembre", creado=utc(2026, 10, 5, 15), asignado=luis,
           categoria="Red", prioridad="Alta", estado="Resuelto", pasos=[("Resuelto", utc(2026, 11, 7, 15))])
    ticket(session, "Impresora", creado=utc(2026, 10, 5, 15), asignado=luis,
           categoria="Red", prioridad="Alta", estado="Resuelto", pasos=[("Resuelto", utc(2026, 10, 7, 15))])

    resp = listar(client, headers, search="vpn", category="Red", priority="Alta", state="Resuelto",
                  assigned_to=luis.id, fecha_campo="resuelto", desde="2026-10-01", hasta="2026-10-31")
    assert ids(resp) == [buscado.id]


def test_my_tickets_combines_with_dates(client, session, equipo):
    headers, luis = equipo["luis"]
    mio = ticket(session, "VPN caída", creado=utc(2026, 10, 5, 15), asignado=luis)
    ticket(session, "VPN vieja", creado=utc(2026, 9, 5, 15), asignado=luis)
    ticket(session, "Impresora", creado=utc(2026, 10, 5, 15))
    assert ids(listar(client, headers, mios="true", desde="2026-10-01")) == [mio.id]


def test_pagination_counts_with_the_new_filters(client, session, equipo):
    headers, _ = equipo["admin"]
    _, luis = equipo["luis"]
    for dia in range(1, 6):
        ticket(session, f"Ticket del día {dia}", creado=utc(2026, 10, dia, 15), asignado=luis)
    resp = listar(client, headers, assigned_to=luis.id, desde="2026-10-02", limit=2)
    assert len(resp.json()) == 2
    assert resp.headers["X-Total-Count"] == "4"


# --- El chat no cambia ------------------------------------------------------------


def test_chat_still_answers_by_person_and_by_month(client, session, equipo, ia):
    headers, _ = equipo["admin"]
    _, luis = equipo["luis"]
    ticket(session, "VPN caída", creado=utc(2026, 10, 5, 15), asignado=luis, estado="Cerrado",
           pasos=[("Cerrado", utc(2026, 10, 9, 15))])
    ticket(session, "Impresora atascada", creado=utc(2026, 10, 6, 15), asignado=luis)

    # Como hoy: los pendientes de esa persona.
    de_luis = _respuesta(ask(client, headers, "tickets de Luis"), "directa")
    assert "Luis Mora" in de_luis and "Impresora atascada" in de_luis
    assert ia.calls == []
    # «en octubre» no lo resuelve el servidor (va a la IA, como antes): solo no se rompe.
    assert ask(client, headers, "tickets cerrados en octubre").status_code == 200
    # Los períodos que sí resuelve («este mes») siguen contando por la fecha del paso.
    ticket(session, "Teclado", creado=datetime.now(timezone.utc), estado="Cerrado",
           pasos=[("Cerrado", datetime.now(timezone.utc))])
    cerrados = _respuesta(ask(client, headers, "cuantos tickets se cerraron este mes"), "directa")
    assert "**1**" in cerrados


# --- Ayuda y documentación ----------------------------------------------------------


def test_help_and_api_docs_explain_the_filters():
    ayuda = (RAIZ / "frontend" / "ayuda.html").read_text(encoding="utf-8")
    assert "«Asignado a»" in ayuda and "«Fecha de creación»" in ayuda and "hora de Costa Rica" in ayuda
    assert "«Fecha de»:" not in ayuda
    api = (RAIZ / "docs" / "api.md").read_text(encoding="utf-8")
    for parametro in ("`assigned_to`", "`sin_asignar`", "`fecha_campo`", "`desde`", "`hasta`"):
        assert parametro in api, parametro


# --- «creado_antes» (Departamentos → «Más de 2 días en Nuevo») ------------------


def test_creado_antes_deja_solo_los_mas_viejos(client, session, equipo):
    headers, _ = equipo["admin"]
    viejo = ticket(session, "Ticket viejo", creado=utc(2026, 3, 1, 10))
    ticket(session, "Ticket nuevo", creado=utc(2026, 3, 5, 10))
    cerrado_viejo = ticket(session, "Cerrado viejo", creado=utc(2026, 2, 1, 10), estado="Cerrado")
    assert ids(listar(client, headers, creado_antes="2026-03-03T00:00:00Z")) == sorted([viejo.id, cerrado_viejo.id])
    assert ids(listar(client, headers, creado_antes="2026-03-03T00:00:00Z", state="Nuevo")) == [viejo.id]
    # Con zona de Costa Rica: 2026-03-01 04:00 −06:00 = 10:00 UTC (no es «antes»).
    assert ids(listar(client, headers, creado_antes="2026-03-01T04:00:00-06:00", state="Nuevo")) == []
    assert listar(client, headers, creado_antes="ayer").status_code == 422
