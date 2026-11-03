#!/usr/bin/env python3
"""Manda un correo de prueba a Mailpit por SMTP (solo local, nada sale a Internet).

Sirve para probar los correos entrantes con ``CORREO_PROVEEDOR=mailpit``: la
ticketera lee lo que llega a Mailpit como si fuera el buzón de Microsoft 365.
Solo usa la biblioteca estándar de Python.

Ejemplos::

    python scripts/enviar_correo_prueba.py --de dsaenz@data.cr --para kcastro@data.cr \\
        --asunto "Daño Nokia" --texto "Se me cayó" --imagen-en-linea foto.jpg

    # Respuesta en el hilo del último correo que la ticketera le mandó a dsaenz
    python scripts/enviar_correo_prueba.py --de dsaenz@data.cr --para kcastro@data.cr \\
        --responder --texto "Así quedó" --imagen-en-linea foto2.jpg

La imagen en línea va como la pega Outlook: parte HTML con
``<img src="cid:…">``, la imagen en ``multipart/related`` con
``Content-Disposition: inline`` y ``Content-ID``, y ``[cid:…]`` en la parte
de texto. El adjunto va como ``attachment``.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import smtplib
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path


def _tipo(ruta: Path) -> tuple[str, str]:
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    principal, _, secundario = tipo.partition("/")
    return principal, secundario


def _ultimo_de_la_app(api: str, para: str, de: str) -> dict:
    """El último correo que el buzón ``de`` le mandó a ``para`` (la respuesta
    de la ticketera), para contestar en su hilo."""
    consulta = urllib.parse.quote(f'from:"{de}" to:"{para}"')
    with urllib.request.urlopen(f"{api}/api/v1/search?query={consulta}&limit=1", timeout=10) as r:
        mensajes = json.load(r).get("messages") or []
    if not mensajes:
        sys.exit(f"No hay en Mailpit ningún correo de {de} para {para} al que responder.")
    with urllib.request.urlopen(f"{api}/api/v1/message/{mensajes[0]['ID']}", timeout=10) as r:
        mensaje = json.load(r)
    with urllib.request.urlopen(f"{api}/api/v1/message/{mensajes[0]['ID']}/headers", timeout=10) as r:
        cabeceras = {k.lower(): v for k, v in json.load(r).items()}
    referencias = " ".join(cabeceras.get("references") or [])
    return {"message_id": f"<{mensaje['MessageID']}>", "asunto": mensaje.get("Subject") or "",
            "referencias": referencias}


def armar(args) -> EmailMessage:
    correo = EmailMessage()
    correo["From"] = args.de
    correo["To"] = ", ".join(args.para)
    if args.cc:
        correo["Cc"] = ", ".join(args.cc)
    asunto = args.asunto
    anterior = None
    if args.responder:
        anterior = _ultimo_de_la_app(args.api, args.de, args.para[0])
    elif args.en_respuesta_a:
        anterior = {"message_id": args.en_respuesta_a, "asunto": "", "referencias": ""}
    if anterior is not None:
        asunto = asunto or f"RE: {anterior['asunto']}"
        correo["In-Reply-To"] = anterior["message_id"]
        correo["References"] = " ".join(p for p in (anterior["referencias"], anterior["message_id"]) if p)
    correo["Subject"] = asunto or "(sin asunto)"
    correo["Date"] = formatdate(localtime=True)
    correo["Message-ID"] = make_msgid(domain=args.de.rsplit("@", 1)[-1])

    imagenes = []
    for indice, nombre in enumerate(args.imagen_en_linea, start=1):
        ruta = Path(nombre)
        cid = make_msgid(idstring=f"image{indice:03d}", domain="prueba.local")[1:-1]
        imagenes.append((ruta, cid))

    # Texto: como Outlook, una marca [cid:…] donde va cada imagen pegada.
    texto = args.texto
    if imagenes:
        texto += "\n\n" + "\n".join(f"[cid:{cid}]" for _, cid in imagenes)
    correo.set_content(texto + "\n")

    if imagenes:
        cuerpo_html = "<html><body><p>{}</p>{}</body></html>".format(
            html.escape(args.texto).replace("\n", "<br>"),
            "".join(f'<p><img src="cid:{cid}" alt="{html.escape(r.name)}"></p>' for r, cid in imagenes))
        correo.add_alternative(cuerpo_html, subtype="html")
        parte_html = correo.get_payload()[1]
        for ruta, cid in imagenes:
            principal, secundario = _tipo(ruta)
            parte_html.add_related(ruta.read_bytes(), principal, secundario, cid=f"<{cid}>",
                                   disposition="inline", filename=ruta.name)

    for nombre in args.adjunto:
        ruta = Path(nombre)
        principal, secundario = _tipo(ruta)
        correo.add_attachment(ruta.read_bytes(), maintype=principal, subtype=secundario,
                              filename=ruta.name)
    return correo


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Manda un correo de prueba a Mailpit por SMTP.")
    parser.add_argument("--de", required=True, help="remitente, por ejemplo dsaenz@data.cr")
    parser.add_argument("--para", required=True, action="append",
                        help="destinatario (el buzón de soporte, CORREO_USUARIO); se puede repetir")
    parser.add_argument("--cc", action="append", default=[], help="copia; se puede repetir")
    parser.add_argument("--asunto", default="", help="asunto (con --responder, «RE: …» del anterior)")
    parser.add_argument("--texto", default="", help="texto del correo")
    parser.add_argument("--adjunto", action="append", default=[], metavar="ARCHIVO",
                        help="archivo adjunto; se puede repetir")
    parser.add_argument("--imagen-en-linea", action="append", default=[], metavar="IMAGEN",
                        help="imagen pegada en el texto (en línea, con cid); se puede repetir")
    parser.add_argument("--responder", action="store_true",
                        help="responder en el hilo del último correo que --para le mandó a --de")
    parser.add_argument("--en-respuesta-a", default="", metavar="MESSAGE_ID",
                        help="responder al correo con este Message-ID (<…>), sin buscarlo en Mailpit")
    parser.add_argument("--servidor", default="localhost", help="servidor SMTP (por defecto localhost)")
    parser.add_argument("--puerto", type=int, default=1025, help="puerto SMTP (por defecto 1025)")
    parser.add_argument("--api", default="http://localhost:8025",
                        help="dirección de Mailpit para --responder (por defecto http://localhost:8025)")
    args = parser.parse_args(argv)

    for archivo in [*args.adjunto, *args.imagen_en_linea]:
        if not Path(archivo).is_file():
            parser.error(f"no existe el archivo {archivo}")

    correo = armar(args)
    with smtplib.SMTP(args.servidor, args.puerto, timeout=10) as smtp:
        smtp.send_message(correo)
    print(f"Enviado a Mailpit: «{correo['Subject']}» de {args.de} para {', '.join(args.para)} "
          f"({len(args.imagen_en_linea)} imagen(es) en línea, {len(args.adjunto)} adjunto(s)). "
          f"Míralo en {args.api}")


if __name__ == "__main__":
    main()
