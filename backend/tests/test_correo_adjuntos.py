"""Adjuntos que llegan por correo (parte 2), con Graph simulado.

Las imágenes pegadas en el texto (en línea) se guardan, salvo las de la
firma (menos de 15 KB o repetidas como logo); las marcas ``[cid:…]`` no
quedan en la descripción ni en los comentarios.

Se pide primero la lista (sin contenido) y se descargan solo los que entran:
firma e imágenes chicas se ignoran; tipo no permitido, más de 4 MB, más de 5
o de 10 MB por correo se omiten y se avisan en la respuesta, el historial y
el log. En un ticket Cerrado no se guarda nada.
"""

import io
import zipfile

import httpx
import pytest
from sqlalchemy import create_engine, inspect, select, text

from backend.database import Base, enable_sqlite_foreign_keys
from backend.migrate_add_attachments import migrate_add_attachment_hash, migrate_add_attachment_source
from backend.models import Attachment, Comment, History, Ticket
from backend.services import adjuntos_service
from backend.services import correo_adjuntos as ca
from backend.services import correo_service as cs
from backend.tests.test_correo import CONFIG, FakeGraph, crear_correo, factory, usuario  # noqa: F401

MB = 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * (20 * 1024)  # 20 KB: no es «imagen chica»
PNG_CHICA = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000
PDF = b"%PDF-1.7\n" + b"0" * 1000 + b"\n%%EOF\n"


def _docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archivo:
        archivo.writestr("[Content_Types].xml", "<Types/>")
        archivo.writestr("word/document.xml", "<x/>")
    return buffer.getvalue()


def archivo(nombre, contenido, tipo, inline=False, odata="#microsoft.graph.fileAttachment",
            tamano=None):
    """Un adjunto como lo lista Graph, más su contenido para ``$value``."""
    adjunto = {"@odata.type": odata, "name": nombre, "contentType": tipo,
               "size": len(contenido) + 200 if tamano is None else tamano,
               "isInline": inline, "_contenido": contenido}
    if inline:
        adjunto["contentId"] = f"{nombre}@01DB2C3A.5F1E9B20"
    return adjunto


def firma():
    """El logo chico de la firma, pegado en línea."""
    return archivo("image001.png", PNG_CHICA, "image/png", inline=True)


def en_linea(nombre, contenido, tipo="image/png"):
    """Una imagen pegada dentro del texto (una captura, por ejemplo)."""
    return archivo(nombre, contenido, tipo, inline=True)


def png(kb: int, relleno: bytes = b"\x00") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + relleno * (kb * 1024)


def correo_otro():
    return archivo("RE: presupuesto", b"", "message/rfc822", odata="#microsoft.graph.itemAttachment",
                   tamano=50_000)


def onedrive():
    return archivo("Planilla.xlsx", b"", "application/vnd.ms-excel",
                   odata="#microsoft.graph.referenceAttachment", tamano=900)


