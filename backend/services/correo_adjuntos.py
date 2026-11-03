"""Adjuntos de los correos que crean un ticket o agregan un comentario.

Se guardan con el mismo almacén y las mismas validaciones que los que se
suben en la ticketera (:mod:`backend.services.adjuntos_service`), marcados
como ``correo``.

1. Primero se pide a Graph **la lista** de adjuntos (nombre, tipo y tamaño,
   sin el contenido) y se decide cuáles entran.
2. Después se descargan **solo los elegidos**, uno por uno: así una revisión
   del buzón no se pasa del tiempo de la función de Vercel.

Se ignoran sin avisar (no son archivos que la persona quiso mandar):

* las imágenes en línea (logos y fotos de la firma);
* las imágenes de menos de :data:`MIN_BYTES_IMAGEN`;
* los adjuntos que son otro correo (``itemAttachment``) o un enlace a
  OneDrive o SharePoint (``referenceAttachment``).

Se **omiten** (y se avisa en la respuesta automática, el historial y el log):
tipo no permitido, más de 4 MB, más de :data:`MAX_ARCHIVOS_CORREO` archivos o
de :data:`MAX_BYTES_CORREO` en el correo, o el ticket ya tiene 10 adjuntos.
En un ticket Cerrado no se guarda nada.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, replace

from sqlalchemy import func, select

from backend.models import Ticket, User
from backend.services import adjuntos_service, ticket_service
from backend.services.adjuntos_service import (
    AdjuntoInvalidoError,
    AlmacenNoConfiguradoError,
    LimiteAdjuntosError,
)
from backend.services.ticket_service import TicketClosedError

logger = logging.getLogger(__name__)

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

MOTIVO_TIPO = "tipo no permitido"
MOTIVO_GRANDE = "más de 4 MB"
MOTIVO_CANTIDAD = f"más de {MAX_ARCHIVOS_CORREO} por correo"
MOTIVO_TOTAL = "más de 10 MB en el correo"
MOTIVO_LLENO = f"el ticket ya tiene {adjuntos_service.MAX_POR_TICKET} adjuntos"
MOTIVO_TIEMPO = "no hubo tiempo de descargarlo"
MOTIVO_ALMACEN = "los adjuntos no están configurados en el servidor"
MOTIVO_ERROR = "no se pudo descargar"
ORDEN_MOTIVOS = (MOTIVO_TIPO, MOTIVO_GRANDE, MOTIVO_CANTIDAD, MOTIVO_TOTAL, MOTIVO_LLENO,
                 MOTIVO_TIEMPO, MOTIVO_ALMACEN, MOTIVO_ERROR)


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


def elegir(adjuntos: list[dict], libres: int) -> Eleccion:
    """Decide, solo con la lista de Graph, qué adjuntos se descargan.

    ``libres`` es cuántos adjuntos más admite el ticket. Se respetan el orden
    del correo, :data:`MAX_ARCHIVOS_CORREO` y :data:`MAX_BYTES_CORREO`.
    """
    eleccion = Eleccion()
    total = 0
    for adjunto in adjuntos:
        nombre = adjuntos_service.limpiar_nombre(adjunto.get("name")) or "adjunto"
        tipo = (adjunto.get("contentType") or "").lower()
        tamano = int(adjunto.get("size") or 0)
        ext = os.path.splitext(nombre)[1].lower()
        if not _es_archivo(adjunto):
            por_que = ("enlace a OneDrive/SharePoint"
                       if "reference" in (adjunto.get("@odata.type") or "") else "otro correo")
            eleccion.ignorados.append((nombre, por_que))
        elif _es_imagen(nombre, tipo) and adjunto.get("isInline"):
            eleccion.ignorados.append((nombre, "imagen en línea (firma)"))
        elif _es_imagen(nombre, tipo) and tamano < MIN_BYTES_IMAGEN:
            eleccion.ignorados.append((nombre, "imagen de menos de 15 KB"))
        elif ext not in adjuntos_service.TIPOS:
            eleccion.omitidos.append((nombre, MOTIVO_TIPO))
        elif tamano > adjuntos_service.MAX_BYTES + HOLGURA_GRAPH:
            eleccion.omitidos.append((nombre, MOTIVO_GRANDE))
        elif len(eleccion.elegidos) >= libres:
            eleccion.omitidos.append((nombre, MOTIVO_LLENO))
        elif len(eleccion.elegidos) >= MAX_ARCHIVOS_CORREO:
            eleccion.omitidos.append((nombre, MOTIVO_CANTIDAD))
        elif total + tamano > MAX_BYTES_CORREO:
            eleccion.omitidos.append((nombre, MOTIVO_TOTAL))
        else:
            total += tamano
            eleccion.elegidos.append({**adjunto, "name": nombre})
    return eleccion


def _motivo_invalido(contenido: bytes) -> str:
    return MOTIVO_GRANDE if len(contenido) > adjuntos_service.MAX_BYTES else MOTIVO_TIPO


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

        eleccion = elegir(cliente.adjuntos(mensaje_id), libres)
        resultado = Resultado(omitidos=list(eleccion.omitidos), ignorados=eleccion.ignorados)
        for posicion, adjunto in enumerate(eleccion.elegidos):
            nombre = adjunto["name"]
            if limite is not None and time.monotonic() >= limite:
                resultado.omitidos += [(a["name"], MOTIVO_TIEMPO)
                                       for a in eleccion.elegidos[posicion:]]
                break
            try:
                contenido = cliente.descargar_adjunto(mensaje_id, adjunto["id"])
            except Exception:  # noqa: BLE001 — se avisa como omitido
                logger.exception("No se pudo descargar el adjunto «%s» del correo", nombre)
                resultado.omitidos.append((nombre, MOTIVO_ERROR))
                continue
            try:
                adjuntos_service.subir(session, ticket, usuario, nombre, contenido,
                                       origen=adjuntos_service.ORIGEN_CORREO)
            except AdjuntoInvalidoError:
                resultado.omitidos.append((nombre, _motivo_invalido(contenido)))
            except LimiteAdjuntosError:
                resultado.omitidos.append((nombre, MOTIVO_LLENO))
            except AlmacenNoConfiguradoError:
                logger.error("Adjunto «%s» del correo no guardado: falta BLOB_READ_WRITE_TOKEN",
                             nombre)
                resultado.omitidos.append((nombre, MOTIVO_ALMACEN))
            except TicketClosedError:
                break
            else:
                resultado.guardados.append(nombre)

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
