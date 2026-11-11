"""Cierre automático de tickets Resuelto (backend/services/cierre_service.py):
los días de lunes a sábado (el domingo no cuenta), la reapertura cuando
responde el solicitante (en la app o por correo, y no cuando comenta IT), el
cierre hecho por «Sistema» con su correo, el cron y los tickets que ya
estaban resueltos."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.migrate_add_ticket_resuelto_en import migrate_add_ticket_resuelto_en
from backend.models import History, Ticket, User
from backend.services import cierre_service as cierre
from backend.services import correo_service as cs
from backend.tests.test_asistente import login_as
from backend.tests.test_correo import CONFIG, crear_correo, procesar

CR = timezone(timedelta(hours=-6))


def cr(dia, hora=10, minuto=0):
    """Una fecha de noviembre de 2026 en la hora de Costa Rica (16 = lunes)."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=CR)


@pytest.fixture(autouse=True)
def encendido(monkeypatch):
    monkeypatch.setenv("CIERRE_AUTOMATICO", "true")
    monkeypatch.delenv("CIERRE_DIAS", raising=False)
    return monkeypatch


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def gente(session):
    personas = {
        "ana": User(name="Ana Pérez", email="ana@data.cr", role="Solicitante"),
        "pedro": User(name="Pedro Rojas", email="pedro@data.cr", role="Técnico"),
        "admin": User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador"),
    }
    session.add_all(personas.values())
    session.commit()
    return personas


def resuelto(session, gente, cuando=None, asignado="pedro", creador="ana"):
    ticket = Ticket(title="La impresora no imprime", description="No imprime desde ayer.",
                    category="Hardware", priority="Media", state="Resuelto",
                    created_by_id=gente[creador].id, assigned_to_id=gente[asignado].id,
                    resuelto_en=(cuando or datetime.now(timezone.utc)).astimezone(timezone.utc))
    session.add(ticket)
    session.commit()
    return ticket


# --- Los días: de lunes a sábado, 24 horas -------------------------------------


@pytest.mark.parametrize("desde,hasta", [
    (cr(16, 10), cr(19, 10)),          # lunes 10:00 → jueves 10:00
    (cr(13, 16), cr(17, 16)),          # viernes 16:00 → martes 16:00 (el sábado cuenta)
    (cr(14, 15), cr(18, 15)),          # sábado 15:00 → miércoles 15:00
    (cr(15, 11), cr(19, 0)),           # domingo 11:00 → jueves 00:00 (empieza el lunes)
    (cr(12, 23, 30), cr(16, 23, 30)),  # jueves 23:30 → lunes 23:30 (salta el domingo)
])
def test_tres_dias_de_lunes_a_sabado(desde, hasta):
    assert cierre.fecha_de_cierre(desde, 3) == hasta.astimezone(timezone.utc)


def test_el_domingo_no_cuenta():
    # Resuelto el sábado a las 23:00: una hora del sábado y 23 horas del lunes.
    assert cierre.fecha_de_cierre(cr(14, 23), 1) == cr(16, 23).astimezone(timezone.utc)
    assert cierre.DIAS_QUE_CUENTAN == frozenset(range(6))


def test_acepta_decimales_y_fechas_sin_zona():
    assert cierre.fecha_de_cierre(cr(16, 10), 0.5) == cr(16, 22).astimezone(timezone.utc)
    sin_zona = datetime(2026, 11, 16, 16, 0)  # 10:00 en Costa Rica, guardado en UTC sin zona
    assert cierre.fecha_de_cierre(sin_zona, 1) == cr(17, 10).astimezone(timezone.utc)


@pytest.mark.parametrize("valor,esperado,texto", [
    (None, 3.0, "3 días"), ("5", 5.0, "5 días"), ("1", 1.0, "1 día"), ("0,5", 0.5, "0,5 días"),
    ("x", 3.0, "3 días"), ("0", 3.0, "3 días"), ("-1", 3.0, "3 días"),
])
def test_cierre_dias_desde_el_entorno(valor, esperado, texto):
    env = {} if valor is None else {"CIERRE_DIAS": valor}
    assert cierre.dias(env) == esperado
    assert cierre.texto_dias(env) == texto


@pytest.mark.parametrize("valor,esperado", [(None, False), ("false", False), ("true", True), ("1", True)])
def test_cierre_automatico_apagado_por_defecto(valor, esperado):
    assert cierre.activo({} if valor is None else {"CIERRE_AUTOMATICO": valor}) is esperado


