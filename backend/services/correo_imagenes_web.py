"""Imágenes del **cuerpo HTML** de un correo que no vienen como adjunto.

Cuando alguien copia una imagen de una página (por ejemplo de Google) y la
pega en Outlook, el correo no trae adjunto: en el HTML queda
``<img src="https://…">`` o ``<img src="data:image/…;base64,…">``. Este
módulo encuentra esas imágenes, las baja (o decodifica) y las deja listas
para guardarlas como los demás adjuntos del correo
(:mod:`backend.services.correo_adjuntos` aplica los límites y las guarda).

Descarga de ``https://`` (la URL la escribe quien manda el correo, así que
se trata como **no confiable**):

* Solo ``https`` y el puerto 443; nunca ``http`` ni otros esquemas.
* Se resuelve el nombre y se **bloquea** toda IP que no sea pública
  (privadas, locales, link-local, metadatos de la nube, CGNAT, multicast…).
  La conexión va a la IP ya revisada (con el nombre en SNI y ``Host``), así
  un DNS que cambia de respuesta no puede llevarla a una IP interna. Lo mismo
  en cada redirección, como máximo :data:`MAX_REDIRECCIONES`.
* :data:`TIMEOUT_S` por imagen (y nunca más allá del tiempo de la revisión).
* Se corta al pasar :data:`MAX_BYTES` (4 MB).
* Sin cookies, sin credenciales, sin proxy del entorno, con un User-Agent
  genérico.

El contenido se valida por sus bytes: JPEG o PNG entera (lo vuelve a revisar
:func:`adjuntos_service.validar` al guardar). WebP, GIF y AVIF se convierten
a PNG si está Pillow; si no, se descartan con motivo.
"""

from __future__ import annotations

import base64
import binascii
import io
import ipaddress
import logging
import os
import re
import socket
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from backend.services import adjuntos_service

logger = logging.getLogger("backend.services.correo_service.imagenes_web")

TIMEOUT_S = 5.0
MAX_REDIRECCIONES = 3
MAX_BYTES = adjuntos_service.MAX_BYTES
# Imágenes del cuerpo que se miran como máximo por correo (un boletín con
# decenas de imágenes no debe gastar la revisión entera).
MAX_IMAGENES = 10
# Las imágenes del cuerpo se descartan como píxel de rastreo o ícono si un
# lado mide menos de esto o si pesan menos de MIN_BYTES. No se usa el mínimo
# de 15 KB de los adjuntos: una imagen copiada de Google suele pesar menos
# (por ejemplo 9 KB con 172×178 px).
MIN_LADO_PX = 48
MIN_BYTES = 1024
# Más píxeles que esto no se convierten (una «bomba» de descompresión).
MAX_PIXELES = 25_000_000
USER_AGENT = "Mozilla/5.0 (compatible; TicketeraSoporte/1.0)"
ACEPTA = "image/png,image/jpeg,image/webp,image/gif,image/avif;q=0.9,*/*;q=0.1"
TAMANO_TROZO = 64 * 1024

# Motivos (los mismos textos que los demás adjuntos del correo).
MOTIVO_TIPO = "tipo no permitido"
MOTIVO_GRANDE = "más de 4 MB"
MOTIVO_DANADA = "imagen dañada o incompleta"
MOTIVO_ERROR = "no se pudo descargar"
MOTIVO_ENLACE = "enlace de imagen no permitido"


class ImagenWebError(Exception):
    """La imagen no se puede usar: ``motivo`` (para la respuesta y el
    historial) y ``detalle`` (para el log)."""

    def __init__(self, motivo: str, detalle: str = ""):
        super().__init__(f"{motivo}: {detalle}" if detalle else motivo)
        self.motivo = motivo
        self.detalle = detalle or motivo


# ---------------------------------------------------------------------------
# Las <img> del HTML
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImagenHtml:
    src: str
    ancho: str = ""
    alto: str = ""
    estilo: str = ""

    @property
    def es_data(self) -> bool:
        return self.src[:5].lower() == "data:"

    def parece_pixel(self) -> bool:
        """Píxel de rastreo o imagen oculta, por sus atributos (sin bajarla)."""
        if _numero(self.ancho) in (0, 1) or _numero(self.alto) in (0, 1):
            return True
        estilo = re.sub(r"\s+", "", self.estilo.lower())
        if "display:none" in estilo or "visibility:hidden" in estilo:
            return True
        return bool(re.search(r"(?:^|;)(?:max-)?(?:width|height):[01](?:px)?(?:;|$)", estilo))


