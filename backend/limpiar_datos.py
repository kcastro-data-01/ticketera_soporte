"""Deja la base limpia antes de usar la ticketera en la empresa: borra los
datos de prueba y conserva solo al administrador de ``ADMIN_INICIAL``.

Uso (dentro del contenedor o en local):

    python -m backend.limpiar_datos

Pasos:

1. Copia la base a ``/data/respaldo-antes-de-limpiar-<fecha-hora>.db`` (fuera
   de Docker, si no existe ``/data``, junto a la base) y dice dónde quedó.
2. Pide escribir ``BORRAR``; con cualquier otra respuesta no borra nada.
3. Borra tickets, comentarios, historial, explicaciones de IA y todos los
   usuarios excepto ``ADMIN_INICIAL``. Si ese usuario no existe, avisa y no
   borra nada.

El registro de correos procesados (``processed_emails``) se conserva con
``ticket_id`` en ``NULL``, para que los correos viejos no vuelvan a crear
tickets. La caché de la sesión de Microsoft (``msal_cache.json``) no se toca.
"""

import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.database import engine as engine_app
from backend.database import init_db
from backend.models import Comment, History, ProcessedEmail, Ticket, TicketExplanation, User
from backend.services.login_microsoft import admin_inicial

PALABRA_CONFIRMACION = "BORRAR"
CARPETA_DATOS = Path("/data")


def ruta_de_la_base(db_engine) -> Path:
    """El archivo SQLite de ``db_engine``; otra base no se puede respaldar aquí."""
    url = db_engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise SystemExit(
            f"La base no es un archivo SQLite ({url.render_as_string(hide_password=True)}): "
            "respáldala con la herramienta de esa base y bórrala a mano. No se borró nada."
        )
    return Path(url.database).resolve()


def respaldar(ruta_base: Path, carpeta: Path | None = None) -> Path:
    """Copia la base con la API de respaldo de SQLite (sirve con la app
    encendida) y devuelve la ruta del respaldo."""
    if carpeta is None:
        carpeta = CARPETA_DATOS if CARPETA_DATOS.is_dir() else ruta_base.parent
    fecha = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = carpeta / f"respaldo-antes-de-limpiar-{fecha}.db"
    with closing(sqlite3.connect(ruta_base)) as origen, closing(sqlite3.connect(destino)) as copia:
        origen.backup(copia)
    return destino


def contar(session: Session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


def limpiar(session: Session, admin: User) -> dict[str, int]:
    """Borra los datos de prueba y devuelve cuántos se borraron."""
    borrados = {
        "tickets": contar(session, Ticket),
        "comentarios": contar(session, Comment),
        "historial": contar(session, History),
        "explicaciones": contar(session, TicketExplanation),
        "usuarios": contar(session, User) - 1,
    }
    session.execute(update(ProcessedEmail).values(ticket_id=None))
    session.execute(delete(TicketExplanation))
    session.execute(delete(History))
    session.execute(delete(Comment))
    session.execute(delete(Ticket))
    session.execute(delete(User).where(User.id != admin.id))
    session.commit()
    return borrados


def main(entrada=input, db_engine=None, carpeta_respaldo: Path | None = None) -> int:
    """Corre el comando; ``entrada``, ``db_engine`` y ``carpeta_respaldo``
    se cambian en las pruebas. Devuelve el código de salida."""
    db_engine = db_engine or engine_app
    ruta_base = ruta_de_la_base(db_engine)
    init_db(db_engine)

    with sessionmaker(bind=db_engine)() as session:
        correo = admin_inicial()
        admin = correo and session.scalar(select(User).where(func.lower(User.email) == correo))
        if not admin:
            motivo = f"no existe el usuario {correo}" if correo else "ADMIN_INICIAL no está configurado"
            print(f"No se borró nada: {motivo}. Es el único usuario que se conserva.")
            return 1

        respaldo = respaldar(ruta_base, carpeta_respaldo)
        print(f"Respaldo de la base: {respaldo}")
        print(
            f"Se van a borrar {contar(session, Ticket)} tickets con sus comentarios, historial "
            f"y explicaciones de IA, y {contar(session, User) - 1} usuarios. "
            f"Se conserva solo a {admin.email}."
        )
        if entrada(f"Escribe {PALABRA_CONFIRMACION} para confirmar: ").strip() != PALABRA_CONFIRMACION:
            print("No se borró nada.")
            return 1

        borrados = limpiar(session, admin)

    print(
        f"Listo. Se borraron {borrados['tickets']} tickets, {borrados['comentarios']} "
        f"comentarios y {borrados['usuarios']} usuarios (además de {borrados['historial']} "
        f"registros de historial y {borrados['explicaciones']} explicaciones de IA)."
    )
    print("Se conservaron los correos procesados y la sesión de Microsoft del buzón.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
