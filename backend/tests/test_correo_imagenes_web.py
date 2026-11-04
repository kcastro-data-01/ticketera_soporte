"""Imágenes del cuerpo HTML que no vienen como adjunto (copiadas de una
página y pegadas en Outlook): ``<img src="https://…">`` y ``data:image/…``.

La red está simulada: un resolutor de DNS falso y un ``MockTransport`` de
httpx. Nada sale a Internet.
"""

import base64
import io
import os
import time

import httpx
import pytest
from sqlalchemy import select

from backend.models import Attachment, Ticket
from backend.services import correo_adjuntos as ca
from backend.services import correo_imagenes_web as web
from backend.tests import imagenes
from backend.tests.test_correo import crear_correo, factory, usuario  # noqa: F401
from backend.tests.test_correo_adjuntos import (  # noqa: F401
    GraphConAdjuntos, adjuntos_en_bd, archivo, carpeta, historial, log, revisar, texto_respuesta)

MB = 1024 * 1024
FOTO = imagenes.jpeg(40, relleno=b"\x07")
CAPTURA = imagenes.png(30, relleno=b"\x05")
IP_PUBLICA = "93.184.216.34"


class Red:
    """DNS y servidores web simulados. ``paginas`` es ``{url: respuesta}``,
    donde la respuesta es ``bytes``, un ``httpx.Response`` o una función."""

    def __init__(self, paginas=None, dns=None):
        self.paginas = dict(paginas or {})
        self.dns = {"www.ejemplo.com": [IP_PUBLICA], "cdn.ejemplo.com": ["151.101.1.1"],
                    "intranet.empresa.com": ["10.0.0.5"], **(dns or {})}
        self.pedidos: list[httpx.Request] = []
        self.resueltos: list[str] = []
        self.transporte = httpx.MockTransport(self.manejar)

    def resolver(self, host):
        self.resueltos.append(host)
        if host not in self.dns:
            raise OSError("nombre desconocido")
        return self.dns[host]

    def manejar(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        url = f"https://{request.headers['Host']}{request.url.raw_path.decode()}"
        respuesta = self.paginas.get(url)
        if respuesta is None:
            return httpx.Response(404)
        if callable(respuesta):
            return respuesta(request)
        if isinstance(respuesta, bytes):
            return httpx.Response(200, content=respuesta, headers={"Content-Type": "image/jpeg"})
        return respuesta

    def descargar(self, src, hasta):
        return web.descargar(src, hasta, transporte=self.transporte, resolver=self.resolver)


@pytest.fixture
def red(monkeypatch):
    red = Red()
    monkeypatch.setattr(ca, "descargar_imagen", red.descargar)
    return red


def correo_html(html, unico=None, **kwargs):
    """Un correo cuyo cuerpo HTML (lo que pide ``cuerpo_html``) es ``html``."""
    mensaje = crear_correo(**kwargs)
    mensaje["_html"] = html
    if unico is not None:
        mensaje["_html_unico"] = unico
    mensaje["_adjuntos"] = []
    return mensaje


def img(src, **atributos):
    extra = "".join(f' {k}="{v}"' for k, v in atributos.items())
    return f'<img src="{src}"{extra}>'


def data_uri(contenido, tipo="image/png"):
    return f"data:{tipo};base64,{base64.b64encode(contenido).decode()}"


def cuerpo(*imgs, texto="La impresora muestra este error:"):
    return f"<html><body><p>{texto}</p>{''.join(imgs)}<p>Gracias</p></body></html>"


# --- data: URI -----------------------------------------------------------------


def test_data_uri_se_decodifica_y_se_guarda_por_correo(factory, session, usuario, log, red):
    graph = GraphConAdjuntos([correo_html(cuerpo(img(data_uri(CAPTURA))))])
    assert revisar(factory, graph) == {"ticket": 1}
    [adjunto] = adjuntos_en_bd(session)
    assert (adjunto.filename, adjunto.source, adjunto.size) == ("imagen_web_1.png", "correo", len(CAPTURA))
    assert "No se guard" not in texto_respuesta(graph)
    assert red.pedidos == []  # data: no sale a la red
    assert [(h.new_value, h.field) for h in historial(session, "attachment_added")] == [
        ("imagen_web_1.png", "correo")]
    # El log no copia el base64 entero.
    assert "data:image/png;base64,… (" in log.text
    assert base64.b64encode(CAPTURA).decode()[:200] not in log.text


def test_data_uri_dañado_o_que_no_es_imagen_se_avisa(factory, session, usuario, log, red):
    graph = GraphConAdjuntos([correo_html(cuerpo(
        img("data:image/png;base64,iVBORw0KGgo%%%%"),
        img(data_uri(b"<svg xmlns='http://www.w3.org/2000/svg'>" + b" " * 20000 + b"</svg>",
                     "image/svg+xml"))))])
    revisar(factory, graph)
    assert adjuntos_en_bd(session) == []
    texto = texto_respuesta(graph)
    assert "No se guardaron 2 adjuntos" in texto
    assert "imagen dañada o incompleta" in texto or "tipo no permitido" in texto
    [entrada] = historial(session, "attachments_skipped")
    assert "imagen_web" in entrada.new_value
    assert "base64 inválido" in log.text
    assert "contenido SVG" in log.text


# --- https:// ------------------------------------------------------------------


def test_https_se_descarga_con_ip_fija_sin_credenciales_y_toma_el_nombre(factory, session, usuario, log, red):
    url = "https://www.ejemplo.com/fotos/router-roto.jpg?w=800&token=secreto"
    red.paginas[url] = FOTO
    graph = GraphConAdjuntos([correo_html(cuerpo(img(url)))])
    revisar(factory, graph)

    [adjunto] = adjuntos_en_bd(session)
    assert (adjunto.filename, adjunto.source) == ("router-roto.jpg", "correo")
    [pedido] = red.pedidos
    # Se conecta a la IP ya revisada, con el nombre en Host y en SNI.
    assert pedido.url.host == IP_PUBLICA
    assert pedido.headers["Host"] == "www.ejemplo.com"
    assert pedido.extensions["sni_hostname"] == "www.ejemplo.com"
    assert pedido.headers["User-Agent"] == web.USER_AGENT
    assert "cookie" not in pedido.headers and "authorization" not in pedido.headers
    assert "referer" not in pedido.headers
    # En el log no queda la consulta (puede llevar claves).
    assert "token=secreto" not in log.text


def test_nombre_del_enlace_raro_o_sin_extension_queda_imagen_web_n(factory, session, usuario, red):
    feo = "https://cdn.ejemplo.com/images?q=tbn:ANd9GcR"
    codigo = "https://www.ejemplo.com/AAAAbbbbCCCCddddEEEEffffGGGGhhhh1234.png"
    red.paginas[feo] = imagenes.jpeg(30, relleno=b"\x01")
    red.paginas[codigo] = imagenes.png(30, relleno=b"\x02")
    graph = GraphConAdjuntos([correo_html(cuerpo(img(feo), img(codigo)))])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["imagen_web_1.jpg", "imagen_web_2.png"]


def test_la_extension_del_nombre_sigue_al_contenido():
    assert web.nombre_del_enlace("https://x.com/a/Error%20impresora.webp", ".png") == "Error impresora.png"
    assert web.nombre_del_enlace("https://x.com/a/captura.png", ".jpg") == "captura.jpg"
    assert web.nombre_del_enlace("https://x.com/a/descargar", ".jpg") is None
    assert web.nombre_del_enlace("https://x.com/a/12345.jpg", ".jpg") is None
    assert web.nombre_del_enlace("data:image/png;base64,AAAA", ".png") is None


@pytest.mark.parametrize("url, dns", [
    ("https://intranet.empresa.com/foto.png", None),
    ("https://127.0.0.1/foto.png", None),
    ("https://10.1.2.3/foto.png", None),
    ("https://172.20.0.1/foto.png", None),
    ("https://192.168.1.10/foto.png", None),
    ("https://169.254.169.254/latest/meta-data", None),
    ("https://[::1]/foto.png", None),
    ("https://[fd00::1]/foto.png", None),
    ("https://[::ffff:10.0.0.1]/foto.png", None),
    ("https://localhost/foto.png", {"localhost": ["127.0.0.1"]}),
    # Un nombre que resuelve a una pública y a una privada: se bloquea.
    ("https://mixto.ejemplo.com/foto.png", {"mixto.ejemplo.com": [IP_PUBLICA, "192.168.0.2"]}),
])
def test_ip_privada_local_o_de_metadatos_se_bloquea_sin_conectar(url, dns):
    red = Red(dns=dns)
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar(url, time.monotonic() + 5)
    assert error.value.motivo == web.MOTIVO_ENLACE
    assert "dirección interna" in error.value.detalle
    assert red.pedidos == []


@pytest.mark.parametrize("url", ["http://www.ejemplo.com/foto.png", "ftp://www.ejemplo.com/foto.png",
                                 "file:///etc/passwd", "https://www.ejemplo.com:8443/foto.png",
                                 "https://usuario:clave@www.ejemplo.com/foto.png"])
def test_solo_https_en_el_puerto_443_y_sin_credenciales(url):
    red = Red()
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar(url, time.monotonic() + 5)
    assert error.value.motivo == web.MOTIVO_ENLACE
    assert red.pedidos == [] and red.resueltos == []


def test_ip_privada_en_el_correo_se_avisa_en_respuesta_historial_y_log(factory, session, usuario, log, red):
    red.paginas["https://www.ejemplo.com/ok.jpg"] = FOTO
    graph = GraphConAdjuntos([correo_html(cuerpo(
        img("https://intranet.empresa.com/secreto.png"),
        img("http://www.ejemplo.com/inseguro.jpg"),
        img("https://www.ejemplo.com/ok.jpg")))])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["ok.jpg"]
    assert "No se guardaron 2 adjuntos (enlace de imagen no permitido)." in texto_respuesta(graph)
    [entrada] = historial(session, "attachments_skipped")
    assert "secreto (enlace de imagen no permitido)" in entrada.new_value
    assert "inseguro (enlace de imagen no permitido)" in entrada.new_value
    descartes = [r for r in log.records if r.levelname == "WARNING" and "descartado" in r.getMessage()]
    assert any("url=https://intranet.empresa.com/secreto.png" in r.getMessage()
               and "10.0.0.5" in r.getMessage() for r in descartes)
    assert any("esquema «http»" in r.getMessage() for r in descartes)


def test_redireccion_a_ip_privada_se_bloquea():
    red = Red(paginas={
        "https://www.ejemplo.com/foto.png": httpx.Response(
            302, headers={"Location": "https://169.254.169.254/latest/meta-data/iam"}),
        "https://cdn.ejemplo.com/foto.png": httpx.Response(
            301, headers={"Location": "https://intranet.empresa.com/foto.png"}),
    })
    for url in ("https://www.ejemplo.com/foto.png", "https://cdn.ejemplo.com/foto.png"):
        with pytest.raises(web.ImagenWebError) as error:
            red.descargar(url, time.monotonic() + 5)
        assert error.value.motivo == web.MOTIVO_ENLACE
    # Solo se pidió la primera de cada una; a la interna nunca se conectó.
    assert [p.headers["Host"] for p in red.pedidos] == ["www.ejemplo.com", "cdn.ejemplo.com"]


def test_redireccion_a_http_se_bloquea():
    red = Red(paginas={"https://www.ejemplo.com/a.png": httpx.Response(
        302, headers={"Location": "http://www.ejemplo.com/a.png"})})
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar("https://www.ejemplo.com/a.png", time.monotonic() + 5)
    assert "esquema «http»" in error.value.detalle


def test_hasta_3_redirecciones_y_la_cuarta_se_corta():
    paginas = {f"https://www.ejemplo.com/{i}.png": httpx.Response(302, headers={"Location": f"/{i + 1}.png"})
               for i in range(4)}
    paginas["https://www.ejemplo.com/3.png"] = FOTO
    red = Red(paginas=paginas)
    assert red.descargar("https://www.ejemplo.com/0.png", time.monotonic() + 5) == FOTO
    assert len(red.pedidos) == 4

    paginas["https://www.ejemplo.com/3.png"] = httpx.Response(302, headers={"Location": "/4.png"})
    paginas["https://www.ejemplo.com/4.png"] = FOTO
    red = Red(paginas=paginas)
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar("https://www.ejemplo.com/0.png", time.monotonic() + 5)
    assert "más de 3 redirecciones" in error.value.detalle
    assert len(red.pedidos) == 4


def test_mas_de_4_mb_se_corta_sin_bajarla_entera():
    leidos = []

    def trozos():
        for _ in range(200):  # 200 × 64 KB = 12.5 MB si se leyera todo
            leidos.append(1)
            yield b"\x00" * 65536

    red = Red(paginas={
        "https://www.ejemplo.com/grande.jpg": httpx.Response(
            200, headers={"Content-Length": str(6 * MB)}, content=b"\xff\xd8\xff"),
        "https://www.ejemplo.com/sin-largo.jpg": lambda request: httpx.Response(
            200, stream=_Flujo(trozos())),
    })
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar("https://www.ejemplo.com/grande.jpg", time.monotonic() + 5)
    assert error.value.motivo == web.MOTIVO_GRANDE and "Content-Length" in error.value.detalle

    with pytest.raises(web.ImagenWebError) as error:
        red.descargar("https://www.ejemplo.com/sin-largo.jpg", time.monotonic() + 5)
    assert error.value.motivo == web.MOTIVO_GRANDE
    assert len(leidos) <= 4 * 16 + 2


class _Flujo(httpx.SyncByteStream):
    def __init__(self, generador):
        self.generador = generador

    def __iter__(self):
        yield from self.generador


def test_mas_de_4_mb_en_el_correo_se_avisa(factory, session, usuario, red):
    red.paginas["https://www.ejemplo.com/enorme.png"] = httpx.Response(
        200, headers={"Content-Length": str(5 * MB)}, content=b"x")
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/enorme.png")))])
    revisar(factory, graph)
    assert adjuntos_en_bd(session) == []
    assert "No se guardó 1 adjunto (tipo no permitido o más de 4 MB)." in texto_respuesta(graph)


def test_timeout_de_la_descarga():
    def lento(request):
        raise httpx.ReadTimeout("lento", request=request)

    red = Red(paginas={"https://www.ejemplo.com/lenta.jpg": lento})
    with pytest.raises(web.ImagenWebError) as error:
        red.descargar("https://www.ejemplo.com/lenta.jpg", time.monotonic() + 5)
    assert (error.value.motivo, error.value.detalle) == (web.MOTIVO_ERROR, "timeout")


def test_timeout_del_dns_no_espera_mas_que_el_limite():
    red = Red()

    def dns_lento(host):
        time.sleep(2)
        return [IP_PUBLICA]

    inicio = time.monotonic()
    with pytest.raises(web.ImagenWebError) as error:
        web.descargar("https://www.ejemplo.com/a.jpg", time.monotonic() + 0.3,
                      transporte=red.transporte, resolver=dns_lento)
    assert time.monotonic() - inicio < 1.5
    assert "timeout al resolver" in error.value.detalle


def test_el_tiempo_de_cada_imagen_es_5_s_y_respeta_el_de_la_revision(factory, session, usuario, monkeypatch):
    plazos = []

    def descargar(src, hasta):
        plazos.append(hasta - time.monotonic())
        raise web.ImagenWebError(web.MOTIVO_ERROR, "timeout")

    monkeypatch.setattr(ca, "descargar_imagen", descargar)
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/a.jpg")))])
    revisar(factory, graph)
    assert 4.5 < plazos[0] <= 5
    assert "No se guardó 1 adjunto (no se pudo descargar)." in texto_respuesta(graph)

    # Con la revisión casi vencida (Vercel), el plazo es lo que queda.
    ticket = session.scalars(select(Ticket)).one()
    mensaje = correo_html(cuerpo(img("https://www.ejemplo.com/b.jpg")))
    graph2 = GraphConAdjuntos([mensaje])
    plazos.clear()
    ca.guardar(factory, graph2.cliente, mensaje["id"], ticket.id, "ana@data.cr",
               hasta=time.monotonic() - ca.MARGEN_DESCARGA_S + 1)
    assert 0 < plazos[0] <= 1
    plazos.clear()
    resultado = ca.guardar(factory, graph2.cliente, mensaje["id"], ticket.id, "ana@data.cr",
                           hasta=time.monotonic() - 100)
    assert plazos == [] and resultado.omitidos == [("b", ca.MOTIVO_TIEMPO)]


def test_una_imagen_lenta_no_impide_guardar_las_demas(factory, session, usuario, log, red):
    def lento(request):
        raise httpx.ConnectTimeout("lento", request=request)

    red.paginas["https://www.ejemplo.com/lenta.jpg"] = lento
    red.paginas["https://www.ejemplo.com/rapida.jpg"] = FOTO
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/lenta.jpg"),
                                                 img("https://www.ejemplo.com/rapida.jpg")))])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["rapida.jpg"]
    assert "No se guardó 1 adjunto (no se pudo descargar)." in texto_respuesta(graph)
    assert "«lenta» (url=https://www.ejemplo.com/lenta.jpg" in log.text and "timeout" in log.text


