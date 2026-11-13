"""Historial agrupado por persona: GET /api/history/resumen y los filtros
nuevos de GET /api/history (persona, periodo, buscar, limit, offset)."""

from datetime import datetime, timedelta, timezone

from backend.constants import TicketCategory, TicketPriority, UserRole
from backend.models import History, ItArea, Ticket, User
from backend.services import historial_service, metricas_service

AHORA = datetime.now(timezone.utc)


def nuevo_ticket(session, titulo: str) -> Ticket:
    ticket = Ticket(
        title=titulo,
        description="Descripción suficientemente larga para la prueba.",
        category=TicketCategory.SOFTWARE.value,
        priority=TicketPriority.MEDIUM.value,
    )
    session.add(ticket)
    session.commit()
    return ticket


def cambio(session, ticket, autor: User | None, hace: timedelta, action="commented", **datos) -> None:
    session.add(History(
        ticket_id=ticket.id,
        action=action,
        author=autor.name if autor else "Sistema",
        author_id=autor.id if autor else None,
        created_at=AHORA - hace,
        **datos,
    ))
    session.commit()


def usuario(session, nombre, rol, area=None) -> User:
    u = User(name=nombre, email=f"{nombre.split()[0].lower()}@ejemplo.com", role=rol,
             is_active=True, area_id=area.id if area else None)
    session.add(u)
    session.commit()
    return u


def preparar(session):
    redes = session.query(ItArea).filter_by(name="Redes e Infraestructura").one_or_none()
    if redes is None:
        redes = ItArea(name="Redes e Infraestructura")
        session.add(redes)
        session.commit()
    daniel = usuario(session, "Daniel Sáenz", UserRole.TECHNICIAN.value, redes)
    sofia = usuario(session, "Sofía Solicitante", UserRole.REQUESTER.value)
    impresora = nuevo_ticket(session, "Impresora sin conexión")
    correo = nuevo_ticket(session, "Correo no sincroniza")
    # Daniel: 3 hoy (2 en la impresora), 1 hace 10 días.
    cambio(session, impresora, daniel, timedelta(minutes=5), new_value="hola")
    cambio(session, impresora, daniel, timedelta(minutes=4), action="Cambio de estado",
           field="state", old_value="Nuevo", new_value="En proceso")
    cambio(session, correo, daniel, timedelta(minutes=3), action="assigned",
           field="assigned_to_id", new_value="Daniel Sáenz")
    cambio(session, correo, daniel, timedelta(days=10))
    # Sofía: 1 hace 3 días. Sistema: 1 cierre automático hace 20 días.
    cambio(session, correo, sofia, timedelta(days=3))
    cambio(session, impresora, None, timedelta(days=20), action="Cierre automático",
           field="state", old_value="Resuelto", new_value="Cerrado")
    return daniel, sofia, impresora, correo


def test_resumen_lista_personas_con_sistema_ordenadas_por_cambios(auth_client, session):
    daniel, sofia, _, _ = preparar(session)

    r = auth_client.get("/api/history/resumen", params={"periodo": "30"})

    assert r.status_code == 200
    datos = r.json()
    assert datos["periodo"] == "30"
    personas = {p["clave"]: p for p in datos["personas"]}
    assert personas[str(daniel.id)]["cambios"] == 4
    assert personas[str(daniel.id)]["rol"] == "Técnico"
    assert personas[str(daniel.id)]["departamento"] == "Redes e Infraestructura"
    assert personas[str(sofia.id)]["cambios"] == 1
    assert personas[str(sofia.id)]["departamento"] is None
    assert personas["sistema"] == {
        "clave": "sistema", "user_id": None, "nombre": "Sistema",
        "rol": "Cambios automáticos", "departamento": None, "cambios": 1,
    }
    cantidades = [p["cambios"] for p in datos["personas"]]
    assert cantidades == sorted(cantidades, reverse=True)
    assert datos["personas"][0]["clave"] == str(daniel.id)
    assert datos["total"] == sum(cantidades)


def test_el_periodo_cuenta_solo_sus_cambios_y_deja_a_los_demas_en_cero(auth_client, session):
    daniel, sofia, _, _ = preparar(session)

    hoy = auth_client.get("/api/history/resumen", params={"periodo": "hoy"}).json()
    siete = auth_client.get("/api/history/resumen", params={"periodo": "7"}).json()

    por_clave = lambda d: {p["clave"]: p["cambios"] for p in d["personas"]}
    assert por_clave(hoy)[str(daniel.id)] == 3
    assert por_clave(hoy)[str(sofia.id)] == 0
    assert por_clave(hoy)["sistema"] == 0
    assert por_clave(siete)[str(sofia.id)] == 1
    assert por_clave(siete)[str(daniel.id)] == 3