class GraphConAdjuntos(FakeGraph):
    """FakeGraph con ``/attachments`` (lista con ``$select``) y ``$value``."""

    def __init__(self, mensajes, **kwargs):
        self.adjuntos = {}
        for mensaje in mensajes:
            lista = mensaje.pop("_adjuntos", [])
            for i, adjunto in enumerate(lista):
                adjunto.setdefault("id", f"{mensaje['id']}-adj{i}")
            self.adjuntos[mensaje["id"]] = lista
            # Como en Graph: ``hasAttachments`` no cuenta las imágenes en
            # línea, y Outlook deja una marca [cid:…] por cada una en el texto.
            mensaje["hasAttachments"] = any(not a.get("isInline") for a in lista)
            cuerpo = mensaje["body"]
            sin_cid = mensaje.pop("_sin_cid", False)
            for adjunto in lista:
                if (adjunto.get("isInline") and adjunto.get("contentId") and not sin_cid
                        and adjunto["contentId"] not in cuerpo["content"]):
                    cuerpo["content"] += f" [cid:{adjunto['contentId']}]"
        self.descargas = []
        self.fallar_lista = False
        super().__init__(mensajes, **kwargs)

    def manejar(self, request: httpx.Request) -> httpx.Response:
        partes = request.url.path.removeprefix("/v1.0").split("/")
        if request.method == "GET" and len(partes) >= 5 and partes[4] == "attachments":
            self.llamadas.append((request.method, request.url.path.removeprefix("/v1.0")))
            lista = self.adjuntos.get(partes[3], [])
            if len(partes) == 5:
                if self.fallar_lista:
                    return httpx.Response(500, json={"error": {"message": "Graph caído"}})
                # Se pide solo la lista: nunca el contenido de todos.
                assert request.url.params["$select"] == "id,name,contentType,size,isInline,contentId"
                return httpx.Response(200, json={"value": [
                    {k: v for k, v in a.items() if k != "_contenido"} for a in lista]})
            if len(partes) == 7 and partes[6] == "$value":
                adjunto = next(a for a in lista if a["id"] == partes[5])
                self.descargas.append(adjunto["name"])
                return httpx.Response(200, content=adjunto["_contenido"])
        return super().manejar(request)


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    destino = tmp_path / "adjuntos"
    monkeypatch.setenv("ADJUNTOS_DIR", str(destino))
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    return destino


@pytest.fixture
def log(caplog, monkeypatch):
    for logger in (cs.logger, ca.logger):
        monkeypatch.setattr(logger, "propagate", True)
        caplog.set_level("INFO", logger=logger.name)
    return caplog


def con_adjuntos(*adjuntos, **kwargs):
    mensaje = crear_correo(**kwargs)
    mensaje["_adjuntos"] = list(adjuntos)
    return mensaje


def texto_respuesta(graph, indice=-1):
    return graph.respuestas[indice][1]["message"]["body"]["content"]


def adjuntos_en_bd(session, ticket_id=None):
    session.expire_all()
    consulta = select(Attachment).order_by(Attachment.id)
    if ticket_id is not None:
        consulta = consulta.where(Attachment.ticket_id == ticket_id)
    return session.scalars(consulta).all()


def historial(session, accion):
    session.expire_all()
    return session.scalars(select(History).where(History.action == accion)).all()


def revisar(factory, graph):
    return cs.revisar_buzon(factory, CONFIG, graph.cliente)


# --- Lo que se guarda y lo que se ignora --------------------------------------