# --- Cerrar los vencidos ---------------------------------------------------------


def test_cierra_el_vencido_como_sistema_y_avisa(session, factory, gente):
    ticket = resuelto(session, gente, cr(16, 10))
    avisados = []
    cerrados = cierre.revisar(factory, ahora=cr(19, 10, 1), avisar=lambda s, t, env=None: avisados.append(t.id))
    assert cerrados == [ticket.id] and avisados == [ticket.id]
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Cerrado"
    assert session.get(Ticket, ticket.id).resuelto_en is None
    entrada = session.scalars(select(History).where(History.ticket_id == ticket.id)).one()
    assert (entrada.action, entrada.field, entrada.old_value, entrada.new_value) == (
        "Cierre automático", "state", "Resuelto", "Cerrado")
    assert (entrada.author, entrada.author_id) == ("Sistema", None)


def test_no_cierra_antes_de_tiempo_ni_el_domingo(session, factory, gente):
    ticket = resuelto(session, gente, cr(13, 16))  # viernes 16:00 → martes 16:00
    assert cierre.revisar(factory, ahora=cr(16, 16), avisar=lambda *a, **k: None) == []
    assert cierre.revisar(factory, ahora=cr(17, 15, 59), avisar=lambda *a, **k: None) == []
    assert cierre.revisar(factory, ahora=cr(17, 16), avisar=lambda *a, **k: None) == [ticket.id]


def test_con_la_funcion_apagada_no_cierra(session, factory, gente, encendido):
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    resuelto(session, gente, cr(1, 10))
    assert cierre.revisar(factory, ahora=cr(30, 10), avisar=lambda *a, **k: None) == []


def test_tope_de_cierres_por_vuelta(session, factory, gente):
    for _ in range(4):
        resuelto(session, gente, cr(9, 10))
    sin_aviso = lambda *a, **k: None  # noqa: E731
    assert len(cierre.revisar(factory, ahora=cr(19, 10), maximo=3, avisar=sin_aviso)) == 3
    assert len(cierre.revisar(factory, ahora=cr(19, 10), maximo=3, avisar=sin_aviso)) == 1


def test_si_el_aviso_falla_el_ticket_queda_cerrado(session, factory, gente):
    ticket = resuelto(session, gente, cr(9, 10))

    def falla(*_a, **_k):
        raise RuntimeError("sin red")

    assert cierre.revisar(factory, ahora=cr(19, 10), avisar=falla) == [ticket.id]
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Cerrado"


def test_un_resuelto_sin_fecha_empieza_a_contar_ahora(session, factory, gente):
    ticket = resuelto(session, gente)
    ticket.resuelto_en = None
    session.commit()
    assert cierre.revisar(factory, ahora=cr(16, 10), avisar=lambda *a, **k: None) == []
    session.expire_all()
    assert session.get(Ticket, ticket.id).resuelto_en == cr(16, 10).astimezone(timezone.utc)


# --- Tickets que ya estaban en Resuelto (la migración) ------------------------------


def test_la_migracion_pone_ahora_a_los_resueltos_sin_tocar_updated_at(engine, session, gente):
    viejo = resuelto(session, gente, cr(1, 10))
    viejo.resuelto_en = None
    en_proceso = Ticket(title="Otro ticket", description="x", category="Red", priority="Baja",
                        state="En proceso", created_by_id=gente["ana"].id)
    session.add(en_proceso)
    session.commit()
    antes = session.get(Ticket, viejo.id).updated_at
    migrate_add_ticket_resuelto_en(engine)
    migrate_add_ticket_resuelto_en(engine)  # idempotente
    session.expire_all()
    ticket = session.get(Ticket, viejo.id)
    assert ticket.resuelto_en is not None
    assert abs(ticket.resuelto_en - datetime.now(timezone.utc)) < timedelta(minutes=1)
    assert ticket.updated_at == antes
    assert session.get(Ticket, en_proceso.id).resuelto_en is None


