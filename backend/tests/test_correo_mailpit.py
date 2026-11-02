"""Correos por Mailpit (``CORREO_PROVEEDOR=mailpit``, solo local).

Un servidor SMTP falso (``ServidorSMTP``, en un hilo y un puerto libre)
recibe lo que envía la app, como lo haría Mailpit:

* Los avisos salen por SMTP con los mismos destinatarios, asunto, texto y
  cabeceras que con Graph, y quedan registrados como ``aviso_app`` antes de
  enviarse.
* Con «mailpit» nunca se usa Graph: no se crea su cliente, no arranca el
  lector del buzón, el cron no lee y ``correo_login`` no inicia sesión.
* En Vercel siempre es «graph», diga lo que diga la variable."""

import socketserver
import threading
from email import message_from_bytes, policy

import pytest
from sqlalchemy import select

from backend import correo_login
from backend.models import Comment, ProcessedEmail
from backend.services import correo_service as cs
from backend.tests.test_correo import factory  # noqa: F401
from backend.tests.test_correo_reglas import APP_URL, YO, comentar, preparar


class _Sesion(socketserver.StreamRequestHandler):
    """Lo justo de SMTP (RFC 5321) para recibir un correo."""

    def _decir(self, linea: str) -> None:
        self.wfile.write(f"{linea}\r\n".encode())

    def handle(self):
        self._decir("220 falso ESMTP")
        remitente, para = "", []
        while linea := self.rfile.readline():
            orden = linea.decode().strip()
            verbo = orden[:4].upper()
            if verbo in ("EHLO", "HELO"):
                self._decir("250 falso")
            elif verbo == "MAIL":
                remitente, para = orden.split(":", 1)[1].strip(" <>"), []
                self._decir("250 OK")
            elif verbo == "RCPT":
                para.append(orden.split(":", 1)[1].strip(" <>"))
                self._decir("250 OK")
            elif verbo == "DATA":
                self._decir("354 adelante")
                datos = b""
                while (renglon := self.rfile.readline()) not in (b".\r\n", b""):
                    datos += renglon[1:] if renglon.startswith(b"..") else renglon
                self.server.recibidos.append(
                    (remitente, para, message_from_bytes(datos, policy=policy.default)))
                self._decir("250 recibido")
            elif verbo == "QUIT":
                self._decir("221 chau")
                return
            else:
                self._decir("250 OK")


class ServidorSMTP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Sesion)
        self.recibidos = []


@pytest.fixture
def smtp():
    servidor = ServidorSMTP()
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture
def entorno_mailpit(monkeypatch, smtp):
    """Como el .env local: Mailpit y los avisos encendidos, sin CORREO_ACTIVO."""
    for nombre in ("CORREO_ACTIVO", "VERCEL", "CORREO_MODO"):
        monkeypatch.delenv(nombre, raising=False)
    valores = {"CORREO_PROVEEDOR": "mailpit", "CORREO_USUARIO": YO, "APP_URL": APP_URL,
               "MAILPIT_HOST": "127.0.0.1", "MAILPIT_PUERTO": str(smtp.server_address[1]),
               "AVISAR_COMENTARIOS": "true", "AVISAR_ASIGNADO": "true",
               "CORREO_M365_TENANT": "t", "CORREO_M365_CLIENT_ID": "c"}
    for nombre, valor in valores.items():
        monkeypatch.setenv(nombre, valor)

    def sin_graph(*_args, **_kwargs):
        raise AssertionError("con CORREO_PROVEEDOR=mailpit no se usa Graph")

    monkeypatch.setattr(cs, "ClienteGraph", sin_graph)
    monkeypatch.setattr(cs, "ProveedorToken", sin_graph)
    return monkeypatch


# --- Proveedor según el entorno ----------------------------------------------------