# --- Lo que se ignora sin avisar -----------------------------------------------


def test_pixel_de_rastreo_logo_firma_y_repetida_se_ignoran_sin_avisar(factory, session, usuario, log, red):
    red.paginas["https://www.ejemplo.com/pixel.gif"] = b"GIF89a\x01\x00\x01\x00"
    red.paginas["https://www.ejemplo.com/p.png"] = imagenes.png(1)       # chica, sin atributos
    red.paginas["https://www.ejemplo.com/logo-firma.png"] = imagenes.png(40, relleno=b"\x09")
    red.paginas["https://www.ejemplo.com/foto.jpg"] = FOTO
    red.paginas["https://cdn.ejemplo.com/la-misma.jpg"] = FOTO               # misma huella
    html = cuerpo(
        img("https://track.ejemplo.com/open?id=123", width="1", height="1"),
        img("https://www.ejemplo.com/pixel.gif", style="display:none"),
        img("https://www.ejemplo.com/p.png"),
        img("https://www.ejemplo.com/foto.jpg"),
        img("https://cdn.ejemplo.com/la-misma.jpg"),
    ) + '<div id="Signature"><p>Ana Pérez</p>' + img("https://www.ejemplo.com/logo-firma.png") + "</div>"
    graph = GraphConAdjuntos([correo_html(html)])
    revisar(factory, graph)

    assert [a.filename for a in adjuntos_en_bd(session)] == ["foto.jpg"]
    assert "No se guard" not in texto_respuesta(graph)
    assert historial(session, "attachments_skipped") == []
    # El píxel con width=1 y el oculto ni se descargan; la firma tampoco.
    hosts = [p.url.raw_path.decode() for p in red.pedidos]
    assert hosts == ["/p.png", "/foto.jpg", "/la-misma.jpg"]
    assert "píxel de rastreo u oculta" in log.text
    assert "píxel de rastreo o logo" in log.text
    assert "la misma imagen ya está en el ticket" in log.text


