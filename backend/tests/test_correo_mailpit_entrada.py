"""Correos que llegan a Mailpit (``CORREO_PROVEEDOR=mailpit``, solo local).

Un Mailpit falso: el servidor SMTP de :mod:`test_correo_mailpit` recibe los
correos (los del script ``scripts/enviar_correo_prueba.py`` y las respuestas
de la app) y :class:`MailpitFalso` los sirve con la API de Mailpit
(``/api/v1/search``, ``/message/{ID}``, ``/headers``, ``/part/{PartID}``,
``PUT /messages`` y ``PUT /tags``). :class:`cs.ClienteMailpit` los convierte
al formato de Graph y pasan por el mismo filtro, tickets, comentarios y
adjuntos que los del buzón real.
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from backend.models import Attachment, Comment, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs
from backend.tests.test_correo import factory  # noqa: F401
from backend.tests.test_correo_mailpit import smtp  # noqa: F401
from backend.tests import imagenes

YO = "kcastro@data.cr"
DANIEL = "dsaenz@data.cr"
JPG = imagenes.jpeg(300, b"N")
PDF = b"%PDF-1.7\n" + b"0" * 2000 + b"\n%%EOF\n"

_ruta_script = Path(__file__).resolve().parents[2] / "scripts" / "enviar_correo_prueba.py"
_spec = importlib.util.spec_from_file_location("enviar_correo_prueba", _ruta_script)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


class MailpitFalso:
    """La API de Mailpit sobre lo que recibió el SMTP falso."""

    def __init__(self, servidor):
        self.servidor = servidor
        self.leidos: set[str] = set()
        self.etiquetas: dict[str, list[str]] = {}

    # Cada correo recibido es un ID: «m0», «m1»…
    def _correos(self):
        return {f"m{i}": correo for i, (_, _, correo) in enumerate(self.servidor.recibidos)}

    @staticmethod
    def _direcciones(valor):
        if not valor:
            return []
        return [{"Name": d.display_name, "Address": d.addr_spec} for d in valor.addresses]

    def _partes(self, correo):
        texto = html = ""
        adjuntos, en_linea = [], []
        for numero, parte in enumerate(correo.walk()):
            if parte.is_multipart():
                continue
            disposicion = parte.get_content_disposition()
            tipo = parte.get_content_type()
            if disposicion is None and tipo == "text/plain" and not texto:
                texto = parte.get_content()
                continue
            if disposicion is None and tipo == "text/html" and not html:
                html = parte.get_content()
                continue
            datos = {"PartID": str(numero), "FileName": parte.get_filename() or "", "ContentType": tipo,
                     "ContentID": (parte.get("Content-ID") or "").strip("<>"),
                     "Size": len(parte.get_payload(decode=True) or b"")}
            (adjuntos if disposicion == "attachment" else en_linea).append(datos)
        return texto, html, adjuntos, en_linea

    def _resumen(self, id_, correo):
        _, _, adjuntos, _ = self._partes(correo)
        fecha = parsedate_to_datetime(correo["Date"])
        return {"ID": id_, "MessageID": correo["Message-ID"].strip("<>"), "Read": id_ in self.leidos,
                "From": self._direcciones(correo["From"])[0], "To": self._direcciones(correo["To"]),
                "Cc": self._direcciones(correo["Cc"]), "Bcc": [], "Subject": correo["Subject"],
                "Created": fecha.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "Attachments": len(adjuntos), "Tags": self.etiquetas.get(id_, [])}

    def _completo(self, id_, correo):
        texto, html, adjuntos, en_linea = self._partes(correo)
        return {**self._resumen(id_, correo), "Date": parsedate_to_datetime(correo["Date"]).isoformat(),
                "Text": texto, "HTML": html, "Attachments": adjuntos, "Inline": en_linea}

    def _buscar(self, consulta):
        resultado = []
        for id_, correo in reversed(list(self._correos().items())):  # más nuevo primero
            if consulta == "is:unread" and id_ in self.leidos:
                continue
            if consulta.startswith("from:") and consulta[5:].strip('"') not in correo["From"]:
                continue
            resultado.append(self._resumen(id_, correo))
        return resultado

    def manejar(self, pedido: httpx.Request) -> httpx.Response:
        ruta = pedido.url.path
        correos = self._correos()
        if pedido.method == "GET" and ruta == "/api/v1/search":
            return httpx.Response(200, json={"messages": self._buscar(pedido.url.params["query"])})
        partes = ruta.split("/")
        if pedido.method == "GET" and ruta.startswith("/api/v1/message/"):
            correo = correos[partes[4]]
            if len(partes) == 5:
                return httpx.Response(200, json=self._completo(partes[4], correo))
            if partes[5] == "headers":
                cabeceras: dict[str, list[str]] = {}
                for nombre, valor in correo.items():
                    cabeceras.setdefault(nombre, []).append(str(valor))
                return httpx.Response(200, json=cabeceras)
            if partes[5] == "part":
                parte = list(correo.walk())[int(partes[6])]
                return httpx.Response(200, content=parte.get_payload(decode=True))
        if pedido.method == "PUT" and ruta == "/api/v1/messages":
            datos = json.loads(pedido.content)
            assert datos["Read"] is True
            self.leidos.update(datos["IDs"])
            return httpx.Response(200, text="ok")
        if pedido.method == "PUT" and ruta == "/api/v1/tags":
            datos = json.loads(pedido.content)
            for id_ in datos["IDs"]:
                self.etiquetas[id_] = datos["Tags"]
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text=f"{pedido.method} {ruta}")

    def id_de(self, asunto):
        return next(id_ for id_, c in self._correos().items() if c["Subject"] == asunto)


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setenv("ADJUNTOS_DIR", str(tmp_path / "adjuntos"))
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)


@pytest.fixture
def mailpit(smtp):  # noqa: F811
    return MailpitFalso(smtp)


@pytest.fixture
def config(smtp):  # noqa: F811
    return cs.ConfigCorreo(usuario=YO, app_url="http://localhost:8000", filtro="auto",
                           dominio_empresa="data.cr", proveedor="mailpit", smtp_host="127.0.0.1",
                           smtp_puerto=smtp.server_address[1], mailpit_api="http://mailpit:8025")


@pytest.fixture
def cliente(config, mailpit):
    return cs.ClienteMailpit(config.smtp_host, config.smtp_puerto, config.usuario, config.mailpit_api,
                             http=httpx.Client(transport=httpx.MockTransport(mailpit.manejar)))


@pytest.fixture
def daniel(session):
    """Solicitante con cuenta; la lectura del buzón empezó hace una hora."""
    usuario = User(name="Daniel Sáenz", email=DANIEL, role="Solicitante", password_hash="x",
                   is_active=True)
    hace_una_hora = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add_all([usuario,
                     ProcessedEmail(message_id=cs.MARCA_INICIO, result="inicio", created_at=hace_una_hora),
                     ProcessedEmail(message_id=cs.MARCA_INICIO_ENVIADOS, result="inicio",
                                    created_at=hace_una_hora)])
    session.commit()
    return usuario


@pytest.fixture
def archivos(tmp_path):
    (tmp_path / "foto.jpg").write_bytes(JPG)
    (tmp_path / "informe.pdf").write_bytes(PDF)
    return tmp_path


def enviar(smtp, *opciones):  # noqa: F811
    """El script, como lo corre la persona, contra el SMTP falso."""
    script.main(["--para", YO, "--servidor", "127.0.0.1", "--puerto", str(smtp.server_address[1]),
                 *opciones])


def revisar(factory, config, cliente):  # noqa: F811
    return cs.revisar_buzon(factory, config, cliente)


def adjuntos(session, ticket_id):
    session.expire_all()
    return session.scalars(select(Attachment).where(Attachment.ticket_id == ticket_id)
                           .order_by(Attachment.id)).all()


# --- Conversión al formato de Graph -------------------------------------------------


def test_mensaje_desde_mailpit_como_graph():
    datos = {"ID": "abc", "MessageID": "x1@data.cr", "Subject": "Daño Nokia",
             "From": {"Name": "Daniel", "Address": DANIEL}, "To": [{"Name": "", "Address": YO}],
             "Cc": None, "Date": "2026-11-03T12:26:35-06:00", "Created": "2026-11-03T18:26:36.1Z",
             "Text": "Se me cayó\r\n", "HTML": '<p>Se me cayó</p><p><img alt="f" src="cid:img1@x"></p>',
             "Attachments": [], "Inline": [{"PartID": "1.2", "FileName": "foto.jpg",
                                            "ContentType": "image/jpeg", "ContentID": "img1@x",
                                            "Size": 4000}]}
    mensaje = cs.mensaje_desde_mailpit(datos, {"In-Reply-To": ["<a@b>"], "X-Ticketera": ["1"]})
    assert mensaje["hasAttachments"] is False, "como Graph: no cuenta las imágenes en línea"
    assert "[cid:img1@x]" in mensaje["body"]["content"]
    assert mensaje["internetMessageId"] == "<x1@data.cr>"
    assert {"name": "X-Ticketera", "value": "1"} in mensaje["internetMessageHeaders"]
    correo = cs.correo_desde_graph(mensaje)
    assert (correo.remitente, correo.asunto, correo.cuerpo) == (DANIEL, "Daño Nokia", "Se me cayó")
    assert correo.en_respuesta_a == ["<a@b>"] and correo.de_la_app


def test_adjuntos_desde_mailpit_como_graph():
    datos = {"Attachments": [{"PartID": "2", "FileName": "a.pdf", "ContentType": "application/pdf",
                              "ContentID": "", "Size": 10},
                             {"PartID": "3", "FileName": "RE.eml", "ContentType": "message/rfc822",
                              "ContentID": "", "Size": 20}],
             "Inline": [{"PartID": "1.2", "FileName": "", "ContentType": "image/png",
                         "ContentID": "img@x", "Size": 30}]}
    assert cs.adjuntos_desde_mailpit(datos) == [
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "2", "name": "a.pdf",
         "contentType": "application/pdf", "size": 10, "isInline": False, "contentId": None},
        {"@odata.type": "#microsoft.graph.itemAttachment", "id": "3", "name": "RE.eml",
         "contentType": "message/rfc822", "size": 20, "isInline": False, "contentId": None},
        {"@odata.type": "#microsoft.graph.fileAttachment", "id": "1.2", "name": "",
         "contentType": "image/png", "size": 30, "isInline": True, "contentId": "img@x"},
    ]


# --- De punta a punta, con el script ----------------------------------------------


def test_ticket_con_foto_pegada(factory, session, daniel, smtp, mailpit, cliente, config, archivos):  # noqa: F811
    enviar(smtp, "--de", DANIEL, "--asunto", "Daño Nokia", "--texto", "Se me cayó",
           "--imagen-en-linea", str(archivos / "foto.jpg"))
    id_ = mailpit.id_de("Daño Nokia")
    assert mailpit._completo(id_, mailpit._correos()[id_])["Attachments"] == []

    assert revisar(factory, config, cliente) == {"ticket": 1}
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.title == "Daño Nokia" and "cid:" not in ticket.description
    assert [(a.filename, a.source, a.size) for a in adjuntos(session, ticket.id)] == [
        ("foto.jpg", "correo", len(JPG))]
    # Leído y con la etiqueta de la carpeta; la respuesta salió en el hilo.
    assert id_ in mailpit.leidos and mailpit.etiquetas[id_] == ["Tickets-Procesados"]
    remitente, para, respuesta = smtp.recibidos[-1]
    assert (remitente, para) == (YO, [DANIEL])
    assert respuesta["In-Reply-To"] == mailpit._correos()[id_]["Message-ID"]
    # La siguiente revisión no lo vuelve a tomar y la respuesta de la app
    # (en «enviados») ya estaba registrada.
    assert revisar(factory, config, cliente) == {"enviado_repetido": 1}


def test_la_foto_que_llega_por_mailpit_queda_igual_byte_por_byte(factory, session, daniel, smtp, mailpit, cliente, config, archivos, auth_client):  # noqa: F811
    """La foto va en base64 en el correo; Mailpit la decodifica (``/part``) y
    la ticketera guarda y devuelve exactamente los mismos bytes."""
    enviar(smtp, "--de", DANIEL, "--asunto", "Daño Nokia", "--texto", "Se me cayó",
           "--imagen-en-linea", str(archivos / "foto.jpg"))
    id_ = mailpit.id_de("Daño Nokia")
    parte = next(p for p in mailpit._correos()[id_].walk() if p.get_content_type() == "image/jpeg")
    assert parte["Content-Transfer-Encoding"] == "base64"
    revisar(factory, config, cliente)
    [adjunto] = adjuntos(session, session.scalars(select(Ticket)).one().id)
    assert (adjunto.filename, adjunto.content_type, adjunto.size) == ("foto.jpg", "image/jpeg", len(JPG))
    resp = auth_client.get(f"/api/tickets/{adjunto.ticket_id}/adjuntos/{adjunto.id}/archivo")
    assert resp.content == JPG and resp.headers["content-type"] == "image/jpeg"


def test_imagen_de_prueba_del_script_es_un_png_real(factory, session, daniel, smtp, mailpit, cliente, config):  # noqa: F811
    enviar(smtp, "--de", DANIEL, "--asunto", "Daño Nokia", "--texto", "Se me cayó", "--imagen-de-prueba")
    revisar(factory, config, cliente)
    [adjunto] = adjuntos(session, session.scalars(select(Ticket)).one().id)
    assert adjunto.filename.startswith("imagen_de_prueba") and adjunto.content_type == "image/png"
    assert adjunto.size >= 15 * 1024


def test_ticket_con_pdf_adjunto(factory, session, daniel, smtp, mailpit, cliente, config, archivos):  # noqa: F811
    enviar(smtp, "--de", DANIEL, "--asunto", "La impresora no imprime", "--texto", "Adjunto el error",
           "--adjunto", str(archivos / "informe.pdf"))
    revisar(factory, config, cliente)
    ticket = session.scalars(select(Ticket)).one()
    assert [(a.filename, a.source) for a in adjuntos(session, ticket.id)] == [("informe.pdf", "correo")]


def test_respuesta_con_foto_es_comentario(factory, session, daniel, smtp, mailpit, cliente, config, archivos):  # noqa: F811
    enviar(smtp, "--de", DANIEL, "--asunto", "Daño Nokia", "--texto", "Se me cayó")
    revisar(factory, config, cliente)
    ticket = session.scalars(select(Ticket)).one()
    respuesta_app = smtp.recibidos[-1][2]

    enviar(smtp, "--de", DANIEL, "--en-respuesta-a", respuesta_app["Message-ID"],
           "--texto", "Así quedó la pantalla", "--imagen-en-linea", str(archivos / "foto.jpg"))
    assert revisar(factory, config, cliente) == {"enviado_repetido": 1, "comentario": 1}
    session.expire_all()
    assert [c.content for c in session.scalars(select(Comment))] == ["Así quedó la pantalla"]
    assert [a.filename for a in adjuntos(session, ticket.id)] == ["foto.jpg"]
    assert session.scalar(select(Ticket.id).where(Ticket.id != ticket.id)) is None


def test_foto_del_celular_en_linea_sin_cid(factory, session, daniel, smtp, mailpit, cliente, config, archivos):  # noqa: F811
    """La foto al final, ``Content-Disposition: inline`` sin ``Content-ID``
    ni [cid:…] en el texto (como desde un celular): Mailpit la cuenta en
    línea y ``hasAttachments`` es false. Igual se guarda."""
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    import smtplib

    correo = EmailMessage()
    correo["From"], correo["To"], correo["Subject"] = DANIEL, YO, "Daño Nokia"
    correo["Date"], correo["Message-ID"] = formatdate(localtime=True), make_msgid(domain="data.cr")
    correo.set_content("Se me cayó\n\nEnviado desde mi celular")
    correo.add_attachment(JPG, maintype="image", subtype="jpeg", filename="IMG_0001.jpeg",
                          disposition="inline")
    with smtplib.SMTP("127.0.0.1", smtp.server_address[1]) as conexion:
        conexion.send_message(correo)
    mensaje = cs.mensaje_desde_mailpit(*_completo_y_cabeceras(mailpit, "Daño Nokia"))
    assert mensaje["hasAttachments"] is False and "cid:" not in mensaje["body"]["content"]

    assert revisar(factory, config, cliente) == {"ticket": 1}
    ticket = session.scalars(select(Ticket)).one()
    assert [(a.filename, a.source) for a in adjuntos(session, ticket.id)] == [("IMG_0001.jpeg", "correo")]


def _completo_y_cabeceras(mailpit, asunto):
    id_ = mailpit.id_de(asunto)
    return mailpit._completo(id_, mailpit._correos()[id_]), {}


def test_correo_que_no_pide_ayuda_no_crea_ticket_y_queda_sin_leer(factory, session, daniel, smtp, mailpit, cliente, config):  # noqa: F811
    enviar(smtp, "--de", DANIEL, "--asunto", "Almuerzo del viernes", "--texto", "¿Quién se apunta?")
    assert revisar(factory, config, cliente) == {"otro": 1}
    assert session.scalar(select(Ticket)) is None
    assert mailpit.leidos == set()


def test_solo_lee_lo_que_llega_al_buzon(factory, session, daniel, smtp, mailpit, cliente, config):  # noqa: F811
    script.main(["--de", DANIEL, "--para", "otra@data.cr", "--asunto", "La impresora no imprime",
                 "--servidor", "127.0.0.1", "--puerto", str(smtp.server_address[1])])
    assert cliente.no_leidos() == []
    assert revisar(factory, config, cliente) == {}


# --- Lector cada 30 s y cron -------------------------------------------------------


def test_mailpit_arranca_el_lector_cada_30_segundos(monkeypatch, factory):  # noqa: F811
    for nombre in ("CORREO_ACTIVO", "VERCEL", "CORREO_MODO", "CORREO_INTERVALO"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("CORREO_PROVEEDOR", "mailpit")
    monkeypatch.setenv("CORREO_USUARIO", YO)
    monkeypatch.setenv("CORREO_INTERVALO", "60")
    arrancado = []
    monkeypatch.setattr(cs, "_bucle", lambda fabrica, config, cliente: arrancado.append((config, cliente)))
    monkeypatch.setattr(cs, "_hilo", None)
    assert cs.iniciar_lector(factory) is True
    cs._hilo.join(2)
    [(config, cliente_)] = arrancado
    assert config.intervalo == cs.INTERVALO_MAILPIT == 30
    assert config.mailpit_api == "http://mailpit:8025"
    assert isinstance(cliente_, cs.ClienteMailpit)


def test_en_vercel_nunca_lee_mailpit():
    config = cs.config_desde_entorno({"VERCEL": "1", "CORREO_PROVEEDOR": "mailpit",
                                      "CORREO_ACTIVO": "1", "CORREO_USUARIO": YO})
    assert config.proveedor == "graph" and config.intervalo == 60