@pytest.mark.parametrize("valor, esperado", [
    (None, "graph"), ("", "graph"), ("graph", "graph"), ("mailpit", "mailpit"),
    (" MailPit ", "mailpit"), ("smtp", "graph"),
])
def test_proveedor_por_defecto_graph(valor, esperado):
    env = {} if valor is None else {"CORREO_PROVEEDOR": valor}
    assert cs.proveedor_desde_entorno(env) == esperado


def test_en_vercel_siempre_graph_aunque_digan_mailpit():
    env = {"VERCEL": "1", "CORREO_PROVEEDOR": "mailpit", "CORREO_ACTIVO": "1", "CORREO_USUARIO": YO}
    assert cs.proveedor_desde_entorno(env) == "graph"
    config = cs.config_desde_entorno(env)
    assert config.proveedor == "graph"
    assert isinstance(cs.crear_cliente(config), cs.ClienteGraph)


def test_en_vercel_con_mailpit_y_sin_correo_activo_no_hay_correo():
    assert cs.config_desde_entorno({"VERCEL": "1", "CORREO_PROVEEDOR": "mailpit"}) is None


def test_mailpit_no_necesita_correo_activo_y_tiene_remitente_propio():
    config = cs.config_desde_entorno({"CORREO_PROVEEDOR": "mailpit"})
    assert (config.proveedor, config.usuario, config.smtp_host, config.smtp_puerto) == (
        "mailpit", cs.REMITENTE_MAILPIT, "mailpit", 1025)
    assert isinstance(cs.crear_cliente(config), cs.ClienteSMTP)


# --- Envío por SMTP ------------------------------------------------------------------


def _cliente(smtp):
    return cs.ClienteSMTP("127.0.0.1", smtp.server_address[1], YO)


def test_enviar_mismos_datos_y_cabeceras_que_graph(smtp):
    aviso = cs.Respuesta(para="ana@data.cr", asunto="[Ticket #7] Nuevo comentario en el ticket #7",
                         texto="Hola Ana Pérez,\n\nÁrbol «ñandú» — Mesa de ayuda", ticket_id=7)
    registrados = []
    _cliente(smtp).enviar(aviso, registrar=registrados.append)

    [(remitente, para, correo)] = smtp.recibidos
    assert (remitente, para) == (YO, ["ana@data.cr"])
    assert correo["From"] == YO and correo["To"] == "ana@data.cr"
    assert correo["Subject"] == aviso.asunto
    # SMTP viaja con CRLF; el texto es el mismo, con tildes y eñes.
    assert correo.get_content().replace("\r\n", "\n").rstrip("\n") == aviso.texto
    assert correo["X-Ticketera"] == "1"
    assert correo["X-Auto-Response-Suppress"] == "All"
    assert correo["Message-ID"].startswith("<") and correo["Message-ID"].endswith("@data.cr>")
    assert correo["In-Reply-To"] is None and correo["References"] is None  # correo nuevo
    assert registrados == [{"id": correo["Message-ID"], "internetMessageId": correo["Message-ID"],
                            "conversationId": ""}]


def test_responder_lleva_in_reply_to_y_references(smtp):
    aviso = cs.Respuesta(para="ana@data.cr", asunto="Ticket #3 cerrado", texto="x")
    _cliente(smtp).responder("<original@data.cr>", aviso, referencias=("<primero@data.cr>",))
    correo = smtp.recibidos[0][2]
    assert correo["In-Reply-To"] == "<original@data.cr>"
    assert correo["References"] == "<primero@data.cr> <original@data.cr>"
    assert correo["X-Ticketera"] == "1"


def test_cada_correo_tiene_su_message_id(smtp):
    cliente = _cliente(smtp)
    for _ in range(2):
        cliente.enviar(cs.Respuesta(para="ana@data.cr", asunto="a", texto="b"))
    assert len({c["Message-ID"] for _, _, c in smtp.recibidos}) == 2