def test_guarda_los_archivos_e_ignora_firma_imagen_chica_correo_y_onedrive(factory, session, usuario, log, carpeta):
    graph = GraphConAdjuntos([con_adjuntos(
        firma(),
        archivo("captura.png", PNG, "image/png"),
        archivo("logo.png", PNG_CHICA, "image/png"),
        archivo("factura.pdf", PDF, "application/pdf"),
        correo_otro(),
        onedrive(),
        archivo("informe.docx", _docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )])
    assert revisar(factory, graph) == {"ticket": 1}

    ticket = session.scalars(select(Ticket)).one()
    guardados = adjuntos_en_bd(session)
    assert [a.filename for a in guardados] == ["captura.png", "factura.pdf", "informe.docx"]
    assert {a.source for a in guardados} == {"correo"}
    assert {a.ticket_id for a in guardados} == {ticket.id}
    assert {a.uploaded_by for a in guardados} == {"Ana Pérez"}
    assert len([p for p in carpeta.rglob("*") if p.is_file()]) == 3
    # Solo se descargaron los que se guardan.
    assert graph.descargas == ["captura.png", "factura.pdf", "informe.docx"]

    # Lo ignorado no se avisa en la respuesta ni en el historial; sí en el log.
    assert "No se guard" not in texto_respuesta(graph)
    assert historial(session, "attachments_skipped") == []
    assert [(h.new_value, h.field) for h in historial(session, "attachment_added")] == [
        ("captura.png", "correo"), ("factura.pdf", "correo"), ("informe.docx", "correo")]
    assert "image001.png (imagen en línea de menos de 15 KB (firma))" in log.text
    assert "logo.png (imagen de menos de 15 KB)" in log.text
    assert "RE: presupuesto (otro correo)" in log.text
    assert "Planilla.xlsx (enlace a OneDrive/SharePoint)" in log.text


def test_sin_adjuntos_no_se_pide_la_lista(factory, usuario):
    graph = GraphConAdjuntos([crear_correo()])
    assert revisar(factory, graph) == {"ticket": 1}
    assert not any("attachments" in ruta for _, ruta in graph.llamadas)


def test_solo_firma_no_agrega_nota(factory, session, usuario):
    graph = GraphConAdjuntos([con_adjuntos(firma(), archivo("logo.png", PNG_CHICA, "image/png"))])
    revisar(factory, graph)
    assert adjuntos_en_bd(session) == []
    assert graph.descargas == []
    assert "No se guard" not in texto_respuesta(graph)


# --- Omitidos: tipo, tamaño, cantidad -----------------------------------------


def test_tipo_no_permitido_y_muy_grande_no_se_descargan_y_se_avisan(factory, session, usuario, log):
    graph = GraphConAdjuntos([con_adjuntos(
        archivo("programa.exe", b"MZ\x90\x00", "application/octet-stream"),
        archivo("manual.pdf", b"%PDF-", "application/pdf", tamano=5 * MB),
        archivo("factura.pdf", PDF, "application/pdf"),
    )])
    assert revisar(factory, graph) == {"ticket": 1}

    ticket = session.scalars(select(Ticket)).one()
    assert [a.filename for a in adjuntos_en_bd(session)] == ["factura.pdf"]
    assert graph.descargas == ["factura.pdf"]

    enlace = f"http://ticketera.data.cr/detalle.html?id={ticket.id}"
    nota = (f"No se guardaron 2 adjuntos (tipo no permitido o más de 4 MB). "
            f"Puede subirlos desde la ticketera: {enlace}")
    respuesta = texto_respuesta(graph)
    assert nota in respuesta
    assert respuesta.endswith(f"{nota}\n\nMesa de ayuda"), "la nota va antes de la firma"

    [entrada] = historial(session, "attachments_skipped")
    assert entrada.ticket_id == ticket.id
    assert entrada.new_value == ("No se guardaron 2 adjuntos del correo: programa.exe (tipo no "
                                 "permitido); manual.pdf (más de 4 MB)")
    assert entrada.author == "Ana Pérez"
    assert (f"Ticket #{ticket.id}: adjuntos del correo no guardados: programa.exe (tipo no "
            "permitido); manual.pdf (más de 4 MB)") in log.text


def test_contenido_que_no_coincide_se_omite_despues_de_bajarlo(factory, session, usuario):
    graph = GraphConAdjuntos([con_adjuntos(archivo("factura.pdf", b"MZ\x90\x00programa", "application/pdf"))])
    revisar(factory, graph)
    assert graph.descargas == ["factura.pdf"]
    assert adjuntos_en_bd(session) == []
    assert "No se guardó 1 adjunto (tipo no permitido o más de 4 MB). Puede subirlos" in texto_respuesta(graph)


def test_mas_de_5_por_correo(factory, session, usuario):
    graph = GraphConAdjuntos([con_adjuntos(
        *[archivo(f"foto{i}.png", PNG, "image/png") for i in range(7)])])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == [f"foto{i}.png" for i in range(5)]
    assert graph.descargas == [f"foto{i}.png" for i in range(5)], "los que sobran no se bajan"
    assert "No se guardaron 2 adjuntos (más de 5 por correo). Puede subirlos" in texto_respuesta(graph)


def test_mas_de_10_mb_por_correo(factory, session, usuario):
    grande = b"%PDF-" + b"0" * int(3.9 * MB)
    graph = GraphConAdjuntos([con_adjuntos(
        archivo("a.pdf", grande, "application/pdf"),
        archivo("b.pdf", grande, "application/pdf"),
        archivo("c.pdf", grande, "application/pdf"),
        archivo("chico.pdf", PDF, "application/pdf"),
    )])
    revisar(factory, graph)
    # a + b ≈ 7,8 MB; c no entra; chico.pdf sí (sigue en el orden del correo).
    assert [a.filename for a in adjuntos_en_bd(session)] == ["a.pdf", "b.pdf", "chico.pdf"]
    assert "c.pdf" not in graph.descargas
    assert "No se guardó 1 adjunto (más de 10 MB en el correo)." in texto_respuesta(graph)


def test_mezcla_de_motivos_los_nombra_todos(factory, session, usuario):
    graph = GraphConAdjuntos([con_adjuntos(
        archivo("virus.exe", b"MZ", "application/octet-stream"),
        *[archivo(f"foto{i}.png", PNG, "image/png") for i in range(6)])])
    revisar(factory, graph)
    assert "No se guardaron 2 adjuntos (tipo no permitido o más de 5 por correo)." in texto_respuesta(graph)


def test_el_ticket_ya_tiene_10_adjuntos(factory, session, usuario):
    graph = GraphConAdjuntos([crear_correo()])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()
    for i in range(9):
        adjuntos_service.subir(session, ticket, None, f"previo{i}.txt", b"texto")

    respuesta = con_adjuntos(*[archivo(f"nuevo{i}.png", PNG, "image/png") for i in range(3)],
                             asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                             cuerpo="Les mando más fotos.", msg_id="<sigue@data.cr>")
    graph2 = GraphConAdjuntos([respuesta])
    assert revisar(factory, graph2) == {"comentario": 1}
    nombres = [a.filename for a in adjuntos_en_bd(session, ticket.id)]
    assert len(nombres) == 10 and nombres[-1] == "nuevo0.png"
    assert graph2.descargas == ["nuevo0.png"]
    assert "No se guardaron 2 adjuntos (el ticket ya tiene 10 adjuntos)." in texto_respuesta(graph2)


# --- Comentario y ticket Cerrado ----------------------------------------------


def test_el_comentario_por_correo_guarda_sus_adjuntos_en_el_ticket(factory, session, usuario):
    graph = GraphConAdjuntos([crear_correo()])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()

    respuesta = con_adjuntos(archivo("error.png", PNG, "image/png"),
                             archivo("datos.zip", b"PK\x03\x04", "application/zip"),
                             asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                             cuerpo="Adjunto la captura del error.", msg_id="<sigue@data.cr>")
    graph2 = GraphConAdjuntos([respuesta])
    assert revisar(factory, graph2) == {"comentario": 1}
    [adjunto] = adjuntos_en_bd(session, ticket.id)
    assert (adjunto.filename, adjunto.source) == ("error.png", "correo")
    texto = texto_respuesta(graph2)
    assert texto.startswith("Hola Ana Pérez,\n\nAgregamos tu mensaje como comentario")
    assert (f"No se guardó 1 adjunto (tipo no permitido o más de 4 MB). Puede subirlos desde la "
            f"ticketera: http://ticketera.data.cr/detalle.html?id={ticket.id}\n\nMesa de ayuda") in texto


def test_en_ticket_cerrado_no_se_guardan(factory, session, usuario, log):
    graph = GraphConAdjuntos([crear_correo()])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()
    ticket.state = "Cerrado"
    session.commit()

    respuesta = con_adjuntos(archivo("error.png", PNG, "image/png"),
                             asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                             cuerpo="Sigue fallando.", msg_id="<sigue@data.cr>")
    graph2 = GraphConAdjuntos([respuesta])
    assert revisar(factory, graph2) == {"cerrado": 1}
    assert adjuntos_en_bd(session) == []
    assert not any("attachments" in ruta for _, ruta in graph2.llamadas), "ni se pide la lista"
    assert "No se guard" not in texto_respuesta(graph2)


def test_guardar_en_un_ticket_cerrado_devuelve_none_sin_llamar_a_graph(factory, session, usuario, log):
    graph = GraphConAdjuntos([con_adjuntos(archivo("a.png", PNG, "image/png"))])
    mensaje_id = next(iter(graph.adjuntos))
    ticket = Ticket(title="Ticket cerrado de prueba", description="Ya está cerrado.",
                    category="Hardware", priority="Media", state="Cerrado")
    session.add(ticket)
    session.commit()
    assert ca.guardar(factory, graph.cliente, mensaje_id, ticket.id, "ana@data.cr") is None
    assert graph.llamadas == []
    assert f"el ticket #{ticket.id} está Cerrado" in log.text


# --- Fallas y tiempo ----------------------------------------------------------


def test_si_graph_falla_el_ticket_se_crea_y_se_responde(factory, session, usuario, log):
    graph = GraphConAdjuntos([con_adjuntos(archivo("a.png", PNG, "image/png"))])
    graph.fallar_lista = True
    assert revisar(factory, graph) == {"ticket": 1}
    assert session.scalars(select(Ticket)).one() is not None
    assert len(graph.respuestas) == 1
    assert "No se pudieron guardar los adjuntos del correo" in log.text


def test_sin_tiempo_los_que_faltan_se_omiten(factory, session, usuario, monkeypatch):
    graph = GraphConAdjuntos([con_adjuntos(archivo("a.png", PNG, "image/png"),
                                           archivo("b.png", PNG, "image/png"))])
    mensaje_id = next(iter(graph.adjuntos))
    ticket = Ticket(title="Ticket abierto de prueba", description="Con tiempo vencido.",
                    category="Hardware", priority="Media")
    session.add(ticket)
    session.commit()
    resultado = ca.guardar(factory, graph.cliente, mensaje_id, ticket.id, "ana@data.cr",
                           hasta=ca.time.monotonic() - 100)
    assert resultado.guardados == []
    assert resultado.omitidos == [("a.png", ca.MOTIVO_TIEMPO), ("b.png", ca.MOTIVO_TIEMPO)]
    assert graph.descargas == []


# --- Detalle («por correo») y migración ---------------------------------------


def test_la_lista_del_detalle_dice_por_correo(factory, session, usuario, auth_client):
    graph = GraphConAdjuntos([con_adjuntos(archivo("captura.png", PNG, "image/png"))])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()
    adjuntos_service.subir(session, ticket, None, "nota.txt", b"subido desde la app")
    lista = auth_client.get(f"/api/tickets/{ticket.id}/adjuntos").json()["adjuntos"]
    assert [(a["nombre"], a["por_correo"]) for a in lista] == [("captura.png", True), ("nota.txt", False)]


def test_migracion_agrega_source_a_la_tabla_de_la_parte_1(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'parte1.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE adjuntos"))
        conn.execute(text(
            "CREATE TABLE adjuntos (id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, "
            "filename VARCHAR(255) NOT NULL, content_type VARCHAR(120) NOT NULL, size INTEGER NOT NULL, "
            "storage VARCHAR(10) NOT NULL, storage_key VARCHAR(500) NOT NULL, uploaded_by VARCHAR(120), "
            "uploaded_by_id INTEGER, created_at DATETIME NOT NULL)"))
        conn.execute(text(
            "INSERT INTO adjuntos (ticket_id, filename, content_type, size, storage, storage_key, created_at) "
            "VALUES (1, 'viejo.pdf', 'application/pdf', 10, 'local', 'tickets/1/x.pdf', '2026-11-01')"))

    assert migrate_add_attachment_source(engine) is True
    assert "source" in {c["name"] for c in inspect(engine).get_columns("adjuntos")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT source FROM adjuntos")).scalar_one() == "app"
    assert migrate_add_attachment_source(engine) is False  # idempotente
    engine.dispose()


# --- La nota de la respuesta --------------------------------------------------


def test_nota_singular_plural_y_motivos():
    enlace = "http://x/detalle.html?id=3"
    assert ca.nota_omitidos([("a.exe", ca.MOTIVO_TIPO)], enlace) == (
        "No se guardó 1 adjunto (tipo no permitido o más de 4 MB). Puede subirlos desde la "
        "ticketera: http://x/detalle.html?id=3")
    assert ca.nota_omitidos([("a.pdf", ca.MOTIVO_GRANDE), ("b.pdf", ca.MOTIVO_GRANDE)], enlace).startswith(
        "No se guardaron 2 adjuntos (tipo no permitido o más de 4 MB).")
    assert ca.nota_omitidos([("a", ca.MOTIVO_CANTIDAD), ("b", ca.MOTIVO_TOTAL), ("c", ca.MOTIVO_GRANDE)],
                            enlace).startswith(
        "No se guardaron 3 adjuntos (más de 4 MB, más de 5 por correo o más de 10 MB en el correo).")


# --- Imágenes pegadas en el texto (en línea) ----------------------------------

CID = "[cid:image001.png@01DB2C3A.5F1E9B20]"


def test_la_captura_pegada_se_guarda_por_correo_y_sin_cid_en_la_descripcion(factory, session, usuario, auth_client):
    captura = png(60)
    mensaje = con_adjuntos(en_linea("image001.png", captura), firma(),
                           cuerpo=f"La impresora muestra este error:\r\n{CID}\r\n\r\nSaludos,\r\nAna "
                                  "[cid:image002.png@01DB2C3A.5F1E9B20]")
    graph = GraphConAdjuntos([mensaje])
    assert revisar(factory, graph) == {"ticket": 1}

    ticket = session.scalars(select(Ticket)).one()
    [adjunto] = adjuntos_en_bd(session)
    assert (adjunto.filename, adjunto.source, adjunto.content_type) == ("image001.png", "correo", "image/png")
    assert adjunto.sha256 == adjuntos_service.huella(captura)
    assert "cid:" not in ticket.description
    assert ticket.description.startswith("La impresora muestra este error:\n\nSaludos,\nAna")
    lista = auth_client.get(f"/api/tickets/{ticket.id}/adjuntos").json()["adjuntos"]
    assert [(a["nombre"], a["por_correo"], a["es_imagen"]) for a in lista] == [("image001.png", True, True)]
    assert "No se guard" not in texto_respuesta(graph)


def test_imagen_en_linea_sin_extension_toma_la_de_su_tipo(factory, session, usuario):
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * (30 * 1024)
    graph = GraphConAdjuntos([con_adjuntos(en_linea("Pasted image", jpg, "image/jpeg"),
                                           cuerpo=f"Mire la foto {CID}")])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["Pasted image.jpg"]


def test_firma_imagenes_chicas_logo_repetido_y_gif_en_linea_no_se_guardan_ni_avisan(factory, session, usuario, log):
    logo = png(20, b"L")
    graph = GraphConAdjuntos([con_adjuntos(
        firma(),
        en_linea("image002.png", logo), en_linea("image003.png", logo),  # el mismo logo, dos veces
        archivo("image004.gif", b"GIF89a" + b"0" * 40_000, "image/gif", inline=True),
        en_linea("image005.png", png(50)),  # la captura de verdad
    )])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["image005.png"]
    assert graph.descargas == ["image005.png"], "los repetidos ni se bajan"
    assert "No se guard" not in texto_respuesta(graph)
    assert historial(session, "attachments_skipped") == []
    assert "image002.png (imagen en línea repetida (logo))" in log.text
    assert "image003.png (imagen en línea repetida (logo))" in log.text
    assert "image004.gif (imagen en línea de un tipo que no se guarda)" in log.text


def test_el_logo_que_ya_llego_en_otro_correo_del_mismo_remitente_no_se_vuelve_a_guardar(factory, session, usuario, log):
    logo = png(25, b"L")
    primero = GraphConAdjuntos([con_adjuntos(en_linea("image001.png", logo), msg_id="<uno@data.cr>",
                                             asunto="La impresora no imprime")])
    revisar(factory, primero)
    assert len(adjuntos_en_bd(session)) == 1  # la primera vez no se sabe que es un logo

    segundo = GraphConAdjuntos([con_adjuntos(en_linea("image001.png", logo), en_linea("image002.png", png(40)),
                                             msg_id="<dos@data.cr>", asunto="No funciona el escáner")])
    assert revisar(factory, segundo) == {"ticket": 1}
    nuevo = session.scalars(select(Ticket).order_by(Ticket.id.desc())).first()
    assert [a.filename for a in adjuntos_en_bd(session, nuevo.id)] == ["image002.png"]
    assert "No se guard" not in texto_respuesta(segundo)
    assert f"Ticket #{nuevo.id}: adjuntos del correo ignorados: image001.png (imagen en línea repetida (logo))" in log.text


def test_un_adjunto_comun_repetido_si_se_guarda(factory, session, usuario):
    """La regla del logo es solo para imágenes en línea."""
    foto = png(30)
    revisar(factory, GraphConAdjuntos([con_adjuntos(archivo("foto.png", foto, "image/png"), msg_id="<a@x>")]))
    revisar(factory, GraphConAdjuntos([con_adjuntos(archivo("foto.png", foto, "image/png"), msg_id="<b@x>",
                                                    asunto="Otra consulta de impresora")]))
    assert len(adjuntos_en_bd(session)) == 2


def test_comentario_por_correo_sin_cid_y_con_la_captura(factory, session, usuario):
    revisar(factory, GraphConAdjuntos([crear_correo()]))
    ticket = session.scalars(select(Ticket)).one()

    respuesta = con_adjuntos(en_linea("image001.png", png(45)), firma(),
                             asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                             cuerpo=f"Ahora sale este mensaje {CID} en pantalla.", msg_id="<sigue@data.cr>")
    assert revisar(factory, GraphConAdjuntos([respuesta])) == {"comentario": 1}
    session.expire_all()
    [comentario] = session.scalars(select(Comment)).all()
    assert comentario.content == "Ahora sale este mensaje en pantalla."
    assert [a.filename for a in adjuntos_en_bd(session, ticket.id)] == ["image001.png"]


def test_respuesta_con_solo_una_captura_igual_es_comentario(factory, session, usuario):
    revisar(factory, GraphConAdjuntos([crear_correo()]))
    ticket = session.scalars(select(Ticket)).one()
    respuesta = con_adjuntos(en_linea("image001.png", png(45)),
                             asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                             cuerpo=CID, msg_id="<sigue@data.cr>")
    assert revisar(factory, GraphConAdjuntos([respuesta])) == {"comentario": 1}
    session.expire_all()
    assert session.scalars(select(Comment)).one().content == "(Imagen pegada en el correo.)"
    assert len(adjuntos_en_bd(session, ticket.id)) == 1


def test_cid_en_html_y_en_texto():
    for cuerpo in ({"contentType": "text", "content": f"Hola {CID} chau"},
                   {"contentType": "html", "content": '<p>Hola <img src="cid:image001.png@01DB"> chau</p>'}):
        correo = cs.correo_desde_graph({"id": "1", "subject": "x", "body": cuerpo,
                                        "from": {"emailAddress": {"address": "ana@data.cr"}}})
        assert correo.cuerpo == "Hola chau"


def test_migracion_agrega_sha256(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sin_huella.db'}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_adjuntos_sha256"))
        conn.execute(text("ALTER TABLE adjuntos DROP COLUMN sha256"))
    assert migrate_add_attachment_hash(engine) is True
    assert "sha256" in {c["name"] for c in inspect(engine).get_columns("adjuntos")}
    assert "ix_adjuntos_sha256" in {i["name"] for i in inspect(engine).get_indexes("adjuntos")}
    assert migrate_add_attachment_hash(engine) is False
    engine.dispose()


# --- hasAttachments=false con imágenes en línea y registro en el log ---------


def test_solo_una_captura_pegada_se_guarda_aunque_hasattachments_sea_false(factory, session, usuario, log):
    """Graph manda ``hasAttachments: false`` si el correo solo trae imágenes
    en línea: igual se pide la lista por la marca [cid:…] del texto."""
    mensaje = con_adjuntos(en_linea("image001.png", png(60)), cuerpo=f"Sale este error:\r\n{CID}")
    graph = GraphConAdjuntos([mensaje])
    assert mensaje["hasAttachments"] is False
    assert revisar(factory, graph) == {"ticket": 1}
    assert [a.filename for a in adjuntos_en_bd(session)] == ["image001.png"]
    assert "hasAttachments=false pero trae imágenes en línea" in log.text
    assert "el correo trae 1 adjunto(s): «image001.png» (tamaño=" in log.text


def test_sin_marca_cid_ni_hasattachments_no_se_pide_la_lista(factory, usuario):
    mensaje = con_adjuntos(en_linea("image001.png", png(60)))
    mensaje["_sin_cid"] = True
    graph = GraphConAdjuntos([mensaje])
    assert revisar(factory, graph) == {"ticket": 1}
    assert not any("attachments" in ruta for _, ruta in graph.llamadas)


def test_cada_descartado_queda_como_warning_con_sus_datos(factory, session, usuario, log):
    graph = GraphConAdjuntos([con_adjuntos(
        firma(),
        archivo("virus.exe", b"MZ" + b"0" * 30_000, "application/octet-stream"),
        archivo("falsa.pdf", b"no es un pdf" * 3000, "application/pdf"),
    )])
    revisar(factory, graph)
    avisos = [r.getMessage() for r in log.records if r.levelname == "WARNING"]
    firma_ = next(a for a in avisos if "«image001.png»" in a)
    assert "isInline=True" in firma_ and "contentId=image001.png@01DB2C3A.5F1E9B20" in firma_
    assert f"tamaño={len(PNG_CHICA) + 200}" in firma_
    assert "motivo: imagen en línea de menos de 15 KB (firma)" in firma_
    exe = next(a for a in avisos if "«virus.exe»" in a)
    assert "isInline=False" in exe and "contentId=-" in exe and "motivo: tipo no permitido" in exe
    # Se descargó y el contenido no coincide: también dice cuántos bytes llegaron.
    pdf = next(a for a in avisos if "«falsa.pdf»" in a)
    assert "motivo: tipo no permitido (" in pdf and "bytes descargados" in pdf


def test_si_falla_la_descarga_queda_warning_con_el_error(factory, session, usuario, log, monkeypatch):
    graph = GraphConAdjuntos([con_adjuntos(en_linea("image001.png", png(60)), cuerpo=f"Mire {CID}")])

    def falla(*args, **kwargs):
        raise RuntimeError("Graph devolvió 503")

    monkeypatch.setattr(graph.cliente, "descargar_adjunto", falla)
    assert revisar(factory, graph) == {"ticket": 1}
    assert adjuntos_en_bd(session) == []
    aviso = next(r.getMessage() for r in log.records
                 if r.levelname == "WARNING" and "«image001.png»" in r.getMessage())
    assert "isInline=True" in aviso and "contentId=image001.png@01DB2C3A.5F1E9B20" in aviso
    assert "motivo: no se pudo descargar: RuntimeError('Graph devolvió 503')" in aviso
    assert "No se guard" in texto_respuesta(graph)


def test_si_falla_el_almacen_queda_warning_y_sigue_con_los_demas(factory, session, usuario, log, monkeypatch):
    graph = GraphConAdjuntos([con_adjuntos(archivo("a.png", PNG, "image/png"),
                                           archivo("b.pdf", PDF, "application/pdf"))])
    original = adjuntos_service.subir

    def subir(session_, ticket, user, nombre, contenido, origen="app"):
        if nombre == "a.png":
            raise OSError("Blob no responde")
        return original(session_, ticket, user, nombre, contenido, origen=origen)

    monkeypatch.setattr(adjuntos_service, "subir", subir)
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["b.pdf"]
    assert any(r.levelname == "WARNING" and "«a.png»" in r.getMessage()
               and "no se pudo guardar: OSError('Blob no responde')" in r.getMessage()
               for r in log.records)
