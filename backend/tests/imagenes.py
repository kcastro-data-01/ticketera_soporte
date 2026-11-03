"""Imágenes **reales** (se pueden abrir) para las pruebas de adjuntos.

La validación revisa la estructura de JPEG y PNG (no solo los primeros
bytes), así que las pruebas no pueden usar una cabecera con relleno.

* :func:`jpeg`: un JPEG de 16×16 (hecho con Pillow) con bloques de
  comentario (COM) para llegar al tamaño pedido; sigue siendo válido.
* :func:`png`: un PNG armado con zlib, con un bloque auxiliar privado
  (``rlNo``, que los visores ignoran) para llegar al tamaño pedido.

``relleno`` cambia el contenido (y la huella SHA-256) sin cambiar el tamaño.
"""

import base64
import struct
import zlib

JPEG_16 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcU"
    "FhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgo"
    "KCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAQABADASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDgKKKK"
    "+eP2E//Z"
)


def jpeg(kb: float = 1, relleno: bytes = b"\x00") -> bytes:
    """Un JPEG válido de unos ``kb`` KB."""
    faltan = max(0, int(kb * 1024) - len(JPEG_16))
    comentarios = b""
    while faltan > 4:
        n = min(65533, faltan - 4)
        comentarios += b"\xff\xfe" + struct.pack(">H", n + 2) + (relleno * n)[:n]
        faltan -= n + 4
    return JPEG_16[:2] + comentarios + JPEG_16[2:]


def _bloque(tipo: bytes, datos: bytes) -> bytes:
    return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))


def png(kb: float = 1, relleno: bytes = b"\x00", lado: int = 8) -> bytes:
    """Un PNG válido (``lado``×``lado``, RGB) de unos ``kb`` KB."""
    filas = b"".join(
        b"\x00" + b"".join(bytes(((x * 31) % 256, (y * 31) % 256, 120)) for x in range(lado))
        for y in range(lado))
    base = (b"\x89PNG\r\n\x1a\n"
            + _bloque(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
            + _bloque(b"IDAT", zlib.compress(filas)))
    fin = _bloque(b"IEND", b"")
    faltan = int(kb * 1024) - len(base) - len(fin) - 12
    extra = _bloque(b"rlNo", (relleno * faltan)[:faltan]) if faltan > 0 else b""
    return base + extra + fin