def test_si_no_se_puede_registrar_no_se_envia(smtp):
    def falla(_borrador):
        raise RuntimeError("base caída")

    with pytest.raises(RuntimeError):
        _cliente(smtp).enviar(cs.Respuesta(para="ana@data.cr", asunto="a", texto="b"), registrar=falla)
    assert smtp.recibidos == []


# --- Comentario desde la app → Mailpit -------------------------------------------------


def test_comentario_en_la_app_avisa_por_mailpit(client, session, entorno_mailpit, smtp):
    headers, ticket = preparar(client, session)
    assert comentar(client, headers, ticket).status_code == 201

    para = sorted(p for _, destinatarios, _ in smtp.recibidos for p in destinatarios)
    assert para == ["ana@data.cr", "pedro@data.cr"]  # no a quien comentó
    for remitente, _, correo in smtp.recibidos:
        assert remitente == YO
        assert correo["Subject"] == f"[Ticket #{ticket.id}] Nuevo comentario en el ticket #{ticket.id}"
        texto = correo.get_content()
        assert "Kristin Castro agregó un comentario" in texto and "Ya pedí el repuesto." in texto
        assert f"{APP_URL}/detalle.html?id={ticket.id}" in texto
        assert correo["X-Ticketera"] == "1"

    # Mismo registro que con Graph: aviso_app con el Message-ID y el ticket.
    registros = session.scalars(select(ProcessedEmail).where(ProcessedEmail.result == "aviso_app")).all()
    assert sorted(r.message_id for r in registros) == sorted(c["Message-ID"] for _, _, c in smtp.recibidos)
    assert {(r.ticket_id, r.sender) for r in registros} == {(ticket.id, YO)}


def test_comentario_sin_avisar_comentarios_no_envia(client, session, entorno_mailpit, smtp):
    entorno_mailpit.setenv("AVISAR_COMENTARIOS", "false")
    headers, ticket = preparar(client, session)
    assert comentar(client, headers, ticket).status_code == 201
    assert smtp.recibidos == []


def test_mailpit_apagado_el_comentario_se_guarda_igual(client, session, entorno_mailpit, smtp, caplog):
    entorno_mailpit.setattr(cs.logger, "propagate", True)
    puerto = smtp.server_address[1]
    smtp.shutdown()
    smtp.server_close()  # nadie escucha en el puerto: conexión rechazada
    entorno_mailpit.setenv("MAILPIT_PUERTO", str(puerto))
    headers, ticket = preparar(client, session)
    with caplog.at_level("ERROR", logger=cs.logger.name):
        assert comentar(client, headers, ticket).status_code == 201
    assert [c.content for c in session.scalars(select(Comment))] == ["Ya pedí el repuesto."]
    assert f"No se pudo avisar por correo el comentario del ticket #{ticket.id}" in caplog.text


# --- Con Mailpit nunca se toca el buzón real ---------------------------------------------


def test_mailpit_no_arranca_el_lector_del_buzon(entorno_mailpit, factory):  # noqa: F811
    entorno_mailpit.setenv("CORREO_ACTIVO", "1")  # aunque el .env lo tenga encendido
    assert cs.iniciar_lector(factory) is False
    assert cs._hilo is None or not cs._hilo.is_alive()


def test_mailpit_el_cron_no_lee_el_buzon(entorno_mailpit, factory):  # noqa: F811
    entorno_mailpit.setenv("CORREO_ACTIVO", "1")
    with pytest.raises(cs.CorreoApagado):
        cs.revisar_una_vez(factory, crear=lambda *_: pytest.fail("no debe crear cliente"))


def test_mailpit_correo_login_no_inicia_sesion_en_microsoft(entorno_mailpit):
    salida = []
    iniciar = lambda *a, **k: pytest.fail("no debe iniciar sesión en Microsoft")  # noqa: E731
    assert correo_login.main(imprimir=salida.append, iniciar=iniciar) == 1
    assert "no usa el buzón de Microsoft" in salida[0]