def test_la_migracion_agrega_la_columna_a_una_base_vieja(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    viejo = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    with viejo.connect() as conn:
        conn.execute(text("CREATE TABLE tickets (id INTEGER PRIMARY KEY, state VARCHAR(20), "
                          "updated_at DATETIME)"))
        conn.execute(text("INSERT INTO tickets (state, updated_at) VALUES ('Resuelto', '2026-11-01')"))
        conn.commit()
    assert migrate_add_ticket_resuelto_en(viejo) is True
    assert "resuelto_en" in [c["name"] for c in inspect(viejo).get_columns("tickets")]
    with viejo.connect() as conn:
        assert conn.execute(text("SELECT resuelto_en FROM tickets")).scalar() is not None
    assert migrate_add_ticket_resuelto_en(viejo) is False


# --- Reapertura: responde el solicitante -------------------------------------------


def headers(client, session, rol, correo, nombre):
    return login_as(client, session, rol, correo, nombre)


def ticket_resuelto_por_la_app(client, session):
    ana = headers(client, session, "Solicitante", "ana2@data.cr", "Ana Pérez")
    pedro = headers(client, session, "Técnico", "pedro2@data.cr", "Pedro Rojas")
    solicitante = session.scalar(select(User).where(User.email == "ana2@data.cr"))
    tecnico = session.scalar(select(User).where(User.email == "pedro2@data.cr"))
    ticket = Ticket(title="La impresora no imprime", description="No imprime.", category="Hardware",
                    priority="Media", created_by_id=solicitante.id, assigned_to_id=tecnico.id)
    session.add(ticket)
    session.commit()
    resp = client.patch(f"/api/tickets/{ticket.id}/state", json={"state": "Resuelto"}, headers=pedro)
    assert resp.status_code == 200, resp.text
    return ticket, ana, pedro


def test_pasar_a_resuelto_guarda_la_fecha_y_la_api_dice_cuando_se_cierra(client, session):
    ticket, ana, _ = ticket_resuelto_por_la_app(client, session)
    session.expire_all()
    guardado = session.get(Ticket, ticket.id)
    assert guardado.resuelto_en is not None
    datos = client.get(f"/api/tickets/{ticket.id}", headers=ana).json()
    esperado = cierre.fecha_de_cierre(guardado.resuelto_en, 3)
    assert datetime.fromisoformat(datos["cierre_automatico_en"]) == esperado


def test_sin_la_funcion_la_api_no_promete_un_cierre(client, session, encendido):
    ticket, ana, _ = ticket_resuelto_por_la_app(client, session)
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    assert client.get(f"/api/tickets/{ticket.id}", headers=ana).json()["cierre_automatico_en"] is None


def test_respuesta_del_solicitante_en_la_app_lo_reabre(client, session):
    ticket, ana, _ = ticket_resuelto_por_la_app(client, session)
    resp = client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Sigue sin imprimir."},
                       headers=ana)
    assert resp.status_code == 201
    session.expire_all()
    guardado = session.get(Ticket, ticket.id)
    assert guardado.state == "En proceso" and guardado.resuelto_en is None
    entrada = session.scalars(select(History).where(History.ticket_id == ticket.id,
                                                    History.action == "Reabierto por respuesta")).one()
    assert (entrada.old_value, entrada.new_value, entrada.author) == ("Resuelto", "En proceso", "Ana Pérez")
    assert client.get(f"/api/tickets/{ticket.id}", headers=ana).json()["cierre_automatico_en"] is None


def test_comentario_de_it_no_lo_reabre(client, session):
    ticket, _, pedro = ticket_resuelto_por_la_app(client, session)
    admin = headers(client, session, "Administrador", "admin2@data.cr", "Admin")
    for quien in (pedro, admin):
        assert client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Quedó listo."},
                           headers=quien).status_code == 201
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Resuelto"
    assert session.get(Ticket, ticket.id).resuelto_en is not None


def test_el_solicitante_que_tambien_es_el_asignado_no_lo_reabre(session, factory, gente):
    from backend.schemas import CommentCreate
    from backend.services import ticket_service

    ticket = resuelto(session, gente, asignado="pedro", creador="pedro")
    ticket_service.create_comment(session, ticket.id, CommentCreate(content="Listo."), gente["pedro"])
    assert session.get(Ticket, ticket.id).state == "Resuelto"


def test_con_la_funcion_apagada_el_comentario_no_lo_reabre(client, session, encendido):
    ticket, ana, _ = ticket_resuelto_por_la_app(client, session)
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Gracias."}, headers=ana)
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Resuelto"