def test_imagen_que_ya_esta_en_el_ticket_no_se_vuelve_a_guardar_en_el_comentario(factory, session, usuario, red):
    red.paginas["https://www.ejemplo.com/error.jpg"] = FOTO
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/error.jpg")))])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()
    red.paginas["https://www.ejemplo.com/otra.png"] = CAPTURA
    respuesta = correo_html(
        cuerpo(img("https://www.ejemplo.com/otra.png"), img("https://www.ejemplo.com/error.jpg"),
               texto="Sigue igual, otra captura."),
        asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}", cuerpo="Sigue igual, otra captura.",
        msg_id="<sigue@data.cr>")
    graph2 = GraphConAdjuntos([respuesta])
    assert revisar(factory, graph2) == {"comentario": 1}
    assert [a.filename for a in adjuntos_en_bd(session, ticket.id)] == ["error.jpg", "otra.png"]
    assert "No se guard" not in texto_respuesta(graph2)


def test_las_imagenes_de_lo_citado_no_se_toman(factory, session, usuario, red):
    red.paginas["https://www.ejemplo.com/nueva.jpg"] = FOTO
    red.paginas["https://www.ejemplo.com/vieja.png"] = CAPTURA
    unico = cuerpo(img("https://www.ejemplo.com/nueva.jpg"))
    completo = unico + ('<div id="divRplyFwdMsg"><b>De:</b> Soporte</div><div>'
                        + img("https://www.ejemplo.com/vieja.png") + "</div>")
    graph = GraphConAdjuntos([correo_html(completo, unico=unico)])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["nueva.jpg"]
    assert [p.url.raw_path.decode() for p in red.pedidos] == ["/nueva.jpg"]


