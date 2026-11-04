"""Adjuntos de los correos que crean un ticket o agregan un comentario.

Se guardan con el mismo almacén y las mismas validaciones que los que se
suben en la ticketera (:mod:`backend.services.adjuntos_service`), marcados
como ``correo``.

1. Primero se pide a Graph **la lista** de adjuntos (nombre, tipo y tamaño,
   sin el contenido) y se decide cuáles entran.
2. Después se descargan **solo los elegidos**, uno por uno: así una revisión
   del buzón no se pasa del tiempo de la función de Vercel.

Las **imágenes en línea** (pegadas dentro del texto, ``isInline`` con
``contentId``: por ejemplo una captura de pantalla) se guardan como los demás
adjuntos, salvo las de la firma.

Se ignoran sin avisar (no son archivos que la persona quiso mandar):

* las imágenes de menos de :data:`MIN_BYTES_IMAGEN` (íconos y logos chicos);
* las imágenes en línea que **se repiten como logo**: dos o más con el mismo
  tamaño y tipo en el mismo correo (no se descargan), o una imagen chica
  (menos de :data:`MAX_BYTES_LOGO`) igual (misma huella SHA-256) a una que
  ya llegó en un correo anterior del mismo remitente;
* las imágenes en línea que ya están en el ticket (misma huella);
* las imágenes en línea de un tipo que no se guarda (gif, bmp…);
* los adjuntos que son otro correo (``itemAttachment``) o un enlace a
  OneDrive o SharePoint (``referenceAttachment``).

Se **omiten** (y se avisa en la respuesta automática, el historial y el log):
tipo no permitido, más de 4 MB, más de :data:`MAX_ARCHIVOS_CORREO` archivos o
de :data:`MAX_BYTES_CORREO` en el correo, o el ticket ya tiene 10 adjuntos.
En un ticket Cerrado no se guarda nada.

**Imágenes del cuerpo HTML** que no vienen como adjunto (copiadas de una
página y pegadas en Outlook: ``<img src="https://…">`` o ``data:image/…``):
después de los adjuntos, con los mismos límites (lo que queda de los 5 y
10 MB del correo y de los 10 del ticket). Cómo se bajan sin riesgo y se
validan: :mod:`backend.services.correo_imagenes_web`. Se ignoran sin avisar
los píxeles de rastreo e íconos (un lado de menos de 48 px, o menos de
1 KB; **no** se usa el mínimo de 15 KB de los adjuntos, porque una imagen
copiada de Google suele pesar menos), las de la firma o lo citado y las que
ya están en el ticket.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, replace

from collections import Counter

from sqlalchemy import func, select

from backend.models import Attachment, Ticket, User
from backend.services import adjuntos_service, correo_imagenes_web as web, ticket_service
from backend.services.adjuntos_service import (
    AdjuntoInvalidoError,
    AlmacenNoConfiguradoError,
    ImagenDanadaError,
    LimiteAdjuntosError,
)
from backend.services.ticket_service import TicketClosedError

# Hijo del logger de correo_service: hereda su salida («CORREO: …») y su
# nivel INFO. Con ``__name__`` los INFO se perdían (Python solo muestra
# WARNING para arriba) y en Vercel no quedaba nada de los adjuntos.
logger = logging.getLogger("backend.services.correo_service.adjuntos")

MAX_ARCHIVOS_CORREO = 5
MAX_BYTES_CORREO = 10 * 1024 * 1024
MIN_BYTES_IMAGEN = 15 * 1024
# Graph cuenta en ``size`` el archivo y sus datos (nombre, tipo…): con este
# margen un archivo de casi 4 MB no se descarta antes de descargarlo. El
# tamaño real se vuelve a revisar con el contenido.
HOLGURA_GRAPH = 64 * 1024
# Tiempo extra, después de ``hasta``, para terminar de bajar los adjuntos
# del correo que ya se estaba procesando (Vercel corta a los 60 s).
MARGEN_DESCARGA_S = 15.0

TIPO_ARCHIVO = "#microsoft.graph.fileAttachment"
EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
                      ".heic", ".heif", ".svg", ".ico", ".emf", ".wmf")

# Extensión para una imagen en línea que vino sin ella («Pasted image»).
EXTENSION_POR_TIPO = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/pjpeg": ".jpg",
                      "image/png": ".png"}
POR_QUE_LOGO = "imagen en línea repetida (logo)"
POR_QUE_YA_ESTA = "la misma imagen ya está en el ticket"
# Una imagen en línea que ya llegó en otro correo del mismo remitente es el
# logo de su firma solo si es chica: una foto o una captura que se vuelve a
# mandar (otro ticket, una prueba) se guarda.
MAX_BYTES_LOGO = 100 * 1024

MOTIVO_TIPO = "tipo no permitido"
MOTIVO_GRANDE = "más de 4 MB"
MOTIVO_CANTIDAD = f"más de {MAX_ARCHIVOS_CORREO} por correo"
MOTIVO_TOTAL = "más de 10 MB en el correo"
MOTIVO_LLENO = f"el ticket ya tiene {adjuntos_service.MAX_POR_TICKET} adjuntos"
MOTIVO_TIEMPO = "no hubo tiempo de descargarlo"
MOTIVO_ALMACEN = "los adjuntos no están configurados en el servidor"
MOTIVO_ERROR = "no se pudo descargar"
MOTIVO_DANADA = "imagen dañada o incompleta"
MOTIVO_ENLACE = web.MOTIVO_ENLACE
ORDEN_MOTIVOS = (MOTIVO_TIPO, MOTIVO_DANADA, MOTIVO_GRANDE, MOTIVO_CANTIDAD, MOTIVO_TOTAL, MOTIVO_LLENO,
                 MOTIVO_TIEMPO, MOTIVO_ALMACEN, MOTIVO_ERROR, MOTIVO_ENLACE)


@dataclass
class Eleccion:
    """Qué hacer con cada adjunto de la lista de Graph."""

    elegidos: list[dict] = field(default_factory=list)
    omitidos: list[tuple[str, str]] = field(default_factory=list)  # (nombre, motivo)
    ignorados: list[tuple[str, str]] = field(default_factory=list)  # (nombre, por qué)


@dataclass
class Resultado:
    guardados: list[str] = field(default_factory=list)
    omitidos: list[tuple[str, str]] = field(default_factory=list)
    ignorados: list[tuple[str, str]] = field(default_factory=list)


def _es_imagen(nombre: str, tipo: str) -> bool:
    return tipo.startswith("image/") or os.path.splitext(nombre)[1].lower() in EXTENSIONES_IMAGEN


def _es_archivo(adjunto: dict) -> bool:
    """``fileAttachment``. Si Graph no mandara ``@odata.type``, un correo
    adjunto se reconoce igual por su tipo ``message/…``."""
    tipo_odata = adjunto.get("@odata.type")
    if tipo_odata:
        return tipo_odata == TIPO_ARCHIVO
    return not (adjunto.get("contentType") or "").lower().startswith("message/")


def _en_linea(adjunto: dict) -> bool:
    nombre = adjunto.get("name") or ""
    tipo = (adjunto.get("contentType") or "").lower()
    return bool(adjunto.get("isInline")) and _es_archivo(adjunto) and _es_imagen(nombre, tipo)


def _nombre(adjunto: dict, en_linea: bool) -> str:
    """Nombre limpio; a una imagen en línea sin extensión se le pone la de su tipo."""
    nombre = adjuntos_service.limpiar_nombre(adjunto.get("name")) or ("imagen" if en_linea else "adjunto")
    tipo = (adjunto.get("contentType") or "").lower()
    if en_linea and os.path.splitext(nombre)[1].lower() not in adjuntos_service.TIPOS:
        nombre += EXTENSION_POR_TIPO.get(tipo, "")
    return nombre


def _datos(adjunto: dict) -> str:
    """Lo que Graph dijo del adjunto (o el enlace de la imagen del cuerpo), para el log."""
    if "url" in adjunto:
        return f"url={adjunto['url']} tamaño={adjunto.get('size') if adjunto.get('size') is not None else '-'}"
    return (f"tamaño={adjunto.get('size')} isInline={bool(adjunto.get('isInline'))} "
            f"contentId={adjunto.get('contentId') or '-'} tipo={adjunto.get('contentType') or '-'}")


def _avisar(ticket_id, adjunto: dict, nombre: str, motivo: str, lista: list | None = None) -> None:
    """Anota el adjunto descartado (o que falló) en ``lista`` y en el log, con
    los datos para entender por qué (se ve en los registros de Vercel)."""
    if lista is not None:
        lista.append((nombre, motivo))
    logger.warning("Ticket #%s: adjunto del correo descartado «%s» (%s) motivo: %s",
                   ticket_id if ticket_id is not None else "?", nombre, _datos(adjunto), motivo)


def elegir(adjuntos: list[dict], libres: int, ticket_id: int | None = None) -> Eleccion:
    """Decide, solo con la lista de Graph, qué adjuntos se descargan.

    ``libres`` es cuántos adjuntos más admite el ticket. Se respetan el orden
    del correo, :data:`MAX_ARCHIVOS_CORREO` y :data:`MAX_BYTES_CORREO`. Las
    imágenes en línea elegidas llevan ``en_linea``: después de bajarlas se
    revisa si son un logo que ya llegó antes.
    """
    eleccion = Eleccion()
    total = 0
    # Imágenes en línea con el mismo tamaño y tipo: el logo de la firma
    # repetido (en las respuestas, una vez por cada correo citado).
    repetidas = Counter((int(a.get("size") or 0), (a.get("contentType") or "").lower())
                        for a in adjuntos if _en_linea(a))
    for adjunto in adjuntos:
        en_linea = _en_linea(adjunto)
        nombre = _nombre(adjunto, en_linea)
        tipo = (adjunto.get("contentType") or "").lower()
        tamano = int(adjunto.get("size") or 0)
        ext = os.path.splitext(nombre)[1].lower()
        if not _es_archivo(adjunto):
            por_que = ("enlace a OneDrive/SharePoint"
                       if "reference" in (adjunto.get("@odata.type") or "") else "otro correo")
            _avisar(ticket_id, adjunto, nombre, por_que, eleccion.ignorados)
        elif en_linea and tamano < MIN_BYTES_IMAGEN:
            _avisar(ticket_id, adjunto, nombre, "imagen en línea de menos de 15 KB (firma)",
                    eleccion.ignorados)
        elif en_linea and repetidas[(tamano, tipo)] > 1:
            _avisar(ticket_id, adjunto, nombre, POR_QUE_LOGO, eleccion.ignorados)
        elif en_linea and ext not in adjuntos_service.TIPOS:
            _avisar(ticket_id, adjunto, nombre, "imagen en línea de un tipo que no se guarda",
                    eleccion.ignorados)
        elif _es_imagen(nombre, tipo) and tamano < MIN_BYTES_IMAGEN:
            _avisar(ticket_id, adjunto, nombre, "imagen de menos de 15 KB", eleccion.ignorados)
        elif ext not in adjuntos_service.TIPOS:
            _avisar(ticket_id, adjunto, nombre, MOTIVO_TIPO, eleccion.omitidos)
        elif tamano > adjuntos_service.MAX_BYTES + HOLGURA_GRAPH:
            _avisar(ticket_id, adjunto, nombre, MOTIVO_GRANDE, eleccion.omitidos)
        elif len(eleccion.elegidos) >= libres:
            _avisar(ticket_id, adjunto, nombre, MOTIVO_LLENO, eleccion.omitidos)
        elif len(eleccion.elegidos) >= MAX_ARCHIVOS_CORREO:
            _avisar(ticket_id, adjunto, nombre, MOTIVO_CANTIDAD, eleccion.omitidos)
        elif total + tamano > MAX_BYTES_CORREO:
            _avisar(ticket_id, adjunto, nombre, MOTIVO_TOTAL, eleccion.omitidos)
        else:
            total += tamano
            eleccion.elegidos.append({**adjunto, "name": nombre, "en_linea": en_linea})
    return eleccion


def _repetida(session, ticket: Ticket, usuario: User | None, contenido: bytes) -> str | None:
    """Por qué no se guarda una imagen en línea ya vista, o ``None``.

    * La misma imagen ya está en el ticket (una respuesta que la vuelve a
      traer): no se duplica.
    * Es chica (menos de :data:`MAX_BYTES_LOGO`) y ya llegó en un correo
      anterior del mismo remitente: el logo de su firma."""
    huella = adjuntos_service.huella(contenido)
    if session.scalar(select(Attachment.id).where(Attachment.sha256 == huella,
                                                  Attachment.ticket_id == ticket.id).limit(1)):
        return POR_QUE_YA_ESTA
    if usuario is None or len(contenido) >= MAX_BYTES_LOGO:
        return None
    previa = session.scalar(
        select(Attachment.id)
        .where(Attachment.sha256 == huella, Attachment.source == adjuntos_service.ORIGEN_CORREO,
               Attachment.uploaded_by_id == usuario.id)
        .limit(1))
    return POR_QUE_LOGO if previa is not None else None


def _motivo_invalido(contenido: bytes, error: Exception | None = None) -> str:
    if len(contenido) > adjuntos_service.MAX_BYTES:
        return MOTIVO_GRANDE
    return MOTIVO_DANADA if isinstance(error, ImagenDanadaError) else MOTIVO_TIPO


def guardar(session_factory, cliente, mensaje_id: str, ticket_id: int, remitente: str,
            hasta: float | None = None) -> Resultado | None:
    """Guarda en ``ticket_id`` los adjuntos del correo ``mensaje_id`` de Graph.

    Devuelve ``None`` si no se guardó nada porque el ticket no existe o está
    Cerrado. Los errores de un adjunto puntual se anotan como omitidos; un
    error de Graph al pedir la lista sube a quien llama.
    """
    limite = None if hasta is None else hasta + MARGEN_DESCARGA_S
    with session_factory() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return None
        if ticket_service.is_closed(ticket):
            logger.info("Adjuntos del correo no guardados: el ticket #%s está Cerrado", ticket_id)
            return None
        usuario = session.scalar(select(User).where(func.lower(User.email) == remitente.lower()))
        libres = adjuntos_service.MAX_POR_TICKET - adjuntos_service.contar(session, ticket_id)

        lista = cliente.adjuntos(mensaje_id)
        logger.info("Ticket #%s: el correo trae %d adjunto(s): %s", ticket_id, len(lista),
                    "; ".join(f"«{a.get('name')}» ({_datos(a)})" for a in lista) or "ninguno")
        eleccion = elegir(lista, libres, ticket_id)
        resultado = Resultado(omitidos=list(eleccion.omitidos), ignorados=eleccion.ignorados)
        bytes_guardados, cerrado = 0, False
        for posicion, adjunto in enumerate(eleccion.elegidos):
            nombre = adjunto["name"]
            if limite is not None and time.monotonic() >= limite:
                for pendiente in eleccion.elegidos[posicion:]:
                    _avisar(ticket_id, pendiente, pendiente["name"], MOTIVO_TIEMPO,
                            resultado.omitidos)
                break
            try:
                contenido = cliente.descargar_adjunto(mensaje_id, adjunto["id"])
            except Exception as error:  # noqa: BLE001 — se avisa como omitido
                _avisar(ticket_id, adjunto, nombre, f"{MOTIVO_ERROR}: {error!r}", None)
                logger.warning("Detalle del error al descargar «%s»", nombre, exc_info=True)
                resultado.omitidos.append((nombre, MOTIVO_ERROR))
                continue
            por_que = adjunto.get("en_linea") and _repetida(session, ticket, usuario, contenido)
            if por_que:
                _avisar(ticket_id, adjunto, nombre,
                        f"{por_que}, ya llegó antes" if por_que == POR_QUE_LOGO else por_que)
                resultado.ignorados.append((nombre, por_que))
                continue
            estado = _subir(session, ticket, usuario, adjunto, nombre, contenido, resultado)
            if estado == "cerrado":
                cerrado = True
                break
            if estado == "ok":
                bytes_guardados += len(contenido)

        if not cerrado:
            _guardar_imagenes_web(session, cliente, mensaje_id, ticket, usuario, resultado,
                                  bytes_guardados, limite)

        if resultado.ignorados:
            logger.info("Ticket #%s: adjuntos del correo ignorados: %s", ticket_id,
                        "; ".join(f"{n} ({p})" for n, p in resultado.ignorados))
        if resultado.omitidos:
            logger.info("Ticket #%s: adjuntos del correo no guardados: %s", ticket_id,
                        "; ".join(f"{n} ({m})" for n, m in resultado.omitidos))
            adjuntos_service.registrar_omitidos(session, ticket, usuario, resultado.omitidos)
        if resultado.guardados:
            logger.info("Ticket #%s: %d adjunto(s) del correo guardado(s)", ticket_id,
                        len(resultado.guardados))
    return resultado


def _subir(session, ticket: Ticket, usuario: User | None, datos: dict, nombre: str,
           contenido: bytes, resultado: Resultado) -> str:
    """Guarda un archivo del correo. Devuelve ``ok``, ``omitido`` o
    ``cerrado`` (el ticket se cerró mientras tanto: no seguir)."""
    ticket_id = ticket.id
    try:
        adjuntos_service.subir(session, ticket, usuario, nombre, contenido,
                               origen=adjuntos_service.ORIGEN_CORREO)
    except AdjuntoInvalidoError as error:
        motivo = _motivo_invalido(contenido, error)
        _avisar(ticket_id, datos, nombre,
                f"{motivo} ({error}; {len(contenido)} bytes descargados)", None)
        resultado.omitidos.append((nombre, motivo))
    except LimiteAdjuntosError:
        _avisar(ticket_id, datos, nombre, MOTIVO_LLENO, resultado.omitidos)
    except AlmacenNoConfiguradoError:
        _avisar(ticket_id, datos, nombre,
                f"{MOTIVO_ALMACEN} (falta BLOB_READ_WRITE_TOKEN)", None)
        resultado.omitidos.append((nombre, MOTIVO_ALMACEN))
    except TicketClosedError:
        _avisar(ticket_id, datos, nombre, "el ticket se cerró mientras se guardaba")
        return "cerrado"
    except Exception as error:  # noqa: BLE001 — Blob caído, etc.: se avisa como omitido
        _avisar(ticket_id, datos, nombre, f"no se pudo guardar: {error!r}", None)
        logger.warning("Detalle del error al guardar «%s»", nombre, exc_info=True)
        session.rollback()
        resultado.omitidos.append((nombre, MOTIVO_ERROR))
    else:
        resultado.guardados.append(nombre)
        return "ok"
    return "omitido"


def _htmls(cliente, mensaje_id: str, ticket_id: int) -> list[str]:
    """El HTML de ``uniqueBody`` y ``body`` (el cliente sabe pedirlo)."""
    pedir = getattr(cliente, "cuerpo_html", None)
    if pedir is None:
        return []
    try:
        return pedir(mensaje_id)
    except Exception as error:  # noqa: BLE001 — sin el HTML, solo los adjuntos
        logger.warning("Ticket #%s: no se pudo leer el HTML del correo para buscar imágenes: %r",
                       ticket_id, error)
        return []


def _ya_en_el_ticket(session, ticket_id: int, contenido: bytes) -> bool:
    return session.scalar(select(Attachment.id).where(
        Attachment.sha256 == adjuntos_service.huella(contenido),
        Attachment.ticket_id == ticket_id).limit(1)) is not None


def _guardar_imagenes_web(session, cliente, mensaje_id: str, ticket: Ticket, usuario: User | None,
                          resultado: Resultado, bytes_guardados: int, limite: float | None) -> None:
    """Las imágenes del cuerpo HTML que no son adjuntos (``https://`` o
    ``data:``), con lo que queda de los límites del correo y del ticket."""
    ticket_id = ticket.id
    imagenes = web.extraer(_htmls(cliente, mensaje_id, ticket_id))
    if not imagenes:
        return
    logger.info("Ticket #%s: el cuerpo del correo trae %d imagen(es) sin adjunto: %s", ticket_id,
                len(imagenes), "; ".join(web.recortar(i.src) for i in imagenes))
    sin_nombre = 0
    for posicion, imagen in enumerate(imagenes):
        datos = {"url": web.recortar(imagen.src), "size": None}
        # Para el log y los avisos antes de saber qué imagen es.
        provisorio = web.nombre_del_enlace(imagen.src, "") or "imagen_web"
        if posicion >= web.MAX_IMAGENES:
            _avisar(ticket_id, datos, provisorio,
                    f"más de {web.MAX_IMAGENES} imágenes en el cuerpo", resultado.ignorados)
            continue
        if imagen.parece_pixel():
            _avisar(ticket_id, datos, provisorio, "píxel de rastreo u oculta (1 px)",
                    resultado.ignorados)
            continue
        if len(resultado.guardados) >= MAX_ARCHIVOS_CORREO:
            _avisar(ticket_id, datos, provisorio, MOTIVO_CANTIDAD, resultado.omitidos)
            continue
        if adjuntos_service.contar(session, ticket_id) >= adjuntos_service.MAX_POR_TICKET:
            _avisar(ticket_id, datos, provisorio, MOTIVO_LLENO, resultado.omitidos)
            continue
        ahora = time.monotonic()
        if limite is not None and ahora >= limite:
            _avisar(ticket_id, datos, provisorio, MOTIVO_TIEMPO, resultado.omitidos)
            continue
        hasta = ahora + web.TIMEOUT_S if limite is None else min(ahora + web.TIMEOUT_S, limite)
        bajada = b""
        try:
            if imagen.es_data:
                bajada = web.decodificar_data(imagen.src)
            elif imagen.src[:8].lower() == "https://":
                bajada = descargar_imagen(imagen.src, hasta)
            else:
                esquema = imagen.src.split(":", 1)[0][:20] if ":" in imagen.src else "relativo"
                raise web.ImagenWebError(MOTIVO_ENLACE, f"esquema «{esquema}» (solo https o data:)")
            datos["size"] = len(bajada)
            img = web.preparar(bajada)
        except web.ImagenWebError as error:
            _avisar(ticket_id, datos, provisorio, f"{error.motivo} ({error.detalle})", None)
            resultado.omitidos.append((provisorio, error.motivo))
            continue
        except Exception as error:  # noqa: BLE001 — cualquier otra falla: se avisa y se sigue
            _avisar(ticket_id, datos, provisorio, f"{MOTIVO_ERROR}: {error!r}", None)
            logger.warning("Detalle del error con la imagen %s", datos["url"], exc_info=True)
            resultado.omitidos.append((provisorio, MOTIVO_ERROR))
            continue

        del_enlace = web.nombre_del_enlace(imagen.src, img.ext)
        nombre = del_enlace or f"imagen_web{img.ext}"
        if img.convertida:
            logger.info("Ticket #%s: imagen %s convertida de %s a PNG", ticket_id, datos["url"],
                        img.convertida)
        # Sin el mínimo de 15 KB de los adjuntos: ver web.por_que_chica.
        chica = web.por_que_chica(len(bajada), img)
        if chica:
            _avisar(ticket_id, datos, nombre, chica, resultado.ignorados)
            continue
        if _ya_en_el_ticket(session, ticket_id, img.contenido):
            _avisar(ticket_id, datos, nombre, POR_QUE_YA_ESTA, resultado.ignorados)
            continue
        if bytes_guardados + len(img.contenido) > MAX_BYTES_CORREO:
            _avisar(ticket_id, datos, nombre, MOTIVO_TOTAL, resultado.omitidos)
            continue
        if del_enlace is None:  # se numeran solo las que se guardan
            sin_nombre += 1
            nombre = f"imagen_web_{sin_nombre}{img.ext}"
        estado = _subir(session, ticket, usuario, datos, nombre, img.contenido, resultado)
        if estado == "cerrado":
            return
        if estado == "ok":
            bytes_guardados += len(img.contenido)


def descargar_imagen(src: str, hasta: float) -> bytes:
    """Baja una imagen ``https://`` (las pruebas la reemplazan)."""
    return web.descargar(src, hasta)