def test_respuesta_del_solicitante_por_correo_lo_reabre(session, gente):
    ticket = resuelto(session, gente)
    respuesta = crear_correo(asunto=f"RE: [Ticket #{ticket.id}] El ticket #{ticket.id} pasó a «Resuelto»",
                             cuerpo="Sigue igual, no imprime.", msg_id="<respuesta@data.cr>")
    assert procesar(session, respuesta, CONFIG)[0] == "comentario"
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "En proceso"
    assert session.scalars(select(History).where(History.action == "Reabierto por respuesta")).one()


def test_respuesta_de_it_por_correo_no_lo_reabre(session, gente):
    ticket = resuelto(session, gente)
    respuesta = crear_correo(remitente="pedro@data.cr", nombre="Pedro Rojas",
                             asunto=f"RE: [Ticket #{ticket.id}] Nuevo comentario",
                             cuerpo="Ya quedó, revisen por favor.", msg_id="<it@data.cr>")
    assert procesar(session, respuesta, CONFIG)[0] == "comentario"
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Resuelto"


def test_volver_a_resolver_reinicia_el_contador(client, session):
    ticket, ana, pedro = ticket_resuelto_por_la_app(client, session)
    session.expire_all()
    primero = session.get(Ticket, ticket.id).resuelto_en
    client.post(f"/api/tickets/{ticket.id}/comments", json={"content": "Sigue igual."}, headers=ana)
    assert client.patch(f"/api/tickets/{ticket.id}/state", json={"state": "Resuelto"},
                        headers=pedro).status_code == 200
    session.expire_all()
    segundo = session.get(Ticket, ticket.id).resuelto_en
    assert segundo is not None and segundo >= primero


# --- Correos ---------------------------------------------------------------------------


@pytest.fixture
def correos(monkeypatch):
    enviados = []

    class Cliente:
        def enviar(self, aviso, registrar=None):
            enviados.append(aviso)

    monkeypatch.setenv("CORREO_ACTIVO", "1")
    monkeypatch.setenv("CORREO_USUARIO", "kcastro@data.cr")
    monkeypatch.setenv("APP_URL", "https://tickets-americandata.vercel.app")
    monkeypatch.setattr(cs, "crear_cliente", lambda config, fabrica: Cliente())
    return enviados


def test_correo_de_cierre_al_solicitante_y_al_asignado(session, gente, correos):
    ticket = resuelto(session, gente)
    cs.avisar_cierre_automatico(session, ticket)
    assert sorted(a.para for a in correos) == ["ana@data.cr", "pedro@data.cr"]
    for aviso in correos:
        assert aviso.asunto == f"[Ticket #{ticket.id}] El ticket #{ticket.id} se cerró automáticamente"
        assert (f"El ticket #{ticket.id} se cerró automáticamente por falta de respuesta. Si el problema "
                "continúa, envíe un nuevo correo para crear otro ticket.") in aviso.texto


def test_un_solo_correo_si_el_solicitante_es_el_asignado(session, gente, correos):
    ticket = resuelto(session, gente, asignado="pedro", creador="pedro")
    cs.avisar_cierre_automatico(session, ticket)
    assert [a.para for a in correos] == ["pedro@data.cr"]


def test_sin_la_funcion_no_sale_el_correo_de_cierre(session, gente, correos, encendido):
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    cs.avisar_cierre_automatico(session, resuelto(session, gente))
    assert correos == []


def test_el_aviso_de_resuelto_al_solicitante_explica_el_cierre(session, gente, correos, encendido):
    encendido.setenv("AVISAR_ESTADOS", "true")
    ticket = resuelto(session, gente)
    cs.avisar_estado(session, ticket, "En proceso", gente["pedro"])
    frase = ("Si el problema continúa, responda este correo. Si no recibimos respuesta en 3 días, "
             "el ticket se cerrará automáticamente.")
    assert [a.para for a in correos] == ["ana@data.cr"]  # no a quien lo resolvió
    assert frase in correos[0].texto


def test_el_aviso_de_resuelto_al_asignado_no_lleva_la_frase(session, gente, correos, encendido):
    encendido.setenv("AVISAR_ESTADOS", "true")
    ticket = resuelto(session, gente)
    cs.avisar_estado(session, ticket, "En proceso", gente["admin"])
    textos = {a.para: a.texto for a in correos}
    assert "se cerrará automáticamente" in textos["ana@data.cr"]
    assert "se cerrará automáticamente" not in textos["pedro@data.cr"]


