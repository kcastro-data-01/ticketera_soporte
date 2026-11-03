"""Adjuntos de un ticket: validación, almacén y reglas.

* Tipos: jpg, png, pdf, docx, xlsx y txt. Se mira el **contenido** (la firma
  del archivo, o la estructura en docx y xlsx), no solo la extensión ni el
  tipo que manda el navegador; la extensión tiene que coincidir con lo que es.
* Límites: :data:`MAX_BYTES` por archivo y :data:`MAX_POR_TICKET` por ticket.
* Permisos: los mismos que ver el ticket; borrar, quien lo subió o el
  Administrador. En un ticket Cerrado no se sube ni se borra (``409``).
* Almacén: Vercel Blob privado si existe ``BLOB_READ_WRITE_TOKEN``; si no, una
  carpeta local (``ADJUNTOS_DIR``, por defecto ``/data/adjuntos`` en Docker).
  Nunca hay enlaces públicos: todo se descarga por la API con sesión.
"""

import io
import logging
import os
import re
import unicodedata
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import func, select

from backend.constants import UserRole
from backend.entorno import en_vercel
from backend.models import Attachment, History, Ticket, User
from backend.services.ticket_service import _audit_author, _ensure_open

logger = logging.getLogger(__name__)

MAX_BYTES = 4 * 1024 * 1024
MAX_POR_TICKET = 10
NOMBRE_MAX = 255

TIPOS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
}
EXTENSIONES_TEXTO = "jpg, png, pdf, docx, xlsx o txt"

ACCION_SUBIDO = "attachment_added"
ACCION_BORRADO = "attachment_deleted"


class AdjuntoInvalidoError(Exception):
    """El archivo no se acepta (tipo, contenido, tamaño o vacío): ``422``."""


class LimiteAdjuntosError(Exception):
    """El ticket ya tiene :data:`MAX_POR_TICKET` adjuntos: ``409``."""


class AdjuntoSinPermisoError(Exception):
    """Solo quien lo subió o el Administrador lo borran: ``403``."""


class AlmacenNoConfiguradoError(Exception):
    """En Vercel sin ``BLOB_READ_WRITE_TOKEN`` no hay dónde guardar: ``503``."""


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------