def _lista_o(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else f"{', '.join(partes[:-1])} o {partes[-1]}"


def nota_omitidos(omitidos: list[tuple[str, str]], enlace: str) -> str:
    """El párrafo de la respuesta automática cuando hubo omitidos."""
    cantidad = len(omitidos)
    motivos = [m for m in ORDEN_MOTIVOS if any(motivo == m for _, motivo in omitidos)]
    if set(motivos) <= {MOTIVO_TIPO, MOTIVO_GRANDE}:
        porque = f"{MOTIVO_TIPO} o {MOTIVO_GRANDE}"
    else:
        porque = _lista_o(motivos)
    cuantos = "No se guardó 1 adjunto" if cantidad == 1 else f"No se guardaron {cantidad} adjuntos"
    return f"{cuantos} ({porque}). Puede subirlos desde la ticketera: {enlace}"


FIRMA = "\n\nMesa de ayuda"


def agregar_nota(respuesta, omitidos: list[tuple[str, str]], enlace: str):
    """La respuesta con la nota de los omitidos antes de la firma."""
    if not omitidos:
        return respuesta
    nota = nota_omitidos(omitidos, enlace)
    cuerpo, firma, resto = respuesta.texto.rpartition(FIRMA)
    texto = f"{cuerpo}\n\n{nota}{firma}{resto}" if firma else f"{respuesta.texto}\n\n{nota}"
    return replace(respuesta, texto=texto)