def _numero(valor: str) -> int | None:
    coincide = re.match(r"\s*(\d+)\s*(?:px)?\s*$", valor or "")
    return int(coincide.group(1)) if coincide else None


class _Imgs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.imagenes: list[ImagenHtml] = []

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        datos = {k.lower(): (v or "") for k, v in attrs}
        src = datos.get("src", "").strip()
        if src:
            self.imagenes.append(ImagenHtml(src, datos.get("width", ""), datos.get("height", ""),
                                            datos.get("style", "")))

    handle_startendtag = handle_starttag


# Dónde empieza la firma o el correo citado: las imágenes de ahí en adelante
# no son de este correo (o son el logo de la firma).
_CORTES = re.compile(
    r"""(?isx)
      <[a-z]+\b[^>]*\b(?:id|class|data-smartmail)\s*=\s*["']?[^"'>]*signature   # Outlook, Gmail, Thunderbird
    | <a\b[^>]*\bname\s*=\s*["']?_MailAutoSig                                   # Outlook de escritorio
    | <div\b[^>]*\bid\s*=\s*["']?(?:x_)?(?:divRplyFwdMsg|appendonsend|mail-editor-reference-message-container)
    | <div\b[^>]*\bclass\s*=\s*["']?[^"'>]*gmail_quote
    | <blockquote\b
    | (?:^|>)\s*--(?:\s|&nbsp;|&\#160;)*<br                                      # «-- » antes de la firma
    """)


def _antes_de_la_firma(html: str) -> str:
    coincide = _CORTES.search(html)
    return html[:coincide.start()] if coincide else html


def extraer(htmls: list[str]) -> list[ImagenHtml]:
    """Las ``<img>`` que no son ``cid:`` (esas vienen como adjunto en
    línea), antes de la firma y de lo citado, sin repetir el ``src``. Se
    juntan las de cada HTML (``uniqueBody`` y ``body``) en orden."""
    vistas: set[str] = set()
    imagenes: list[ImagenHtml] = []
    for html in htmls:
        if not html:
            continue
        lector = _Imgs()
        try:
            lector.feed(_antes_de_la_firma(html))
            lector.close()
        except Exception:  # noqa: BLE001 — HTML roto: lo que se haya leído
            logger.warning("HTML del correo ilegible al buscar imágenes", exc_info=True)
        for imagen in lector.imagenes:
            if imagen.src[:4].lower() == "cid:" or imagen.src in vistas:
                continue
            vistas.add(imagen.src)
            imagenes.append(imagen)
    return imagenes


def recortar(src: str) -> str:
    """El ``src`` para el log: sin el base64 ni la consulta (puede llevar
    claves) y como máximo 100 caracteres."""
    if src[:5].lower() == "data:":
        cabecera = src.split(",", 1)[0][:60]
        return f"{cabecera},… ({len(src)} caracteres)"
    sin_consulta, signo, _ = src.partition("?")
    sin_consulta = sin_consulta.split("#", 1)[0]
    texto = sin_consulta[:100] + ("…" if len(sin_consulta) > 100 else "")
    return texto + ("?…" if signo else "")


# ---------------------------------------------------------------------------
# data:image/…;base64,…
# ---------------------------------------------------------------------------

_DATA = re.compile(r"(?is)^data:([^,;]*)((?:;[^,;]*)*),(.*)$")