def test_las_cid_siguen_siendo_adjuntos_en_linea_y_no_se_bajan_de_la_red(factory, session, usuario, red):
    captura = archivo("image002.png", CAPTURA, "image/png", inline=True)
    mensaje = correo_html(cuerpo(img(f"cid:{captura['contentId']}")))
    mensaje["_adjuntos"] = [captura]
    graph = GraphConAdjuntos([mensaje])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["image002.png"]
    assert red.pedidos == []


# --- WebP, GIF y AVIF ----------------------------------------------------------


def _webp(lado=128):
    Image = pytest.importorskip("PIL.Image")
    imagen = Image.frombytes("RGB", (lado, lado), os.urandom(lado * lado * 3))
    salida = io.BytesIO()
    imagen.save(salida, format="WEBP", lossless=True)
    return salida.getvalue()


def test_webp_se_convierte_a_png(factory, session, usuario, log, red):
    webp = _webp()
    assert len(webp) > ca.MIN_BYTES_IMAGEN
    red.paginas["https://www.ejemplo.com/pantalla-azul.webp"] = webp
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/pantalla-azul.webp")))])
    revisar(factory, graph)
    [adjunto] = adjuntos_en_bd(session)
    assert (adjunto.filename, adjunto.content_type) == ("pantalla-azul.png", "image/png")
    guardado = next(p for p in ca.adjuntos_service.carpeta_local().rglob("*.png"))
    from PIL import Image
    with Image.open(guardado) as imagen:
        assert imagen.format == "PNG" and imagen.size == (128, 128)
    assert "convertida de webp a PNG" in log.text