def test_sin_la_funcion_el_aviso_de_resuelto_no_lleva_la_frase(session, gente, correos, encendido):
    encendido.setenv("AVISAR_ESTADOS", "true")
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    cs.avisar_estado(session, resuelto(session, gente), "En proceso", gente["pedro"])
    assert "se cerrará automáticamente" not in correos[0].texto


# --- El cron ----------------------------------------------------------------------------


def test_el_cron_cierra_aunque_el_correo_este_apagado(client, session, gente, encendido):
    encendido.setenv("CRON_SECRET", "s3creto")
    encendido.delenv("CORREO_ACTIVO", raising=False)
    encendido.setenv("CORREO_PROVEEDOR", "graph")
    ticket = resuelto(session, gente, datetime.now(timezone.utc) - timedelta(days=10))
    from backend.database import get_session
    from backend.main import app

    fabrica = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    llamados = []
    original = cierre.revisar
    encendido.setattr(cierre, "revisar", lambda **k: llamados.append(k) or original(
        fabrica, limite=k.get("limite"), avisar=lambda *a, **kw: None))
    assert app.dependency_overrides.get(get_session) is not None
    resp = client.post("/api/cron/correo", headers={"Authorization": "Bearer s3creto"})
    assert resp.status_code == 503  # el correo está apagado, pero el cierre ya corrió
    assert llamados and llamados[0]["limite"] == cierre.LIMITE_CRON
    session.expire_all()
    assert session.get(Ticket, ticket.id).state == "Cerrado"


def test_el_cron_le_deja_al_correo_el_tiempo_que_queda(client, encendido, monkeypatch):
    encendido.setenv("CRON_SECRET", "s3creto")
    pedido = {}
    monkeypatch.setattr(cierre, "revisar", lambda **k: [])
    monkeypatch.setattr(cs, "revisar_una_vez", lambda limite=None: pedido.setdefault("limite", limite) and {})
    resp = client.post("/api/cron/correo", headers={"Authorization": "Bearer s3creto"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["cierre"] == 0
    assert 5.0 <= pedido["limite"] <= cs.LIMITE_CRON


def test_el_hilo_no_arranca_en_vercel_ni_apagado(encendido):
    encendido.setenv("VERCEL", "1")
    assert cierre.iniciar_hilo() is False
    encendido.delenv("VERCEL")
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    assert cierre.iniciar_hilo() is False


# --- El chat ---------------------------------------------------------------------------

from backend.tests.test_asistente_app import preguntar  # noqa: E402
from backend.tests.test_asistente_interpretacion import _respuesta, ia  # noqa: E402,F401


@pytest.mark.parametrize("pregunta", [
    "cuando se cierra un ticket resuelto",
    "por que se cerro mi ticket solo",
    "que es el cierre automatico",
    "cuanto tarda en cerrarse un ticket resuelto",
    "los tickets se cierran solos?",
])
def test_el_chat_explica_el_cierre_automatico(client, session, ia, pregunta):  # noqa: F811
    respuesta = _respuesta(preguntar(client, session, "Solicitante", pregunta), "directa")
    assert "no responde en 3 días" in respuesta
    assert "el domingo no cuenta" in respuesta
    assert "Cerrado automáticamente por falta de respuesta" in respuesta
    assert ia.calls == []


def test_el_chat_usa_los_dias_configurados(client, session, ia, encendido):  # noqa: F811
    encendido.setenv("CIERRE_DIAS", "5")
    assert "no responde en 5 días" in _respuesta(
        preguntar(client, session, "Técnico", "que es el cierre automatico"), "directa")


def test_el_chat_dice_si_no_esta_activo(client, session, ia, encendido):  # noqa: F811
    encendido.setenv("CIERRE_AUTOMATICO", "false")
    assert "no está activo" in _respuesta(
        preguntar(client, session, "Técnico", "que es el cierre automatico"), "directa")


@pytest.mark.parametrize("pregunta,esperado", [
    ("como cierro un ticket", "el estado de sus tickets lo cambian"),
    ("como cierro sesion", "elija «Cerrar sesión»"),
])
def test_el_chat_no_confunde_cerrar_un_ticket_ni_la_sesion(client, session, ia, pregunta, esperado):  # noqa: F811
    assert esperado in _respuesta(preguntar(client, session, "Solicitante", pregunta), "directa")
