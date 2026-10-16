"""Tests de la creación de tickets por correo (sin servidor real)."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.models import Comment, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs

CONFIG = cs.ConfigCorreo(usuario="kcastro@data.cr", clave="x", app_url="http://ticketera.data.cr")


def crear_correo(remitente="Ana Pérez <ana@data.cr>", asunto="La impresora no imprime",
                 cuerpo="Desde ayer la impresora del segundo piso no imprime.",
                 msg_id="<m1@data.cr>", fecha=None, extra=None, html=None) -> bytes:
    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = "kcastro@data.cr"
    msg["Subject"] = asunto
    msg["Message-ID"] = msg_id
    msg["Date"] = format_datetime(fecha or datetime.now(timezone.utc) + timedelta(minutes=1))
    for clave, valor in (extra or {}).items():
        msg[clave] = valor
    msg.set_content(cuerpo)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


@pytest.fixture
def usuario(session):
    user = User(name="Ana Pérez", email="Ana@data.cr", role="Solicitante",
                password_hash="x", is_active=True)
    session.add(user)
    session.commit()
    return user


def procesar(session, crudo):
    return cs.procesar_correo(session, cs.leer_correo(crudo), CONFIG)


def test_known_user_gets_a_ticket_and_a_reply(session, usuario):
    resultado, respuesta = procesar(session, crear_correo(asunto="URGENTE: la impresora no imprime"))
    assert resultado == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.title == "URGENTE: la impresora no imprime"
    assert ticket.created_by_id == usuario.id
    assert ticket.category == "Hardware"
    assert ticket.priority == "Crítica"
    assert "segundo piso" in ticket.description
    assert "Recibido por correo de ana@data.cr" in ticket.description
    assert respuesta.para == "ana@data.cr"
    assert f"#{ticket.id}" in respuesta.asunto
    assert f"http://ticketera.data.cr/detalle.html?id={ticket.id}" in respuesta.texto
    assert respuesta.en_respuesta_a == "<m1@data.cr>"


def test_unknown_sender_is_asked_to_register(session):
    resultado, respuesta = procesar(session, crear_correo(remitente="Luis <luis@otro.com>"))
    assert resultado == "registro"
    assert session.scalars(select(Ticket)).first() is None
    assert respuesta.para == "luis@otro.com"
    assert "http://ticketera.data.cr/login.html?registro=1&email=luis@otro.com" in respuesta.texto
    assert "Hola Luis" in respuesta.texto

    # Un segundo correo el mismo día no vuelve a enviar el aviso.
    resultado, respuesta = procesar(session, crear_correo(remitente="luis@otro.com", msg_id="<m2@x>"))
    assert (resultado, respuesta) == ("ignorado", None)


def test_inactive_user_is_told_the_account_is_disabled(session, usuario):
    usuario.is_active = False
    session.commit()
    resultado, respuesta = procesar(session, crear_correo())
    assert resultado == "inactivo"
    assert "desactivada" in respuesta.texto
    assert session.scalars(select(Ticket)).first() is None


@pytest.mark.parametrize("extra,remitente", [
    ({"Auto-Submitted": "auto-replied"}, "ana@data.cr"),
    ({"Precedence": "bulk"}, "ana@data.cr"),
    ({}, "MAILER-DAEMON@data.cr"),
    ({}, "noreply@servicio.com"),
    ({}, "kcastro@data.cr"),
])
def test_automatic_or_own_mail_is_ignored(session, usuario, extra, remitente):
    resultado, respuesta = procesar(session, crear_correo(remitente=remitente, extra=extra))
    assert (resultado, respuesta) == ("ignorado", None)
    assert session.scalars(select(Ticket)).first() is None


def test_same_message_is_processed_only_once(session, usuario):
    crudo = crear_correo()
    assert procesar(session, crudo)[0] == "ticket"
    assert procesar(session, crudo) == ("repetido", None)
    assert len(session.scalars(select(Ticket)).all()) == 1


def test_reply_with_ticket_number_adds_a_comment(session, usuario):
    procesar(session, crear_correo())
    ticket = session.scalars(select(Ticket)).one()
    crudo = crear_correo(asunto=f"RE: Ticket #{ticket.id} creado: La impresora",
                         cuerpo="Ya probé reiniciarla.\n\nEl lunes, Mesa escribió:\n> texto viejo",
                         msg_id="<m3@data.cr>")
    resultado, respuesta = procesar(session, crudo)
    assert resultado == "comentario"
    comentario = session.scalars(select(Comment)).one()
    assert comentario.content == "Ya probé reiniciarla."
    assert comentario.author == "Ana Pérez"
    assert len(session.scalars(select(Ticket)).all()) == 1
    assert f"#{ticket.id}" in respuesta.asunto


def test_reply_to_someone_elses_ticket_creates_a_new_one(session, usuario):
    otro = Ticket(title="Ajeno", description="x", category="Red", priority="Baja")
    session.add(otro)
    session.commit()
    resultado, _ = procesar(session, crear_correo(asunto=f"Ticket #{otro.id} ayuda"))
    assert resultado == "ticket"
    assert len(session.scalars(select(Ticket)).all()) == 2


def test_short_subject_and_html_body(session, usuario):
    crudo = crear_correo(asunto="Re:", cuerpo="", html="<p>No tengo <b>internet</b></p><br>gracias")
    procesar(session, crudo)
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.title == cs.TITULO_POR_DEFECTO
    assert ticket.category == "Red"
    assert ticket.priority == "Media"


@pytest.mark.parametrize("asunto,cuerpo,categoria,prioridad", [
    ("Olvidé mi contraseña", "", "Accesos", "Media"),
    ("Consulta", "¿Cómo instalo Excel?", "Software", "Baja"),
    ("VPN no conecta", "no puedo trabajar", "Red", "Alta"),
    ("Hola", "algo raro", "Software", "Media"),
])
def test_classification(asunto, cuerpo, categoria, prioridad):
    cat, pri = cs.clasificar(asunto, cuerpo)
    assert (cat.value, pri.value) == (categoria, prioridad)


def test_config_from_env():
    assert cs.config_desde_entorno({}) is None
    assert cs.config_desde_entorno({"CORREO_ACTIVO": "1"}) is None
    cfg = cs.config_desde_entorno({"CORREO_ACTIVO": "si", "CORREO_USUARIO": "kcastro@data.cr",
                                   "APP_URL": "http://10.0.0.5:8000/"})
    assert cfg.usuario == "kcastro@data.cr"
    assert cfg.app_url == "http://10.0.0.5:8000"
    assert cfg.imap_servidor == "outlook.office365.com"
    assert not cfg.usa_oauth


class FakeImap:
    def __init__(self, mensajes):
        self.mensajes = mensajes
        self.seleccion = None
        self.cerrado = False

    def select(self, carpeta, readonly=False):
        self.seleccion = (carpeta, readonly)
        return "OK", [b"1"]

    def uid(self, comando, *args):
        if comando == "SEARCH":
            return "OK", [b" ".join(str(i).encode() for i in range(1, len(self.mensajes) + 1))]
        uid = int(args[0])
        assert args[1] == "(BODY.PEEK[])"  # nunca marca como leído
        return "OK", [(b"1 (BODY[] {10}", self.mensajes[uid - 1]), b")"]

    def logout(self):
        self.cerrado = True


def test_revisar_buzon_processes_new_mail_and_sends_replies(engine, session, usuario):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    viejo = crear_correo(msg_id="<viejo@x>", fecha=datetime.now(timezone.utc) - timedelta(days=2))
    nuevo = crear_correo(msg_id="<nuevo@x>")
    desconocido = crear_correo(remitente="otro@x.com", msg_id="<otro@x>")
    imap = FakeImap([viejo, nuevo, desconocido])
    enviados = []

    conteo = cs.revisar_buzon(factory, CONFIG, conectar=lambda c: imap,
                              enviar=lambda c, r: enviados.append(r))
    assert conteo == {"ticket": 1, "registro": 1}
    assert imap.seleccion == ("INBOX", True)
    assert imap.cerrado
    assert [r.para for r in enviados] == ["ana@data.cr", "otro@x.com"]

    # Segunda revisión: no repite nada.
    enviados.clear()
    conteo = cs.revisar_buzon(factory, CONFIG, conectar=lambda c: imap,
                              enviar=lambda c, r: enviados.append(r))
    assert conteo == {"repetido": 2}
    assert enviados == []
    assert session.scalar(select(ProcessedEmail).where(
        ProcessedEmail.message_id == cs.MARCA_INICIO)) is not None


def test_send_failure_does_not_stop_processing(engine, usuario):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    imap = FakeImap([crear_correo(msg_id="<a@x>"), crear_correo(msg_id="<b@x>")])

    def falla(c, r):
        raise OSError("sin conexión")

    assert cs.revisar_buzon(factory, CONFIG, conectar=lambda c: imap, enviar=falla) == {"ticket": 2}


def test_reply_message_is_marked_automatic(monkeypatch):
    enviados = []

    class FakeSmtp:
        def __init__(self, *a, **k): pass
        def starttls(self): pass
        def login(self, u, p): enviados.append(("login", u))
        def send_message(self, msg): enviados.append(msg)
        def quit(self): pass

    monkeypatch.setattr(cs.smtplib, "SMTP", FakeSmtp)
    cs.enviar_respuesta(CONFIG, cs.Respuesta(para="ana@data.cr", asunto="Hola", texto="t",
                                             en_respuesta_a="<m1@x>"))
    msg = enviados[1]
    assert msg["Auto-Submitted"] == "auto-replied"
    assert msg["In-Reply-To"] == "<m1@x>"
    assert msg["From"] == "kcastro@data.cr"