def test_webp_sin_pillow_se_descarta_con_motivo(factory, session, usuario, log, red, monkeypatch):
    monkeypatch.setattr(web, "_pillow", lambda: None)
    red.paginas["https://www.ejemplo.com/foto.webp"] = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20000
    graph = GraphConAdjuntos([correo_html(cuerpo(img("https://www.ejemplo.com/foto.webp")))])
    revisar(factory, graph)
    assert adjuntos_en_bd(session) == []
    assert "No se guardó 1 adjunto (tipo no permitido o más de 4 MB)." in texto_respuesta(graph)
    assert "webp y Pillow no está instalado" in log.text


def test_gif_animado_se_convierte_con_su_primer_cuadro():
    Image = pytest.importorskip("PIL.Image")
    cuadros = [Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3)) for _ in range(3)]
    salida = io.BytesIO()
    cuadros[0].save(salida, format="GIF", save_all=True, append_images=cuadros[1:])
    imagen = web.preparar(salida.getvalue())
    assert (imagen.ext, imagen.convertida, imagen.ancho, imagen.alto) == (".png", "gif", 64, 64)
    assert ca.adjuntos_service.validar("a.png", imagen.contenido)[1] == "image/png"


def test_jpeg_cortado_se_rechaza_por_contenido():
    with pytest.raises(web.ImagenWebError) as error:
        web.preparar(FOTO[:2000])
    assert error.value.motivo == web.MOTIVO_DANADA