def decodificar_data(src: str) -> bytes:
    coincide = _DATA.match(src)
    if not coincide:
        raise ImagenWebError(MOTIVO_TIPO, "data: mal formado")
    tipo, parametros, datos = coincide.groups()
    if not tipo.lower().startswith("image/"):
        raise ImagenWebError(MOTIVO_TIPO, f"data: de tipo {tipo or '-'}")
    if "base64" not in parametros.lower():
        raise ImagenWebError(MOTIVO_TIPO, f"data: {tipo} sin base64")
    datos = re.sub(r"\s+", "", urllib.parse.unquote(datos))
    if len(datos) * 3 // 4 > MAX_BYTES + 3:
        raise ImagenWebError(MOTIVO_GRANDE, f"unos {len(datos) * 3 // 4} bytes")
    try:
        return base64.b64decode(datos + "=" * (-len(datos) % 4), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ImagenWebError(MOTIVO_DANADA, f"base64 inválido ({error})") from None


# ---------------------------------------------------------------------------
# https:// con protecciones
# ---------------------------------------------------------------------------

_resolutor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dns-imagen")


def ip_bloqueada(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """¿No es una IP pública de Internet? (127/8, 10/8, 172.16/12,
    192.168/16, 169.254/16 —metadatos—, 100.64/10, 0/8, ::1, fc00::/7,
    fe80::/10, multicast, reservadas…). Las IPv6 que llevan una IPv4
    adentro (::ffff:a.b.c.d, 6to4, Teredo) se juzgan por esa IPv4."""
    if isinstance(ip, ipaddress.IPv6Address):
        interna = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if interna is not None and ip_bloqueada(interna):
            return True
    return not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def _resolver_sistema(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def _ips(host: str, resolver, restante: float) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Las IP de ``host`` (todas tienen que ser públicas)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    futuro = _resolutor.submit(resolver, host)
    try:
        crudas = futuro.result(timeout=max(0.1, restante))
    except TiempoAgotado:
        raise ImagenWebError(MOTIVO_ERROR, f"timeout al resolver {host}") from None
    except (OSError, UnicodeError) as error:
        raise ImagenWebError(MOTIVO_ERROR, f"no se pudo resolver {host} ({error})") from None
    ips = []
    for cruda in crudas:
        try:
            ips.append(ipaddress.ip_address(cruda.split("%", 1)[0]))
        except ValueError:
            continue
    if not ips:
        raise ImagenWebError(MOTIVO_ERROR, f"{host} no tiene dirección")
    return ips


def _revisar_url(url: httpx.URL) -> None:
    if url.scheme != "https":
        raise ImagenWebError(MOTIVO_ENLACE, f"esquema «{url.scheme or '-'}» (solo https)")
    if not url.host:
        raise ImagenWebError(MOTIVO_ENLACE, "sin servidor")
    if url.port not in (None, 443):
        raise ImagenWebError(MOTIVO_ENLACE, f"puerto {url.port} (solo 443)")
    if url.userinfo:
        raise ImagenWebError(MOTIVO_ENLACE, "con usuario o clave en el enlace")


def descargar(src: str, hasta: float, transporte: httpx.BaseTransport | None = None,
              resolver=_resolver_sistema) -> bytes:
    """Baja la imagen de ``src`` (``https://``) antes de ``hasta``
    (``time.monotonic()``). Lanza :class:`ImagenWebError`."""
    try:
        url = httpx.URL(src)
    except (httpx.InvalidURL, ValueError, TypeError) as error:
        raise ImagenWebError(MOTIVO_ENLACE, f"enlace inválido ({error})") from None
    cliente = httpx.Client(transport=transporte or httpx.HTTPTransport(retries=0),
                           follow_redirects=False, trust_env=False)
    try:
        for salto in range(MAX_REDIRECCIONES + 1):
            _revisar_url(url)
            host = url.raw_host.decode("ascii")  # en punycode si tiene tildes
            restante = hasta - time.monotonic()
            if restante <= 0:
                raise ImagenWebError(MOTIVO_ERROR, "timeout")
            ips = _ips(host, resolver, restante)
            bloqueadas = [str(ip) for ip in ips if ip_bloqueada(ip)]
            if bloqueadas:
                raise ImagenWebError(MOTIVO_ENLACE,
                                     f"{host} es una dirección interna ({', '.join(bloqueadas)})")
            restante = hasta - time.monotonic()
            if restante <= 0:
                raise ImagenWebError(MOTIVO_ERROR, "timeout")
            pedido = httpx.Request(
                "GET", url.copy_with(host=str(ips[0])),
                headers={"Host": url.netloc.decode("ascii"), "User-Agent": USER_AGENT,
                         "Accept": ACEPTA, "Accept-Encoding": "identity"},
                extensions={"sni_hostname": host,
                            "timeout": httpx.Timeout(restante).as_dict()})
            try:
                respuesta = cliente.send(pedido, stream=True)
            except httpx.TimeoutException:
                raise ImagenWebError(MOTIVO_ERROR, "timeout") from None
            except httpx.HTTPError as error:
                raise ImagenWebError(MOTIVO_ERROR, f"{type(error).__name__}: {error}") from None
            try:
                if respuesta.status_code in (301, 302, 303, 307, 308):
                    destino = respuesta.headers.get("location")
                    if not destino:
                        raise ImagenWebError(MOTIVO_ERROR, f"redirección {respuesta.status_code} sin destino")
                    if salto == MAX_REDIRECCIONES:
                        raise ImagenWebError(MOTIVO_ENLACE,
                                             f"más de {MAX_REDIRECCIONES} redirecciones")
                    try:
                        url = url.join(destino)
                    except (httpx.InvalidURL, ValueError) as error:
                        raise ImagenWebError(MOTIVO_ENLACE, f"redirección inválida ({error})") from None
                    continue
                if respuesta.status_code != 200:
                    raise ImagenWebError(MOTIVO_ERROR, f"HTTP {respuesta.status_code}")
                return _leer(respuesta, hasta)
            finally:
                respuesta.close()
        raise ImagenWebError(MOTIVO_ENLACE, f"más de {MAX_REDIRECCIONES} redirecciones")
    finally:
        cliente.close()


def _leer(respuesta: httpx.Response, hasta: float) -> bytes:
    largo = respuesta.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > MAX_BYTES:
        raise ImagenWebError(MOTIVO_GRANDE, f"Content-Length {largo}")
    contenido = bytearray()
    try:
        for trozo in respuesta.iter_bytes(TAMANO_TROZO):  # ya descomprimido: se cuenta lo real
            contenido += trozo
            if len(contenido) > MAX_BYTES:
                raise ImagenWebError(MOTIVO_GRANDE, f"se cortó al pasar {MAX_BYTES} bytes")
            if time.monotonic() > hasta:
                raise ImagenWebError(MOTIVO_ERROR, f"timeout ({len(contenido)} bytes bajados)")
    except httpx.TimeoutException:
        raise ImagenWebError(MOTIVO_ERROR, f"timeout ({len(contenido)} bytes bajados)") from None
    except httpx.HTTPError as error:
        raise ImagenWebError(MOTIVO_ERROR, f"{type(error).__name__}: {error}") from None
    return bytes(contenido)


# ---------------------------------------------------------------------------
# Contenido: qué imagen es, tamaño en píxeles y conversión
# ---------------------------------------------------------------------------


def formato(contenido: bytes) -> str | None:
    """``jpg``, ``png``, ``webp``, ``gif``, ``avif`` (por los bytes) o ``None``."""
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    if contenido[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if contenido[4:8] == b"ftyp" and contenido[8:12] in (b"avif", b"avis"):
        return "avif"
    return None


def _medidas_png(contenido: bytes) -> tuple[int, int]:
    return int.from_bytes(contenido[16:20], "big"), int.from_bytes(contenido[20:24], "big")


def _medidas_jpeg(contenido: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 4 <= len(contenido):
        if contenido[i] != 0xFF:
            return None
        marcador = contenido[i + 1]
        if marcador in (0xD8, 0x01) or 0xD0 <= marcador <= 0xD7 or marcador == 0xFF:
            i += 1 if marcador == 0xFF else 2
            continue
        largo = int.from_bytes(contenido[i + 2:i + 4], "big")
        if 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC):
            if i + 9 <= len(contenido):
                return (int.from_bytes(contenido[i + 7:i + 9], "big"),
                        int.from_bytes(contenido[i + 5:i + 7], "big"))
            return None
        i += 2 + largo
    return None


def _pillow():
    try:
        from PIL import Image  # noqa: PLC0415 — opcional
    except ImportError:
        return None
    return Image


def _a_png(contenido: bytes, origen: str) -> tuple[bytes, int, int]:
    Image = _pillow()
    if Image is None:
        raise ImagenWebError(MOTIVO_TIPO, f"{origen} y Pillow no está instalado para convertirla")
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            ancho, alto = imagen.size
            if ancho * alto > MAX_PIXELES:
                raise ImagenWebError(MOTIVO_GRANDE, f"{origen} de {ancho}×{alto} píxeles")
            imagen.seek(0)
            if imagen.mode not in ("RGB", "RGBA", "L", "LA"):
                imagen = imagen.convert("RGBA")
            salida = io.BytesIO()
            imagen.save(salida, format="PNG")
    except ImagenWebError:
        raise
    except Image.DecompressionBombError:
        raise ImagenWebError(MOTIVO_GRANDE, f"{origen} demasiado grande para convertir") from None
    except Exception as error:  # noqa: BLE001 — UnidentifiedImageError, OSError (dañada, sin códec)
        motivo = MOTIVO_TIPO if "cannot identify" in str(error) else MOTIVO_DANADA
        raise ImagenWebError(motivo, f"{origen} no se pudo convertir ({error})") from None
    return salida.getvalue(), ancho, alto


@dataclass
class Imagen:
    contenido: bytes
    ext: str           # ".jpg" o ".png"
    ancho: int | None
    alto: int | None
    convertida: str = ""  # «webp», «gif»… si se pasó a PNG


def por_que_chica(tamano: int, imagen: Imagen) -> str | None:
    """Por qué se descarta (píxel de rastreo o ícono) o ``None``. ``tamano``
    es lo que se bajó o decodificó; si no se pudieron leer las medidas de un
    JPEG, se mira solo el peso."""
    if tamano < MIN_BYTES:
        return f"píxel de rastreo o ícono (menos de 1 KB: {tamano} bytes)"
    lados = [lado for lado in (imagen.ancho, imagen.alto) if lado is not None]
    if any(lado < MIN_LADO_PX for lado in lados):
        return (f"píxel de rastreo o ícono (menos de {MIN_LADO_PX} px: "
                f"{imagen.ancho}×{imagen.alto} px, {tamano} bytes)")
    return None


def preparar(contenido: bytes) -> Imagen:
    """La imagen lista para guardar (jpg o png entera) o
    :class:`ImagenWebError`."""
    if not contenido:
        raise ImagenWebError(MOTIVO_DANADA, "vacía")
    tipo = formato(contenido)
    if tipo in ("webp", "gif", "avif"):
        png, ancho, alto = _a_png(contenido, tipo)
        if len(png) > MAX_BYTES:
            raise ImagenWebError(MOTIVO_GRANDE, f"{tipo} convertida a PNG pesa {len(png)} bytes")
        return Imagen(png, ".png", ancho, alto, convertida=tipo)
    if tipo == "png":
        if not adjuntos_service._png_completo(contenido):
            raise ImagenWebError(MOTIVO_DANADA, "PNG incompleto o dañado")
        return Imagen(contenido, ".png", *_medidas_png(contenido))
    if tipo == "jpg":
        if not adjuntos_service._jpeg_completo(contenido):
            raise ImagenWebError(MOTIVO_DANADA, "JPEG incompleto o dañado")
        medidas = _medidas_jpeg(contenido) or (None, None)
        return Imagen(contenido, ".jpg", *medidas)
    inicio = contenido[:60].lstrip().lower()
    que = "SVG" if b"<svg" in inicio or inicio.startswith(b"<?xml") else (
        "HTML" if inicio.startswith((b"<!doctype", b"<html")) else "desconocido")
    raise ImagenWebError(MOTIVO_TIPO, f"no es una imagen jpg ni png (contenido {que})")


# ---------------------------------------------------------------------------
# Nombre del archivo
# ---------------------------------------------------------------------------

_EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")
_NOMBRE_RAZONABLE = re.compile(r"^[\w][\w\-. ()]{0,79}$")


def nombre_del_enlace(src: str, ext: str) -> str | None:
    """El nombre del archivo del enlace (``…/fotos/router-roto.jpg``) con la
    extensión de lo que realmente es, si es razonable: con extensión de
    imagen, con letras, sin caracteres raros y de hasta 80 caracteres (no un
    código largo como ``AAAbbb123…``)."""
    if src[:5].lower() == "data:":
        return None
    ruta = urllib.parse.urlsplit(src).path
    nombre = adjuntos_service.limpiar_nombre(urllib.parse.unquote(ruta.rsplit("/", 1)[-1]))
    raiz, ext_original = os.path.splitext(nombre)
    if ext_original.lower() not in _EXT_IMAGEN or not _NOMBRE_RAZONABLE.match(nombre):
        return None
    if not re.search(r"[^\W\d_]", raiz) or re.fullmatch(r"[A-Za-z0-9_-]{32,}", raiz):
        return None
    return raiz + ext