def limpiar_nombre(nombre: str | None) -> str:
    """Nombre para mostrar: sin carpetas ni caracteres de control, con
    espacios simples y como máximo :data:`NOMBRE_MAX` caracteres (se recorta
    la parte de antes de la extensión)."""
    base = re.split(r"[\\/]", nombre or "")[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    base = re.sub(r"\s+", " ", base).strip().strip(".")
    if not base:
        return ""
    if len(base) > NOMBRE_MAX:
        raiz, ext = os.path.splitext(base)
        base = raiz[: NOMBRE_MAX - len(ext)] + ext
    return base


def _es_ooxml(contenido: bytes, parte: str) -> bool:
    """Un docx o xlsx es un zip con ``[Content_Types].xml`` y su parte
    principal; sin macros (``vbaProject.bin``). Solo lee el índice del zip."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            nombres = set(archivo.namelist())
    except (zipfile.BadZipFile, ValueError, OSError):
        return False
    if any(n.lower().endswith("vbaproject.bin") for n in nombres):
        return False
    return "[Content_Types].xml" in nombres and parte in nombres


_FIRMAS_BINARIAS = (b"%PDF", b"\x89PNG", b"\xff\xd8\xff", b"PK\x03\x04", b"MZ", b"\x7fELF")


def _es_texto(contenido: bytes) -> bool:
    """Texto plano en UTF-8 (o Windows-1252, el de los Bloc de notas viejos),
    sin bytes nulos ni caracteres de control salvo saltos y tabulaciones."""
    if b"\x00" in contenido or contenido.startswith(_FIRMAS_BINARIAS):
        return False
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            texto = contenido.decode("cp1252")
        except UnicodeDecodeError:
            return False
    return all(c in "\t\n\r\f" or unicodedata.category(c) != "Cc" for c in texto)


def _contenido_coincide(ext: str, contenido: bytes) -> bool:
    if ext in (".jpg", ".jpeg"):
        return contenido.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return contenido.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".pdf":
        return contenido.startswith(b"%PDF-")
    if ext == ".docx":
        return _es_ooxml(contenido, "word/document.xml")
    if ext == ".xlsx":
        return _es_ooxml(contenido, "xl/workbook.xml")
    if ext == ".txt":
        return _es_texto(contenido)
    return False


def validar(nombre: str | None, contenido: bytes) -> tuple[str, str]:
    """Devuelve ``(nombre limpio, tipo MIME)`` o lanza
    :class:`AdjuntoInvalidoError` con el motivo para mostrar."""
    limpio = limpiar_nombre(nombre)
    if not limpio:
        raise AdjuntoInvalidoError("Falta el nombre del archivo.")
    ext = os.path.splitext(limpio)[1].lower()
    if ext not in TIPOS:
        raise AdjuntoInvalidoError(
            f"«{limpio}»: tipo de archivo no permitido. Se aceptan {EXTENSIONES_TEXTO}.")
    if not contenido:
        raise AdjuntoInvalidoError(f"«{limpio}» está vacío.")
    if len(contenido) > MAX_BYTES:
        raise AdjuntoInvalidoError(f"«{limpio}» pesa más de 4 MB.")
    if not _contenido_coincide(ext, contenido):
        raise AdjuntoInvalidoError(
            f"«{limpio}»: el contenido no corresponde a un archivo {ext[1:].upper()} válido.")
    return limpio, TIPOS[ext]


# ---------------------------------------------------------------------------
# Almacén
# ---------------------------------------------------------------------------


def carpeta_local() -> Path:
    configurada = (os.environ.get("ADJUNTOS_DIR") or "").strip()
    if configurada:
        return Path(configurada)
    if Path("/data").is_dir():
        return Path("/data/adjuntos")
    return Path(__file__).resolve().parent.parent.parent / "adjuntos"


class AlmacenLocal:
    nombre = "local"

    def _ruta(self, clave: str) -> Path:
        raiz = carpeta_local().resolve()
        ruta = (raiz / clave).resolve()
        if raiz not in ruta.parents:
            raise ValueError("Ruta de adjunto fuera de la carpeta")
        return ruta

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(ruta.suffix + ".tmp")
        temporal.write_bytes(contenido)
        temporal.replace(ruta)
        return clave

    def leer(self, ref: str) -> bytes:
        return self._ruta(ref).read_bytes()

    def borrar(self, ref: str) -> None:
        self._ruta(ref).unlink(missing_ok=True)


class AlmacenBlob:
    """Vercel Blob en un store **privado** (``vercel-blob`` >= 0.5). Las
    credenciales las toma el SDK de ``BLOB_READ_WRITE_TOKEN``."""

    nombre = "blob"

    def _sdk(self):
        from vercel.blob import sync as blob

        return blob

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        resultado = self._sdk().put_blob(
            f"adjuntos/{clave}", contenido, access="private", content_type=content_type)
        return resultado.url

    def leer(self, ref: str) -> bytes:
        return self._sdk().get_blob(ref, access="private").body

    def borrar(self, ref: str) -> None:
        self._sdk().delete_blob(ref)


def almacen_actual():
    """Donde se guardan los adjuntos nuevos."""
    if (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip():
        return AlmacenBlob()
    if en_vercel():
        # En Vercel el disco no dura entre llamadas: sin Blob no se guarda.
        raise AlmacenNoConfiguradoError(
            "Los adjuntos no están configurados en este servidor.")
    return AlmacenLocal()


def almacen_de(adjunto: Attachment):
    """El almacén donde quedó guardado ``adjunto``."""
    return AlmacenBlob() if adjunto.storage == AlmacenBlob.nombre else AlmacenLocal()


# ---------------------------------------------------------------------------
# Reglas y operaciones
# ---------------------------------------------------------------------------


def listar(session, ticket_id: int) -> list[Attachment]:
    return list(session.scalars(
        select(Attachment).where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at, Attachment.id)
    ))


def contar(session, ticket_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(Attachment).where(Attachment.ticket_id == ticket_id))


def obtener(session, ticket_id: int, adjunto_id: int) -> Attachment | None:
    adjunto = session.get(Attachment, adjunto_id)
    if adjunto is None or adjunto.ticket_id != ticket_id:
        return None
    return adjunto


def puede_eliminar(adjunto: Attachment, ticket: Ticket, user: User) -> bool:
    if ticket.state == "Cerrado":
        return False
    return user.role == UserRole.ADMIN.value or adjunto.uploaded_by_id == user.id


def subir(session, ticket: Ticket, user: User, nombre: str | None, contenido: bytes) -> Attachment:
    """Valida, guarda el archivo y registra la fila y el historial.

    Raises: ``TicketClosedError``, :class:`LimiteAdjuntosError`,
    :class:`AdjuntoInvalidoError`, :class:`AlmacenNoConfiguradoError`.
    """
    _ensure_open(ticket)
    if contar(session, ticket.id) >= MAX_POR_TICKET:
        raise LimiteAdjuntosError(
            f"El ticket ya tiene {MAX_POR_TICKET} adjuntos, el máximo permitido.")
    limpio, content_type = validar(nombre, contenido)
    almacen = almacen_actual()
    ext = os.path.splitext(limpio)[1].lower().replace(".jpeg", ".jpg")
    clave = f"tickets/{ticket.id}/{uuid.uuid4().hex}{ext}"
    ref = almacen.guardar(clave, contenido, content_type)

    autor, autor_id = _audit_author(user)
    adjunto = Attachment(
        ticket_id=ticket.id, filename=limpio, content_type=content_type,
        size=len(contenido), storage=almacen.nombre, storage_key=ref,
        uploaded_by=autor, uploaded_by_id=autor_id,
    )
    session.add(adjunto)
    session.add(History(
        ticket_id=ticket.id, action=ACCION_SUBIDO, field="adjunto",
        old_value=None, new_value=limpio, author=autor, author_id=autor_id,
    ))
    try:
        session.commit()
    except Exception:
        session.rollback()
        _borrar_archivo(almacen, ref)
        raise
    session.refresh(adjunto)
    return adjunto


def eliminar(session, ticket: Ticket, adjunto: Attachment, user: User) -> None:
    """Borra la fila (con su entrada de historial) y luego el archivo.

    Raises: ``TicketClosedError``, :class:`AdjuntoSinPermisoError`.
    """
    _ensure_open(ticket)
    if not puede_eliminar(adjunto, ticket, user):
        raise AdjuntoSinPermisoError(
            "Solo quien subió el archivo o un Administrador pueden eliminarlo.")
    almacen, ref, nombre = almacen_de(adjunto), adjunto.storage_key, adjunto.filename
    autor, autor_id = _audit_author(user)
    session.delete(adjunto)
    session.add(History(
        ticket_id=ticket.id, action=ACCION_BORRADO, field="adjunto",
        old_value=nombre, new_value=None, author=autor, author_id=autor_id,
    ))
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    _borrar_archivo(almacen, ref)


def leer(adjunto: Attachment) -> bytes:
    return almacen_de(adjunto).leer(adjunto.storage_key)


def _borrar_archivo(almacen, ref: str) -> None:
    """Borrar el archivo nunca hace fallar la acción: si no se puede, queda
    en el log (la fila ya no existe, nadie lo ve)."""
    try:
        almacen.borrar(ref)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo borrar el archivo adjunto %s", ref)


def borrar_archivos(adjuntos: list[tuple[str, str]]) -> None:
    """Borra del almacén ``(storage, storage_key)`` ya sacados de la base
    (al eliminar un ticket)."""
    for storage, ref in adjuntos:
        almacen = AlmacenBlob() if storage == AlmacenBlob.nombre else AlmacenLocal()
        _borrar_archivo(almacen, ref)