# --- Límites compartidos con los adjuntos --------------------------------------


def test_los_5_por_correo_se_comparten_con_los_adjuntos(factory, session, usuario, red):
    for i in range(3):
        red.paginas[f"https://www.ejemplo.com/web{i}.png"] = imagenes.png(30, relleno=bytes([40 + i]))
    adjuntos = [archivo(f"adj{i}.png", imagenes.png(30, relleno=bytes([10 + i])), "image/png")
                for i in range(4)]
    mensaje = correo_html(cuerpo(*[img(f"https://www.ejemplo.com/web{i}.png") for i in range(3)]))
    mensaje["_adjuntos"] = adjuntos
    graph = GraphConAdjuntos([mensaje])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == [
        "adj0.png", "adj1.png", "adj2.png", "adj3.png", "web0.png"]
    assert "No se guardaron 2 adjuntos (más de 5 por correo)." in texto_respuesta(graph)
    # Las que ya no entraban no se bajaron.
    assert len(red.pedidos) == 1


def test_el_ticket_lleno_no_baja_imagenes(factory, session, usuario, red):
    graph = GraphConAdjuntos([crear_correo()])
    revisar(factory, graph)
    ticket = session.scalars(select(Ticket)).one()
    for i in range(10):
        ca.adjuntos_service.subir(session, ticket, None, f"previo{i}.txt", b"texto")
    red.paginas["https://www.ejemplo.com/una.jpg"] = FOTO
    respuesta = correo_html(cuerpo(img("https://www.ejemplo.com/una.jpg")),
                            asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                            cuerpo="Otra foto.", msg_id="<lleno@data.cr>")
    graph2 = GraphConAdjuntos([respuesta])
    revisar(factory, graph2)
    assert red.pedidos == []
    assert "No se guardó 1 adjunto (el ticket ya tiene 10 adjuntos)." in texto_respuesta(graph2)