def test_por_defecto_el_periodo_es_de_7_dias(auth_client, session):
    preparar(session)
    datos = auth_client.get("/api/history/resumen").json()
    assert datos["periodo"] == "7"
    inicio = metricas_service.limites_utc(metricas_service.hoy() - timedelta(days=6), metricas_service.hoy())[0]
    assert datos["desde"].startswith(inicio.isoformat()[:16])


def test_cajas_de_la_persona_y_con_busqueda(auth_client, session):
    daniel, _, impresora, _ = preparar(session)

    cajas = auth_client.get(
        "/api/history/resumen", params={"periodo": "30", "persona": daniel.id}
    ).json()["cajas"]
    assert cajas == {"cambios": 4, "tickets": 2, "comentarios": 2, "cambios_estado": 1}

    por_numero = auth_client.get(
        "/api/history/resumen", params={"periodo": "30", "persona": daniel.id, "buscar": f"#{impresora.id}"}
    ).json()["cajas"]
    assert por_numero == {"cambios": 2, "tickets": 1, "comentarios": 1, "cambios_estado": 1}

    por_titulo = auth_client.get(
        "/api/history/resumen", params={"periodo": "30", "buscar": "correo"}
    ).json()["cajas"]
    assert por_titulo["tickets"] == 1
    assert por_titulo["cambios"] == 3  # 2 de Daniel y 1 de Sofía

    sistema = auth_client.get(
        "/api/history/resumen", params={"periodo": "30", "persona": "sistema"}
    ).json()["cajas"]
    assert sistema == {"cambios": 1, "tickets": 1, "comentarios": 0, "cambios_estado": 1}


def test_listado_filtra_por_persona_periodo_y_busqueda(auth_client, session):
    daniel, sofia, impresora, correo = preparar(session)

    hoy = auth_client.get("/api/history", params={"persona": daniel.id, "periodo": "hoy"}).json()
    assert [e["action"] for e in hoy] == ["assigned", "Cambio de estado", "commented"]
    assert {e["author_id"] for e in hoy} == {daniel.id}

    sistema = auth_client.get("/api/history", params={"persona": "sistema", "periodo": "30"}).json()
    assert [e["action"] for e in sistema] == ["Cierre automático"]

    busqueda = auth_client.get("/api/history", params={"periodo": "30", "buscar": "impresora"}).json()
    assert {e["ticket_id"] for e in busqueda} == {impresora.id}
    assert busqueda[0]["ticket_title"] == "Impresora sin conexión"

    numero = auth_client.get("/api/history", params={"periodo": "30", "buscar": str(correo.id)}).json()
    assert {e["ticket_id"] for e in numero} == {correo.id}


def test_listado_por_paginas_para_ver_mas(auth_client, session):
    daniel, *_ = preparar(session)
    todos = auth_client.get("/api/history", params={"persona": daniel.id}).json()
    assert len(todos) == 4

    primera = auth_client.get("/api/history", params={"persona": daniel.id, "limit": 3}).json()
    segunda = auth_client.get("/api/history", params={"persona": daniel.id, "limit": 3, "offset": 3}).json()

    assert [e["id"] for e in primera + segunda] == [e["id"] for e in todos]
    assert len(segunda) == 1


def test_parametros_invalidos_responden_422(auth_client):
    assert auth_client.get("/api/history", params={"persona": "pepe"}).status_code == 422
    assert auth_client.get("/api/history", params={"periodo": "90"}).status_code == 422
    assert auth_client.get("/api/history", params={"limit": 0}).status_code == 422
    assert auth_client.get("/api/history", params={"limit": 201}).status_code == 422
    assert auth_client.get("/api/history/resumen", params={"persona": "x1"}).status_code == 422


def test_resumen_requiere_sesion(client):
    assert client.get("/api/history/resumen").status_code == 401


def test_el_solicitante_no_ve_el_resumen(client, session):
    from backend.auth import hash_password

    session.add(User(name="Sol", email="sol@ejemplo.com", role=UserRole.REQUESTER.value,
                     is_active=True, password_hash=hash_password("clave12345")))
    session.commit()
    token = client.post("/api/auth/login", json={"email": "sol@ejemplo.com", "password": "clave12345"}).json()["access_token"]
    r = client.get("/api/history/resumen", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_normalizar_persona():
    assert historial_service.normalizar_persona(None) == "todas"
    assert historial_service.normalizar_persona("Todas") == "todas"
    assert historial_service.normalizar_persona("sistema") == "sistema"
    assert historial_service.normalizar_persona("12") == 12