def test_en_ticket_cerrado_no_se_baja_nada(factory, session, usuario, red):
    ticket = Ticket(title="Ticket cerrado de prueba", description="Ya se resolvió.",
                    category="Hardware", priority="Media", state="Cerrado")
    session.add(ticket)
    session.commit()
    mensaje = correo_html(cuerpo(img("https://www.ejemplo.com/foto.jpg")))
    graph = GraphConAdjuntos([mensaje])
    assert ca.guardar(factory, graph.cliente, mensaje["id"], ticket.id, "ana@data.cr") is None
    assert red.pedidos == []
    assert session.scalars(select(Attachment)).all() == []


def test_si_no_se_puede_leer_el_html_igual_se_guardan_los_adjuntos(factory, session, usuario, log, monkeypatch):
    def falla(self, mensaje_id):
        raise RuntimeError("Graph caído")

    from backend.services import correo_service as cs
    monkeypatch.setattr(cs.ClienteGraph, "cuerpo_html", falla)
    mensaje = crear_correo()
    mensaje["_adjuntos"] = [archivo("captura.png", CAPTURA, "image/png")]
    graph = GraphConAdjuntos([mensaje])
    revisar(factory, graph)
    assert [a.filename for a in adjuntos_en_bd(session)] == ["captura.png"]
    assert "no se pudo leer el HTML del correo" in log.text


# --- Unidades ------------------------------------------------------------------


def test_extraer_salta_cid_firma_y_repetidas():
    html = ('<p>Hola</p><img src="cid:image001.png@01">'
            '<img src="https://a.com/x.png"><IMG SRC=\'https://a.com/x.png\'>'
            '<img src="data:image/png;base64,AAAA" width="300">'
            '<p>--&nbsp;<br>Ana</p><img src="https://a.com/firma.png">')
    assert [i.src for i in web.extraer([html])] == ["https://a.com/x.png", "data:image/png;base64,AAAA"]
    assert [i.src for i in web.extraer(['<img src="https://a.com/1.png">',
                                        '<img src="https://a.com/1.png"><img src="https://a.com/2.png">'])] \
        == ["https://a.com/1.png", "https://a.com/2.png"]


@pytest.mark.parametrize("ip, bloqueada", [
    ("8.8.8.8", False), (IP_PUBLICA, False), ("2606:4700::1111", False),
    ("127.0.0.1", True), ("10.0.0.1", True), ("172.16.0.1", True), ("172.31.255.255", True),
    ("172.32.0.1", False), ("192.168.0.1", True), ("169.254.169.254", True), ("100.64.0.1", True),
    ("0.0.0.0", True), ("224.0.0.1", True), ("::1", True), ("fc00::1", True), ("fe80::1", True),
    ("::ffff:127.0.0.1", True), ("2002:a00:1::", True),
])
def test_ip_bloqueada(ip, bloqueada):
    import ipaddress
    assert web.ip_bloqueada(ipaddress.ip_address(ip)) is bloqueada


def test_mailpit_devuelve_el_html():
    from backend.services import correo_service as cs
    cliente = cs.ClienteMailpit("mailpit", 1025, "kcastro@data.cr", "http://mailpit:8025")
    cliente._leidos["m1"] = {"HTML": "<p>hola</p>"}
    cliente._leidos["m2"] = {"HTML": "", "Text": "hola"}
    assert cliente.cuerpo_html("m1") == ["<p>hola</p>"]
    assert cliente.cuerpo_html("m2") == []
